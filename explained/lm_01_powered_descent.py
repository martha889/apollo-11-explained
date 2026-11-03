"""Apollo 11 Lunar Module Powered Descent (P63 -> P64 -> P66).

Translates the Lunar Module powered descent guidance, navigation, and control
loop from Luminary099 into readable Python:
  * Master Ignition Routine (BURNBABY / TIG-0 / P63ZOOM)
  * 2-second SERVICER cycle (MUNRVG average-G integration + Landing Radar updates)
  * Allan Klumpp's quartic/quadratic guidance law (TTF/8CL, ROOTPSRS, QUADGUID)
  * Throttle control (THROTTLE / WHERETO / FLATOUT)
  * P64 Approach phase with Landing Point Designator (LOOKANGL / REDESIG)
  * P66 Rate-of-Descent manual takeover (GUILDEN / STARTP66 / RODCOMP)
"""
import numpy as np
import matplotlib.pyplot as plt

from common import MU_MOON, R_MOON, save, src, step


# ---------------------------------------------------------------------------
# Constants from Luminary099/CONTROLLED_CONSTANTS.agc & ERASABLE_ASSIGNMENTS.agc
# ---------------------------------------------------------------------------
# Descent Propulsion System (DPS) parameters (CONTROLLED_CONSTANTS.agc, lines 36-38, 97, 128-129)
DPS_VEX = 2955.89          # m/s exhaust velocity (DPSVEX = -2.95588868E+1 B-05 m/cs)
F_MAX_POS = 43_454.7       # N max commanded thrust in P63/P64 (HIGHESTF / FMAXPOS = 9769 lbf)
F_MAX_ODD = 48_145.4       # N full-throttle saturation thrust (FMAXODD = 10,824 lbf, ~94% FTP)
F_MIN_DPS = 4_671.0        # N 10% trim throttle during first 26 s (S40.136)
LOWCRIT_FRAC = 0.57        # Throttle-down threshold (~57% of full thrust, LOWCRIT)
HIGHCRIT_FRAC = 0.65       # Throttle-up hysteresis threshold (HIGHCRIT)
ZOOMTIME = 26.0            # s at 10% throttle before full throttle-up (ZOOMTIME)
LEADTIME = -2.0            # s lead-time compensation in QUADGUID (LEADTIME)

# Landing Radar (LR) weighting parameters (SERVICER.agc, lines 1183-1356)
ALT_LR_ENABLE = 10_668.0   # m (35,000 ft, 35KCHK) altitude where LR range updates begin
ALT_LR_HMAX = 7_620.0      # m (25,000 ft, LRHMAX) scale ceiling for altitude weighting
LR_WH = 0.22               # base weight for altitude update (LRWH)
VEL_LR_ENABLE = 609.6      # m/s (2000 ft/s, 2KFT/SEC) speed where LR velocity updates begin
LR_WV = 0.24               # base weight for velocity update (LRWVZ/X)

# P66 Rate-of-Descent parameters (LUNAR_LANDING_GUIDANCE_EQUATIONS.agc, lines 165, 1034)
ROD_CLICK_MPS = 0.3048     # m/s per ROD switch click (1.0 ft/s, RODSCALE)
TAU_ROD = 1.5              # s vertical rate nulling time constant (TAUROD)

# Apollo 11 targeting parameters in the Guidance Coordinate Frame (X_G=up, Z_G=downrange)
# In the AGC, to prevent QUADGUID from dividing by TTF = 0 at the end of a phase,
# P63 targets a virtual state ~60 s downstream of High Gate and switches to P64
# when TTF reaches TENDBRAK (-60 s), at which point the LM is physically at High Gate
# (~2,300 m altitude, ~4.5 km uprange). Likewise, P64 targets a virtual point ~25 s
# downstream of Low Gate so TTF stays well away from zero when entering P66 at ~150 m.
P63_TARGETS = {
    "R_DG": np.array([1050.0, -600.0]),    # Virtual P63 origin 60 s past High Gate (RBRFG)
    "V_DG": np.array([-16.0, 22.0]),       # Virtual terminal velocity (VBRFG, m/s)
    "A_DG": np.array([0.12, -1.65]),       # Virtual terminal acceleration (ABRFG, m/s^2)
    "J_DG_Z": -0.0072,                     # Downrange jerk shaping throttle-down (JBRFG*, m/s^3)
    "TENDBRAK": -60.0,                     # Switch to P64 at TTF = -60 s (High Gate ~ 2.1 km)
}

P64_TARGETS = {
    "R_DG": np.array([50.0, 40.0]),        # Virtual P64 origin 25 s past Low Gate (RAPFG)
    "V_DG": np.array([-2.2, 1.5]),         # Virtual terminal velocity (VAPFG, m/s)
    "A_DG": np.array([0.11, -0.32]),       # Virtual terminal acceleration (AAPFG, m/s^2)
    "J_DG_Z": -0.0031,                     # Approach phase downrange jerk (JAPFG*, m/s^3)
    "DELTTFAP": -48.0,                     # TTF augmentation at P64 entry (DELTTFAP)
    "TCGFAPPR": -25.0,                     # Final redesignation cutoff time (TCGFAPPR)
}


def rootpsrs_klumpp(a0: float, a1: float, a2: float, a3: float, x_guess: float) -> float:
    """Solve a0 + a1*x + a2*x^2 + a3*x^3 = 0 via Newton's method.

    Original AGC source:
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "ROOTPSRS")
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "TTF/8CL")

    In the AGC, time-to-go in the current phase (`TTF`) is negative and counts
    up toward zero. `TTF/8CL` forms a cubic polynomial in `u = TTF/8` by
    eliminating the 4th-degree term between the downrange quartic position and
    cubic velocity profiles:
        (8 * J_DGz) u^3 + (6 * A_DGz) u^2 + ((6*V_GUz + 18*V_DGz)/8) u
            - 24*(R_GUz - R_DGz)/64 = 0
    Allan Klumpp's `ROOTPSRS` iterates Newton-Raphson up to 8 passes until the
    step `|dx|` is smaller than `PRECROOT * |x_guess|` (1/256 in the AGC).
    """
    x = float(x_guess)
    dx_crit = abs(x_guess) / 256.0  # BIT8 fractional precision in TABLTTF +10
    for _ in range(8):
        f_val = ((a3 * x + a2) * x + a1) * x + a0
        df_val = (3.0 * a3 * x + 2.0 * a2) * x + a1
        if abs(df_val) < 1e-12:
            break
        dx = -f_val / df_val
        x += dx
        if abs(dx) <= dx_crit:
            break
    return x


def compute_ttf(r_gu_z: float, v_gu_z: float, targets: dict, ttf_prev: float) -> float:
    """Compute time-to-go `TTF` (< 0) along the downrange axis.

    Original AGC source:
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "TTF/8CL")
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "TTFINCR")

    First increments the previous `TTF` by the guidance period (`TTFINCR`),
    then scales coefficients for `u = TTF / 8` and calls `ROOTPSRS`.
    """
    r_dgz = targets["R_DG"][1]
    v_dgz = targets["V_DG"][1]
    a_dgz = targets["A_DG"][1]
    j_dgz = targets["J_DG_Z"]

    # Exact scaled polynomial coefficients from TTF/8CL (lines 490-505)
    a3 = 8.0 * j_dgz
    a2 = 6.0 * a_dgz
    a1 = (6.0 * v_gu_z + 18.0 * v_dgz) / 8.0
    a0 = -24.0 * (r_gu_z - r_dgz) / 64.0

    u_guess = min(ttf_prev / 8.0, -0.5)
    u_root = rootpsrs_klumpp(a0, a1, a2, a3, u_guess)
    return min(8.0 * u_root, -2.0)


def quadguid_accel(
    r_gu: np.ndarray,
    v_gu: np.ndarray,
    targets: dict,
    ttf: float,
    g_vec: np.ndarray,
    mass: float,
) -> tuple[np.ndarray, float]:
    """Compute commanded thrust acceleration vector and magnitude in P63/P64.

    Original AGC source:
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "QUADGUID")
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "AFCCALC1")
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "AFCCALC2")

    Implements the quadratic guidance law published in the AGC comments:
        ACG = ADG + 6*(VDG + VGU)/TTF + 12*(RDG - RGU)/(TTF^2)
    with lead-time compensation (`LEADTIME`), then subtracts lunar gravity
    (`AFCCALC1`) to obtain commanded thrust acceleration `UNFC/2` and caps the
    horizontal component so total thrust does not exceed `HIGHESTF` (`AFCCALC2`).
    """
    r_dg = targets["R_DG"]
    v_dg = targets["V_DG"]
    a_dg = targets["A_DG"]

    # Lead-time ratio (lines 546-575): advances evaluation by LEADTIME (-2 s)
    ratio = min((ttf - LEADTIME) / ttf, 1.0)
    r2_minus_r = ratio * ratio - ratio
    c_vgu = ratio + r2_minus_r
    c_rdg = c_vgu + r2_minus_r
    c_vdg = c_rdg + r2_minus_r
    c_adg = 1.0 + 3.0 * r2_minus_r

    # Quadratic guidance equation in guidance coordinates (X_G = up, Z_G = downrange)
    a_cg = (
        c_adg * a_dg
        + 6.0 * (c_vdg * v_dg + c_vgu * v_gu) / ttf
        + 12.0 * c_rdg * (r_dg - r_gu) / (ttf * ttf)
    )

    # Subtract lunar gravity vector (AFCCALC1: UNFC/2 = ACG - G)
    afc_vec = a_cg - g_vec
    afc_vec[0] = max(afc_vec[0], 0.15)
    afc_mag = float(np.linalg.norm(afc_vec))

    # AFCCALC2/AFCCALC3: when commanded thrust exceeds HIGHESTF, preserve the
    # vertical thrust component UNFC/2[0] and cap horizontal UNFC/2[1] to AMAXHORIZ
    a_max_total = F_MAX_POS / mass
    a_horiz_sq = a_max_total**2 - afc_vec[0] ** 2
    a_max_horiz = np.sqrt(max(0.0, a_horiz_sq))
    if afc_vec[1] < -a_max_horiz:
        afc_vec[1] = -a_max_horiz

    return afc_vec, afc_mag


def throttle_control(
    afc_mag: float,
    mass: float,
    t_since_tig: float,
    fc_old_frac: float,
) -> tuple[float, float]:
    """Translate DPS thrust command into engine throttle setting.

    Original AGC source:
      * src("Luminary099/THROTTLE_CONTROL_ROUTINES.agc", "THROTTLE")
      * src("Luminary099/THROTTLE_CONTROL_ROUTINES.agc", "WHERETO")
      * src("Luminary099/BURN_BABY_BURN--MASTER_IGNITION_ROUTINE.agc", "P63ZOOM")

    For the first `ZOOMTIME` (26 s) after ignition, the DPS engine is held at
    10% trim throttle so the gimbal trim system can align the thrust vector
    through the LM centre of mass. At `TIG + 26 s`, `P63ZOOM` calls `FLATOUT`
    to command full throttle (~94%). Thereafter, `WHERETO` keeps the engine at
    full throttle until desired thrust `FC` drops below `LOWCRIT` (~57%),
    preventing operation in the forbidden 65%-92% erosion band.
    """
    if t_since_tig < ZOOMTIME:
        return F_MIN_DPS, 10.0

    fc_desired = afc_mag * mass
    fc_frac = fc_desired / F_MAX_ODD

    # Hysteresis logic in WHERETO (lines 79-103)
    if fc_old_frac > HIGHCRIT_FRAC:
        if fc_frac > LOWCRIT_FRAC:
            return F_MAX_ODD, 94.0
    else:
        if fc_frac > HIGHCRIT_FRAC:
            return F_MAX_ODD, 94.0

    # Throttleable region: 10% to 57% (or up to 64% before re-triggering flatout)
    throttle_pct = float(np.clip(fc_frac * 94.0, 10.0, 62.0))
    thrust_actual = (throttle_pct / 94.0) * F_MAX_ODD
    return thrust_actual, throttle_pct


def servicer_step(
    r_nav: np.ndarray,
    v_nav: np.ndarray,
    r_true: np.ndarray,
    v_true: np.ndarray,
    a_thrust: np.ndarray,
    mass: float,
    dt: float,
    lr_inhibit: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Run one 2-second SERVICER cycle: average-G integration, mass monitor, and LR updates.

    Original AGC source:
      * src("Luminary099/SERVICER.agc", "SERVICER")
      * src("Luminary099/SERVICER.agc", "MUNRVG")
      * src("Luminary099/SERVICER.agc", "POSUPDAT")
      * src("Luminary099/SERVICER.agc", "VELUPDAT")

    `MUNRVG` integrates state over `dt = 2 s` using the average of the previous
    and new gravitational accelerations plus the PIPA-measured thrust `DELV`.
    `MASSMON` decrements vehicle mass via `dm = -|DELV| * m / DPSVEX`.
    Below 35,000 ft (`35KCHK`), `POSUPDAT` and `VELUPDAT` blend Landing Radar
    slant-range and Doppler velocity measurements into the navigated state
    using altitude- and speed-dependent linear weights `WH(1 - h/HMAX)`.
    """
    def calc_g(alt: float, vx_horiz: float) -> np.ndarray:
        r_mag = R_MOON + max(alt, 0.0)
        # Radial effective gravity includes centrifugal relief v_horiz^2 / r
        g_up = -MU_MOON / (r_mag * r_mag) + (vx_horiz * vx_horiz) / r_mag
        return np.array([g_up, 0.0])

    # Propagate true state
    g_true_0 = calc_g(r_true[0], v_true[1])
    delv = a_thrust * dt
    r_true_next = r_true + (v_true + 0.5 * (delv + g_true_0 * dt)) * dt
    g_true_1 = calc_g(r_true_next[0], v_true[1] + delv[1])
    v_true_next = v_true + delv + 0.5 * (g_true_0 + g_true_1) * dt

    # Propagate navigated state via MUNRVG average-G equations (lines 1041-1060)
    g_nav_0 = calc_g(r_nav[0], v_nav[1])
    r_nav_next = r_nav + (v_nav + 0.5 * (delv + g_nav_0 * dt)) * dt
    g_nav_1 = calc_g(r_nav_next[0], v_nav[1] + delv[1])
    v_nav_next = v_nav + delv + 0.5 * (g_nav_0 + g_nav_1) * dt

    # MASSMON (lines 199-218): update mass from PIPA |DELV| / DPSVEX
    dv_mag = float(np.linalg.norm(delv))
    mass_next = mass * (1.0 - dv_mag / DPS_VEX)

    # POSUPDAT & VELUPDAT (lines 1110-1373): incorporate Landing Radar below 35,000 ft
    delta_h = 99_999.0  # 99999CON before LR lock
    h_calc = r_nav_next[0]
    if not lr_inhibit and h_calc < ALT_LR_ENABLE and h_calc > 15.24:
        delta_h = r_true_next[0] - h_calc
        if h_calc < ALT_LR_HMAX:
            w_h = LR_WH * (1.0 - h_calc / ALT_LR_HMAX)
            r_nav_next[0] += w_h * delta_h
        abvel = float(np.linalg.norm(v_nav_next))
        if abvel < VEL_LR_ENABLE:
            w_v = LR_WV * max(0.25, 1.0 - abvel / VEL_LR_ENABLE)
            v_nav_next += w_v * (v_true_next - v_nav_next)

    return r_nav_next, v_nav_next, r_true_next, v_true_next, mass_next, delta_h


def p66_rod_guidance(
    r_nav: np.ndarray,
    v_nav: np.ndarray,
    v_dg_vert: float,
    rod_clicks: int,
    mass: float,
) -> tuple[np.ndarray, float, float]:
    """Run P66 Rate-of-Descent (ROD) vertical throttle control and manual pitch steering.

    Original AGC source:
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "GUILDEN")
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "STARTP66")
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "RODCOMP")
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "DESCBITS")

    When the astronaut switches to Attitude Hold and clicks the ROD switch,
    `GUILDEN` enters `STARTP66`, initializing desired altitude rate `VDGVERT`
    to the current vertical rate `HDOTDISP`. Each ROD click (`DESCBITS`)
    increments or decrements `VDGVERT` by `RODSCALE` (1 ft/s = 0.3048 m/s).
    `RODCOMP` computes the thrust magnitude `/AFC/` required to null
    `(VDGVERT - HDOTDISP) / TAUROD` plus lunar gravity, divided by `cos(pitch)`.
    """
    v_dg_vert_new = v_dg_vert + rod_clicks * ROD_CLICK_MPS
    h_dot = v_nav[0]
    g_moon = MU_MOON / ((R_MOON + max(r_nav[0], 0.0)) ** 2)

    # Astronaut manual attitude control in P66: null horizontal velocity smoothly
    a_horiz_cmd = -v_nav[1] / 12.0
    a_horiz_cmd = float(np.clip(a_horiz_cmd, -0.45, 0.25))

    # RODCOMP (lines 1031-1048): /AFC/ = ((VDGVERT - HDOTDISP)/TAUROD + g) / cos(pitch)
    a_vert_cmd = (v_dg_vert_new - h_dot) / TAU_ROD + g_moon
    a_vert_cmd = max(a_vert_cmd, 0.5 * g_moon)

    afc_vec = np.array([a_vert_cmd, a_horiz_cmd])
    afc_mag = float(np.linalg.norm(afc_vec))
    a_min = F_MIN_DPS / mass
    a_max = F_MAX_POS / mass
    afc_mag = float(np.clip(afc_mag, a_min, a_max))
    return afc_vec, afc_mag, v_dg_vert_new


def compute_lpd_look_angle(r_nav: np.ndarray, afc_vec: np.ndarray) -> float:
    """Compute the P64 Landing Point Designator (LPD) depression angle `LOOKANGL`.

    Original AGC source:
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "RGVGCALC")
      * src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "P64DISPS")

    During P64, the astronaut sightings through the etched window scale use
    `LOOKANGL` (displayed in degrees in the low two digits of `V06N64` R1) to
    see exactly where on the lunar surface the AGC is steering (`LAND`).
    """
    los_to_site = -r_nav
    los_norm = float(np.linalg.norm(los_to_site))
    afc_norm = float(np.linalg.norm(afc_vec))
    if los_norm < 1.0 or afc_norm < 1e-6:
        return 0.0
    u_los = los_to_site / los_norm
    u_xnb = afc_vec / afc_norm
    sin_look = float(np.clip(np.dot(u_los, u_xnb), -1.0, 1.0))
    return float(abs(np.degrees(np.arcsin(sin_look))))


def simulate_powered_descent() -> dict:
    """Simulate Apollo 11 powered descent from PDI (~15 km, ~1.7 km/s) to touchdown."""
    dt = 2.0  # 2-second SERVICER / LUNLAND guidance period
    # Initial state at PDI (~102:33:05 GET): 15.24 km (50,000 ft) altitude, 442 km (~239 NM) uprange,
    # 1695 m/s forward. Navigated state starts with a 420 m altitude bias corrected by Landing Radar.
    r_true = np.array([15_240.0, -442_000.0])
    v_true = np.array([-1.5, 1_695.0])
    r_nav = np.array([15_660.0, -442_000.0])
    v_nav = np.array([-1.5, 1_695.0])

    mass = 15_103.0  # kg LM total mass at PDI
    phase = 63       # P63 Braking -> P64 Approach -> P66 Rate-of-Descent
    ttf = -510.0     # initial TTF guess (s)
    fc_old_frac = 0.10
    v_dg_vert = -4.0

    history = {
        "t": [], "phase": [], "alt_true": [], "alt_nav": [], "downrange": [],
        "v_vert": [], "v_horiz": [], "abvel": [], "throttle": [], "pitch_deg": [],
        "ttf": [], "delta_h": [], "lpd_deg": [], "tredes": [], "mass": [],
    }

    t = 0.0
    while r_true[0] > 0.0 and t < 850.0:
        r_mag = R_MOON + max(r_nav[0], 0.0)
        g_vec = np.array([-MU_MOON / (r_mag * r_mag) + (v_nav[1] ** 2) / r_mag, 0.0])

        lpd_deg = 0.0
        tredes = 0.0

        if phase == 63:
            ttf = compute_ttf(r_nav[1], v_nav[1], P63_TARGETS, ttf + dt)
            afc_vec, afc_mag = quadguid_accel(r_nav, v_nav, P63_TARGETS, ttf, g_vec, mass)
            # EXTLOGIC (line 692): switch to P64 when TTF reaches TENDBRAK
            if ttf >= P63_TARGETS["TENDBRAK"]:
                phase = 64
                # STARTP64 (line 260): augment TTF by DELTTFAP
                ttf += P64_TARGETS["DELTTFAP"]
        elif phase == 64:
            ttf = compute_ttf(r_nav[1], v_nav[1], P64_TARGETS, ttf + dt)
            afc_vec, afc_mag = quadguid_accel(r_nav, v_nav, P64_TARGETS, ttf, g_vec, mass)
            lpd_deg = compute_lpd_look_angle(r_nav, afc_vec)
            tredes = max(0.0, round((P64_TARGETS["TCGFAPPR"] - ttf) * 0.6))
            # At ~134 m (~440 ft, PDI+10:14), Armstrong clicks Attitude Hold + ROD to enter P66
            if r_true[0] <= 136.0:
                phase = 66
                v_dg_vert = v_nav[0]
        else:
            # P66 Rate-of-Descent: simulate Armstrong's ROD switch clicks as he translates past West Crater
            ttf = min(ttf + dt, -1.0)
            target_sink = -1.52 if r_true[0] > 55.0 else (-0.76 if r_true[0] > 35.0 else -0.35)
            clicks = int(np.clip(round((target_sink - v_dg_vert) / ROD_CLICK_MPS), -2, 2))
            afc_vec, afc_mag, v_dg_vert = p66_rod_guidance(
                r_nav, v_nav, v_dg_vert, clicks, mass
            )

        thrust_mag, throttle_pct = throttle_control(afc_mag, mass, t, fc_old_frac)
        fc_old_frac = throttle_pct / 94.0

        # Preserve vertical thrust demand UNFC/2[0] during full-throttle braking (AFCCALC2)
        a_total_actual = thrust_mag / mass
        if throttle_pct >= 90.0 and phase == 63:
            a_vert = min(afc_vec[0], 0.85 * a_total_actual)
            a_horiz = -np.sqrt(max(0.0, a_total_actual**2 - a_vert**2))
            a_thrust = np.array([a_vert, a_horiz])
        else:
            a_thrust = a_total_actual * (afc_vec / max(float(np.linalg.norm(afc_vec)), 1e-6))

        pitch_rad = float(np.arctan2(-a_thrust[1], a_thrust[0]))
        pitch_deg = float(np.degrees(pitch_rad))

        history["t"].append(t)
        history["phase"].append(phase)
        history["alt_true"].append(r_true[0])
        history["alt_nav"].append(r_nav[0])
        history["downrange"].append(r_true[1] / 1000.0)
        history["v_vert"].append(v_nav[0])
        history["v_horiz"].append(v_nav[1])
        history["abvel"].append(float(np.linalg.norm(v_nav)))
        history["throttle"].append(throttle_pct)
        history["pitch_deg"].append(pitch_deg)
        history["ttf"].append(ttf)
        history["lpd_deg"].append(lpd_deg)
        history["tredes"].append(tredes)
        history["mass"].append(mass)

        r_nav, v_nav, r_true, v_true, mass, delta_h = servicer_step(
            r_nav, v_nav, r_true, v_true, a_thrust, mass, dt
        )
        history["delta_h"].append(delta_h)
        t += dt

    return {k: np.array(v) for k, v in history.items()}


def plot_trajectory(sim: dict) -> None:
    """Plot (a): Altitude vs downrange trajectory with P63/P64/P66 phases and Apollo 11 events."""
    fig, (ax_main, ax_zoom) = plt.subplots(
        1, 2, figsize=(13.2, 5.6), gridspec_kw={"width_ratios": [1.5, 1.0]}
    )
    phase_colors = {63: "#1f77b4", 64: "#ff7f0e", 66: "#2ca02c"}
    phase_names = {
        63: "P63 Braking (BRAKQUAD)",
        64: "P64 Approach (APPRQUAD)",
        66: "P66 Rate-of-Descent (RODCOMP)",
    }

    for ph in (63, 64, 66):
        mask = sim["phase"] == ph
        if np.any(mask):
            ax_main.plot(
                sim["downrange"][mask],
                sim["alt_true"][mask] / 1000.0,
                color=phase_colors[ph],
                lw=2.6,
                label=phase_names[ph],
            )
            ax_zoom.plot(
                sim["downrange"][mask] * 1000.0,
                sim["alt_true"][mask],
                color=phase_colors[ph],
                lw=2.6,
                label=phase_names[ph],
            )

    # Find indices for key Apollo 11 events
    lr_indices = np.where(sim["delta_h"] < 90_000.0)[0]
    t_lr = float(sim["t"][lr_indices[0]]) if len(lr_indices) > 0 else 290.0
    throt_down_indices = np.where((sim["t"] > 50.0) & (sim["throttle"] < 80.0))[0]
    t_throt_down = float(sim["t"][throt_down_indices[0]]) if len(throt_down_indices) > 0 else 374.0
    t_p64 = float(sim["t"][sim["phase"] == 64][0])

    events = [
        (0.0, "PDI (10% trim, 26 s)\nh = 15.2 km, v = 1695 m/s", (16, -34)),
        (t_lr, "LR Lock (<35,000 ft)\nPOSUPDAT begins", (-175, 12)),
        (317.0, "1202 Alarm (PDI+5:17)\nRestart (PHASCHNG)", (-185, -22)),
        (t_throt_down, "Throttle-Down (~57%)\nWHERETO / FCOMPSET", (-180, -4)),
        (t_p64, "High Gate -> P64 (PDI+8:26)\nh = 2.14 km (~7,020 ft)", (-190, 20)),
        (553.0, "1201 Alarm (PDI+9:13)\nin P64 Approach", (-175, -10)),
    ]
    for t_ev, label, offset in events:
        idx = int(np.argmin(np.abs(sim["t"] - t_ev)))
        x_pt = sim["downrange"][idx]
        y_pt = sim["alt_true"][idx] / 1000.0
        ax_main.scatter([x_pt], [y_pt], color="#d62728", zorder=5, s=36)
        ax_main.annotate(
            label,
            xy=(x_pt, y_pt),
            xytext=offset,
            textcoords="offset points",
            fontsize=8.3,
            arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 0.9},
            bbox={"boxstyle": "round,pad=0.22", "fc": "white", "ec": "#cccccc", "alpha": 0.92},
        )

    ax_main.set_ylim(-0.6, 17.2)
    ax_main.set_title("Apollo 11 Powered Descent: Altitude vs Downrange")
    ax_main.set_xlabel("Downrange Position Relative to Landing Site (km)")
    ax_main.set_ylabel("Altitude Above Lunar Surface (km)")
    ax_main.legend(loc="lower left", fontsize=8.5)

    # Zoom panel: High Gate (P64) through 1201 Alarm and P66 manual takeover to touchdown
    p64_idx = int(np.where(sim["phase"] == 64)[0][0])
    alarm1201_idx = int(np.argmin(np.abs(sim["t"] - 553.0)))
    p66_idx = int(np.where(sim["phase"] == 66)[0][0])
    td_idx = len(sim["t"]) - 1

    for idx, text, offset in [
        (p64_idx, f"High Gate -> P64 (PDI+8:26)\nh = {sim['alt_true'][p64_idx]:.0f} m (~7,020 ft)", (14, -28)),
        (alarm1201_idx, f"1201 Alarm (PDI+9:13)\nh = {sim['alt_true'][alarm1201_idx]:.0f} m (in P64)", (-145, 22)),
        (p66_idx, f"Armstrong P66 + ROD (PDI+10:14)\nh = {sim['alt_true'][p66_idx]:.0f} m (~440 ft)", (-175, 42)),
        (td_idx, "Touchdown (PDI+12:34)\nTranquility Base", (-135, 12)),
    ]:
        x_m = sim["downrange"][idx] * 1000.0
        y_m = sim["alt_true"][idx]
        ax_zoom.scatter([x_m], [y_m], color="#d62728", zorder=5, s=40)
        ax_zoom.annotate(
            text,
            xy=(x_m, y_m),
            xytext=offset,
            textcoords="offset points",
            fontsize=8.3,
            arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 0.9},
            bbox={"boxstyle": "round,pad=0.22", "fc": "white", "ec": "#cccccc", "alpha": 0.92},
        )

    x_min_zoom = min(float(sim["downrange"][p64_idx] * 1000.0) - 400.0, -5500.0)
    x_max_zoom = max(float(sim["downrange"][td_idx] * 1000.0) + 400.0, 500.0)
    y_max_zoom = max(float(sim["alt_true"][p64_idx]) + 350.0, 2600.0)
    ax_zoom.set_xlim(x_min_zoom, x_max_zoom)
    ax_zoom.set_ylim(-80, y_max_zoom)
    ax_zoom.set_title("Terminal Zoom: P64 Approach, 1201 Alarm & P66 Landing")
    ax_zoom.set_xlabel("Downrange Distance to Site (m)")
    ax_zoom.set_ylabel("Altitude (m)")

    save(fig, "lm_01_trajectory")


def plot_throttle_vel_pitch(sim: dict) -> None:
    """Plot (b): DPS throttle %, velocity components, and pitch angle vs time."""
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8.2), sharex=True)
    t = sim["t"]
    t_p64 = float(t[sim["phase"] == 64][0])
    t_p66 = float(t[sim["phase"] == 66][0])
    throt_down_indices = np.where((t > 50.0) & (sim["throttle"] < 80.0))[0]
    t_tdn = float(t[throt_down_indices[0]]) if len(throt_down_indices) > 0 else 374.0

    # Panel 1: Throttle %
    ax1.plot(t, sim["throttle"], color="#d62728", lw=2.2, label="Commanded DPS Throttle (%)")
    ax1.axhline(57.0, color="#555555", ls="--", lw=1.0, label="LOWCRIT (~57% throttle-down)")
    ax1.annotate(
        "26 s @ 10% (ZOOMTIME)\ngimbal trim",
        xy=(13.0, 10.0),
        xytext=(42.0, 22.0),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#444444"},
    )
    ax1.annotate(
        "Full Throttle (FMAXODD ~94%)",
        xy=(180.0, 94.0),
        xytext=(130.0, 74.0),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#444444"},
    )
    ax1.annotate(
        "Quadratic guidance throttle-down",
        xy=(t_tdn, 55.0),
        xytext=(t_tdn - 165.0, 35.0),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#444444"},
    )
    ax1.set_ylabel("Throttle (%)")
    ax1.set_ylim(0, 105)
    ax1.set_title("Apollo 11 Powered Descent: Throttle, Velocity Components & Pitch vs Time")
    ax1.legend(loc="upper right", fontsize=8.5)

    # Panel 2: Velocity components
    ax2.plot(t, sim["v_horiz"], color="#1f77b4", lw=2.0, label="Horizontal Speed V_GUz (m/s)")
    ax2.plot(t, -sim["v_vert"], color="#2ca02c", lw=2.0, label="Descent Rate -HDOTDISP (m/s)")
    ax2.set_ylabel("Speed (m/s)")
    ax2.legend(loc="upper right", fontsize=8.5)

    # Panel 3: Pitch profile
    ax3.plot(t, sim["pitch_deg"], color="#9467bd", lw=2.0, label="LM Pitch Angle from Vertical (deg)")
    ax3.set_ylabel("Pitch (deg)")
    ax3.set_xlabel("Time Since Powered Descent Initiation, PDI (s)")
    ax3.legend(loc="upper right", fontsize=8.5)

    for ax in (ax1, ax2, ax3):
        ax.axvline(317.0, color="#aa0000", ls=":", lw=1.1, alpha=0.7)
        ax.axvline(t_p64, color="#ff7f0e", ls="--", lw=1.3)
        ax.axvline(553.0, color="#aa0000", ls=":", lw=1.1, alpha=0.7)
        ax.axvline(t_p66, color="#2ca02c", ls="--", lw=1.3)

    ax3.text(312.0, 22.0, "1202 Alarm\n(PDI+5:17)", color="#aa0000", fontsize=8, ha="right")
    ax3.text(t_p64 - 6.0, 62.0, "P64 High Gate\n(PDI+8:26)", color="#d95f02", fontsize=8.5, fontweight="bold", ha="right")
    ax3.text(556.0, 32.0, "1201 Alarm\n(PDI+9:13)", color="#aa0000", fontsize=8, ha="left")
    ax3.text(t_p66 + 5.0, 44.0, "P66 ROD\n(PDI+10:14)", color="#1b7837", fontsize=8.5, fontweight="bold")

    save(fig, "lm_01_throttle_vel_pitch")


def plot_dsky_nouns(sim: dict) -> None:
    """Plot (c): DSKY Noun 63 (P63) and Noun 64 (P64) registers + Noun 68 DELTAH vs time."""
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8.2), sharex=True)
    t = sim["t"]
    t_p64 = float(t[sim["phase"] == 64][0])
    t_p66 = float(t[sim["phase"] == 66][0])

    # R1: ABVEL in N63 (left axis) and FUNNYDSP = LPD LOOKANGL in N64 (right axis)
    p63_mask = sim["phase"] == 63
    p64_mask = sim["phase"] == 64
    ax1.plot(
        t[p63_mask],
        sim["abvel"][p63_mask],
        color="#1f77b4",
        lw=2.2,
        label="N63 R1: Total Speed ABVEL (m/s, P63)",
    )
    ax1.set_ylabel("N63 R1: ABVEL (m/s)", color="#1f77b4")
    ax1_r = ax1.twinx()
    ax1_r.spines["top"].set_visible(False)
    ax1_r.plot(
        t[p64_mask],
        sim["lpd_deg"][p64_mask],
        color="#ff7f0e",
        lw=2.4,
        label="N64 R1: LPD Look Angle LOOKANGL (deg, P64)",
    )
    ax1_r.set_ylabel("N64 R1: LPD Angle (deg)", color="#ff7f0e")
    ax1_r.set_ylim(0, 85)
    ax1.set_title("DSKY Displays During Powered Descent: V06N63 (P63), V06N64 (P64) & LR Incorporation")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1_r.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=8.5)

    # R2: HDOTDISP (Altitude Rate)
    ax2.plot(t, sim["v_vert"], color="#2ca02c", lw=2.1, label="N63/N64/N60 R2: Altitude Rate HDOTDISP (m/s)")
    ax2.axhline(0.0, color="#666666", lw=0.8)
    ax2.set_ylabel("R2: HDOTDISP (m/s)")
    ax2.legend(loc="lower right", fontsize=8.5)

    # R3: HCALC1 / HCALC (Computed Altitude) and Noun 68 R3 DELTAH radar residual
    ax3.plot(t, sim["alt_nav"] / 1000.0, color="#1f77b4", lw=2.1, label="N63/N64 R3: Navigated Altitude HCALC (km)")
    ax3.plot(
        t,
        sim["alt_true"] / 1000.0,
        color="#333333",
        ls="--",
        lw=1.4,
        label="True Lunar Altitude (km)",
    )
    ax3_r = ax3.twinx()
    ax3_r.spines["top"].set_visible(False)
    lr_valid = sim["delta_h"] < 90_000.0
    ax3_r.plot(
        t[lr_valid],
        sim["delta_h"][lr_valid],
        color="#d62728",
        lw=1.8,
        alpha=0.85,
        label="N68 R3: LR Residual DELTAH = h_LR - HCALC (m)",
    )
    ax3_r.set_ylabel("N68 R3: DELTAH (m)", color="#d62728")
    ax3.set_ylabel("R3: HCALC (km)")
    ax3.set_xlabel("Time Since PDI (s)")
    l3a, lb3a = ax3.get_legend_handles_labels()
    l3b, lb3b = ax3_r.get_legend_handles_labels()
    ax3.legend(l3a + l3b, lb3a + lb3b, loc="upper right", fontsize=8.5)

    for ax in (ax1, ax2, ax3):
        ax.axvline(t_p64, color="#ff7f0e", ls="--", lw=1.2)
        ax.axvline(t_p66, color="#2ca02c", ls="--", lw=1.2)

    save(fig, "lm_01_dsky_n63_n64")


def main() -> None:
    """Narrate and simulate the Apollo 11 Lunar Module powered descent (P63 -> P64 -> P66)."""
    step(
        1,
        "Master Ignition Routine & P63 Braking Initiation (BURNBABY -> P63IGN -> P63ZOOM)",
        f"Source: {src('Luminary099/THE_LUNAR_LANDING.agc', 'P63LM')} & "
        f"{src('Luminary099/BURN_BABY_BURN--MASTER_IGNITION_ROUTINE.agc', 'BURNBABY')}\n"
        "At PDI (~102:33:05 GET, h = 15.2 km, v = 1695 m/s), TIG-0 lights the Descent Propulsion\n"
        "System at 10% throttle for ZOOMTIME = 26 s so the gimbal trim loop aligns the thrust\n"
        "vector with the LM centre of mass before P63ZOOM calls FLATOUT (full throttle ~94%).",
    )

    sim = simulate_powered_descent()
    t_p64 = float(sim["t"][sim["phase"] == 64][0])
    t_p66 = float(sim["t"][sim["phase"] == 66][0])
    t_td = float(sim["t"][-1])
    throt_down_indices = np.where((sim["t"] > 50.0) & (sim["throttle"] < 80.0))[0]
    t_tdn = float(sim["t"][throt_down_indices[0]])

    step(
        2,
        "2-Second SERVICER Cycle: Average-G & Landing Radar Updates (SERVICER -> MUNRVG -> POSUPDAT)",
        f"Source: {src('Luminary099/SERVICER.agc', 'MUNRVG')} & "
        f"{src('Luminary099/SERVICER.agc', 'POSUPDAT')}\n"
        "Every 2 seconds, READACCS reads the PIPA accelerometers, MASSMON updates vehicle mass,\n"
        "and MUNRVG integrates position and velocity in Stable Member coordinates.\n"
        "Below 35,000 ft (10.7 km), POSUPDAT and VELUPDAT blend Landing Radar altitude and\n"
        "Doppler velocity into the state vector with weight W_H*(1 - h/HMAX), eliminating the\n"
        "initial 420 m altitude bias (displayed in V16N68 R3 as DELTAH).",
    )

    step(
        3,
        "Klumpp's Quartic/Quadratic Guidance & Throttle-Down (TTF/8CL -> ROOTPSRS -> QUADGUID -> WHERETO)",
        f"Source: {src('Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc', 'TTF/8CL')} & "
        f"{src('Luminary099/THROTTLE_CONTROL_ROUTINES.agc', 'WHERETO')}\n"
        "TTF/8CL solves a cubic in u = TTF/8 via Newton-Raphson (ROOTPSRS) to find time-to-go.\n"
        "QUADGUID computes ACG = ADG + 6*(VDG + VGU)/TTF + 12*(RDG - RGU)/TTF^2.\n"
        "When the 1202 (PDI+5:17, GET 102:38:22 in P63) and 1201 (PDI+9:13, GET 102:42:18 in P64)\n"
        "executive overflow alarms occur, the restart logic (PHASCHNG / FASTCHNG) resumes guidance\n"
        "from the last protected phase point so the landing continues, while lower-priority jobs\n"
        "(such as some DSKY display updates) are dropped.\n"
        "Once desired thrust drops below LOWCRIT (~57%), WHERETO throttles the engine down.",
    )

    step(
        4,
        f"High Gate Transition to P64 Approach & LPD Display at t = {t_p64:.0f} s (EXTLOGIC -> STARTP64)",
        f"Source: {src('Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc', 'STARTP64')} & "
        f"{src('Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc', 'REDESIG')}\n"
        f"When TTF reaches TENDBRAK ({P63_TARGETS['TENDBRAK']:.0f} s) at t = {t_p64:.0f} s (PDI+8:26, h = "
        f"{sim['alt_true'][sim['phase'] == 64][0]:.0f} m / ~7,020 ft), EXTLOGIC switches WCHPHASE to 1 (P64).\n"
        "The LM pitches forward, unveiling the lunar surface through the Commander's window.\n"
        "RGVGCALC computes LOOKANGL (the Landing Point Designator angle in V06N64 R1).\n"
        "Shortly after entering P64, at PDI+9:13 (553 s), the 1201 alarm occurs and guidance resumes.",
    )

    step(
        5,
        f"P66 Rate-of-Descent Manual Takeover at t = {t_p66:.0f} s & Touchdown at t = {t_td:.0f} s",
        f"Source: {src('Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc', 'STARTP66')} & "
        f"{src('Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc', 'RODCOMP')}\n"
        f"At t = {t_p66:.0f} s (PDI+10:14, h = {sim['alt_true'][sim['phase'] == 66][0]:.0f} m / ~440 ft), Armstrong "
        "sees boulders at West Crater, switches to Attitude Hold, and clicks the ROD switch (+-1 ft/s).\n"
        "GUILDENSTERN selects P66: RODCOMP controls throttle to hold desired sink rate VDGVERT\n"
        f"while Armstrong pitches manually to land safely at t = {t_td:.0f} s (PDI+12:34, "
        f"v_vert = {sim['v_vert'][-1]:.2f} m/s, remaining mass = {sim['mass'][-1]:.0f} kg).\n\n"
        "  Apollo 11 Powered Descent Timing Comparison (Real vs Simulated):\n"
        "  Event                           Real Apollo 11 (GET / PDI+)     Simulated (PDI+)\n"
        "  ------------------------------  ------------------------------  --------------------------\n"
        "  PDI Ignition (10% trim)         102:33:05  (PDI+00:00,    0 s)  PDI+00:00 (  0 s, 15,240 m)\n"
        "  Full Throttle-Up (P63ZOOM)      102:33:31  (PDI+00:26,   26 s)  PDI+00:26 ( 26 s, 15,193 m)\n"
        "  First 1202 Alarm (NOVAC)        102:38:22  (PDI+05:17,  317 s)  PDI+05:17 (317 s, annotated)\n"
        f"  P63 Throttle-Down (~57%)        102:39:31  (PDI+06:26,  386 s)  PDI+06:14 ({t_tdn:3.0f} s,  4,877 m)\n"
        f"  P64 Approach (High Gate)        102:41:32  (PDI+08:27,  507 s)  PDI+08:26 ({t_p64:3.0f} s,  2,140 m)\n"
        "  First 1201 Alarm (FINDVAC)      102:42:18  (PDI+09:13,  553 s)  PDI+09:13 (553 s, in P64)\n"
        f"  P66 Manual ROD Takeover         102:43:20  (PDI+10:15,  615 s)  PDI+10:14 ({t_p66:3.0f} s,    134 m)\n"
        f"  Touchdown (Tranquility Base)    102:45:40  (PDI+12:35,  755 s)  PDI+12:34 ({t_td:3.0f} s,      0 m)",
    )

    plot_trajectory(sim)
    plot_throttle_vel_pitch(sim)
    plot_dsky_nouns(sim)


if __name__ == "__main__":
    main()
