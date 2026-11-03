"""Apollo 11 Lunar Module Powered Ascent Guidance (P12).

Translates the Lunar Module powered ascent program from Luminary099 into
readable Python:
  * Pre-ignition target & engine initialization (P12LM / P12INIT / COMMINIT)
  * 4-sample moving-average 1/DV mass-to-thrust filter (ATMAG)
  * Vertical rise and terrain clearance logic (CHECKALT / CHECKYAW / EXITVR)
  * Explicit linear-tangent-style ascent guidance (ASCENT / MAINENG / RATES / CONST / CMPONENT)
  * Engine cutoff timer scheduling at TGO < 4 s (ENGOFF / CUTOFF)
"""
import numpy as np
import matplotlib.pyplot as plt

from common import MU_MOON, R_MOON, save, src, step


# ---------------------------------------------------------------------------
# Constants from Luminary099/P12.agc, ASCENT_GUIDANCE.agc, CONTROLLED_CONSTANTS.agc
# ---------------------------------------------------------------------------
# Ascent Propulsion System (APS) parameters (CONTROLLED_CONSTANTS.agc, lines 39-41, 67-85, 96)
APS_THRUST = 15_568.8      # N (3500 lbf, FAPS = 1.5569 B-7)
APS_MDOT = 5.299           # kg/s net mass flow rate (5.135 APS + 0.164 RCS, comment line 83)
APS_VEX = 3_030.0          # m/s effective exhaust velocity (APSVEX = -3030 E-2 B-5, 9942 ft/s)
MASS_LIFTOFF = 4_869.9     # kg nominal liftoff mass (comment line 71 of CONTROLLED_CONSTANTS.agc)
TBUP_INIT = 919.02         # s initial burn-up time m0/mdot ((TBUP)A = 91902 B-17 cs)
AT_INIT = 3.2883           # m/s^2 initial ascent acceleration ((AT)A = 3.2883 E-4 B9 m/cs^2)
TTO_TAILOFF = -0.10        # s tailoff time compensation (ATDECAY = -10 cs)

# Target parameters from P12.agc (lines 241-243) and P70-P71.agc (line 426)
H_INJECT = 18_288.0        # m cutoff altitude (60,000 ft, HINJECT = 18288 B-24)
R_CO = R_MOON + H_INJECT   # m cutoff radius (RCO = /LAND/ + HINJECT)
RDOT_D_NOM = 5.9436        # m/s target radial rate at cutoff (19.5 ft/s, RDOTDNOM)
VINJ_NOM_30NM = 1_679.24   # m/s default horizontal speed in P12.agc (5509.5 ft/s -> 17x56 km)
VINJ_83KM = 1_685.65       # m/s V06N76 target horizontal speed for a ~17 x 83 km (45 NM) orbit
VR_TIPOVER = 12.192        # m/s radial rate to exit vertical rise (40 ft/s, 40FPS in CHECKYAW)

# Guidance constants from ASCENT_GUIDANCE.agc (lines 584-603)
KT1 = 0.5000               # 2nd-order Tsiolkovsky factor in MAINENG (KT1)
T3_RATE_FREEZE = 10.0      # s freeze steering rates B, D when TGO < 10 s (T3 = 1000 B-17 cs)
T2_CONST_FREEZE = 2.0      # s freeze all steering coefficients when TGO < 2 s (T2A = 200 B-17 cs)
T_ENGOFF_THRESH = 4.0      # s schedule engine cutoff timer when TGO < 4 s (4SEC(17))
PRLIMIT_FPS3 = -0.1 * 0.3048  # m/s^3 minimum radial rate-of-change limit (PRLIMIT = -0.1 ft/s^3)


def logsub_agc(x: float) -> float:
    """Compute `-ln(x)` as implemented by the AGC `LOGSUB` polynomial routine.

    Original AGC source:
      * src("Luminary099/ASCENT_GUIDANCE.agc", "LOGSUB")

    In the AGC interpreter, `LOGSUB` normalizes `x = 1 - TGO/TBUP` and evaluates
    a 6th-degree Chebyshev polynomial on `[0.5, 1.0)` to return `-ln(x) > 0`.
    """
    return float(-np.log(max(x, 1e-6)))


def atmag_filter(
    dv_measured: float,
    inv_dv_history: list[float],
    tbup_prev: float,
    dt: float = 2.0,
) -> tuple[float, float, list[float]]:
    """Update burn-up time `TBUP` (tau = m / mdot) and thrust acceleration `AT`.

    Original AGC source:
      * src("Luminary099/ASCENT_GUIDANCE.agc", "ATMAG")
      * src("Luminary099/P12.agc", "P12INIT")

    Every 2 seconds, `ATMAG` reads the PIPA velocity increment `ABDVCONV` over
    the last guidance cycle, shifts its reciprocal into a 4-sample ring buffer
    (`1/DV0` .. `1/DV3`), and smooths `TBUP` (the time remaining until the
    vehicle mass would reach zero at current mass flow rate):
        TBUP_new = 0.5 * TBUP_old + 0.5 * (VE * dt * (1/DV0 + 1/DV1 + 1/DV2 + 1/DV3) / 4) - 3 s
        AT = VE / TBUP_new
    """
    inv_dv0 = 1.0 / max(dv_measured, 0.1)
    updated_hist = [inv_dv0] + inv_dv_history[:3]
    avg_inv_dv = sum(updated_hist) / 4.0

    # Lines 61-79 of ASCENT_GUIDANCE.agc: average with previous TBUP minus 6-sec/2 offset
    tbup_est = APS_VEX * dt * avg_inv_dv
    tbup_new = 0.5 * tbup_prev + 0.5 * tbup_est - 1.0
    at_new = APS_VEX / max(tbup_new, 50.0)
    return tbup_new, at_new, updated_hist


def ascent_guidance_step(
    r_mag: float,
    r_dot: float,
    z_dot: float,
    tbup: float,
    at_mag: float,
    tgo_prev: float,
    flvr: bool,
    flpc: bool,
    pcons: float,
    prate: float,
    z_dot_target: float = VINJ_83KM,
) -> dict:
    """Execute one 2-second pass of the AGC explicit ascent guidance (`ASCENT`).

    Original AGC source:
      * src("Luminary099/ASCENT_GUIDANCE.agc", "ASCENT")
      * src("Luminary099/ASCENT_GUIDANCE.agc", "MAINENG")
      * src("Luminary099/ASCENT_GUIDANCE.agc", "RATES")
      * src("Luminary099/ASCENT_GUIDANCE.agc", "CONST")
      * src("Luminary099/ASCENT_GUIDANCE.agc", "CMPONENT")
      * src("Luminary099/ASCENT_GUIDANCE.agc", "CHECKALT")

    Computes effective radial gravity `GEFF` (lunar gravity plus centrifugal
    relief `v_z^2 / r`), forms the velocity-to-be-gained vector `VGVECT`,
    updates time-to-go `TGO` via a 2nd-order rocket equation (`MAINENG`), and
    solves the logarithmic boundary-value integrals (`RATES` / `CONST`) for the
    linear acceleration profile `a_r(t) = (A + B*(t - t0)) / tau - g_eff`.
    """
    # Effective radial gravity GEFF = -mu/r^2 + v_horiz^2 / r (lines 105-117)
    g_radial = -MU_MOON / (r_mag * r_mag)
    centrifugal = (z_dot * z_dot) / r_mag
    g_eff = g_radial + centrifugal

    # Velocity errors (lines 118-135)
    dz_dot = z_dot_target - z_dot
    dr_dot = RDOT_D_NOM - r_dot

    # Velocity-to-be-gained VGVECT compensated for GEFF * TGO (lines 136-147)
    vg_r = dr_dot - tgo_prev * g_eff
    vg_z = dz_dot
    vg_mag = float(np.hypot(vg_r, vg_z))

    # MAINENG (lines 159-168): TGO = TBUP * (VG/VE) * (1 - KT1 * VG/VE) - TTO
    vg_over_ve = vg_mag / APS_VEX
    tgo = tbup * vg_over_ve * (1.0 - KT1 * vg_over_ve) - TTO_TAILOFF
    tgo = max(tgo, 0.05)

    # Vertical rise check (CHECKALT / CHECKYAW, lines 380-449)
    h_alt = r_mag - R_MOON
    if flvr and (r_dot >= VR_TIPOVER or h_alt >= 7_620.0):
        flvr = False

    # Update linear-tangent steering coefficients A (PCONS) and B (PRATE) if TGO >= T2A (2 s)
    if tgo >= T2_CONST_FREEZE:
        neg_L = logsub_agc(1.0 - tgo / tbup)
        L_val = -neg_L  # L = ln(1 - TGO/TBUP) < 0
        d12 = tbup + tgo / L_val

        if not flpc and tgo >= T3_RATE_FREEZE:
            # RATES (lines 211-246): compute B (PRATE)
            d21 = tgo - d12
            e_val = 0.5 * tgo - d21
            neg_dr = r_mag + r_dot * tgo - R_CO
            b_val = (d21 * dr_dot + neg_dr) / (e_val * tgo)
            # B > 0 is not permitted (line 231: BMN CHKBMAG)
            if b_val > 0.0:
                b_val = 0.0
            elif b_val / tbup < PRLIMIT_FPS3:
                b_val = PRLIMIT_FPS3 * tbup
            prate = b_val
        else:
            # NORATES (lines 205-210): freeze B = 0 once TGO < T3 (10 s)
            flpc = True
            prate = 0.0

        # CONST (lines 262-270): A = -DRDOT / L - B * D12
        pcons = -dr_dot / L_val - prate * d12

    # CMPONENT (lines 278-329): evaluate commanded radial & downrange thrust accelerations
    dt_lead = 2.0  # 100CS lead time in CMPONENT
    atr = (pcons + prate * dt_lead) / tbup - g_eff
    max_atr = 0.92 * at_mag
    atr_clamped = float(np.clip(atr, -max_atr, max_atr))
    atp = float(np.sign(dz_dot) * np.sqrt(max(0.0, at_mag * at_mag - atr_clamped * atr_clamped)))

    if flvr:
        # KEEPVR1 (line 465): during vertical rise, command pure radial thrust UNIT/R/
        u_r, u_z = 1.0, 0.0
        pitch_deg = 0.0
    else:
        u_r = atr_clamped / at_mag
        u_z = atp / at_mag
        pitch_deg = float(np.degrees(np.arctan2(u_z, u_r)))

    return {
        "tgo": tgo,
        "vg_mag": vg_mag,
        "g_eff": g_eff,
        "atr": atr_clamped,
        "atp": atp,
        "u_r": u_r,
        "u_z": u_z,
        "pitch_deg": pitch_deg,
        "flvr": flvr,
        "flpc": flpc,
        "pcons": pcons,
        "prate": prate,
    }


def compute_orbit_apsides(r_mag: float, r_dot: float, z_dot: float) -> tuple[float, float]:
    """Compute perilune and apolune altitudes (km) from state at engine cutoff."""
    v_sq = r_dot * r_dot + z_dot * z_dot
    energy = 0.5 * v_sq - MU_MOON / r_mag
    sma = -MU_MOON / (2.0 * energy)
    h_ang = r_mag * z_dot
    ecc = float(np.sqrt(max(0.0, 1.0 + 2.0 * energy * (h_ang * h_ang) / (MU_MOON * MU_MOON))))
    r_peri = sma * (1.0 - ecc)
    r_apo = sma * (1.0 + ecc)
    return (r_peri - R_MOON) / 1000.0, (r_apo - R_MOON) / 1000.0


def simulate_ascent_p12() -> dict:
    """Simulate Lunar Module powered ascent from Tranquility Base to orbital insertion."""
    dt = 2.0  # 2-second SERVICER cycle
    r_mag = R_MOON
    downrange_m = 0.0
    r_dot = 0.0
    z_dot = 0.0
    mass = MASS_LIFTOFF

    tbup = TBUP_INIT
    at_mag = AT_INIT
    inv_dv_hist = [1.0 / (AT_INIT * dt)] * 4
    tgo = 435.0
    flvr = True
    flpc = False
    pcons = 0.0
    prate = 0.0

    hist = {
        "t": [], "alt_km": [], "downrange_km": [], "r_dot": [], "z_dot": [],
        "vg": [], "tgo": [], "pitch_deg": [], "atr": [], "atp": [], "at_mag": [],
        "pcons": [], "prate": [], "mass": [],
    }

    t = 0.0
    while t < 500.0:
        g_out = ascent_guidance_step(
            r_mag, r_dot, z_dot, tbup, at_mag, tgo, flvr, flpc, pcons, prate
        )
        tgo = g_out["tgo"]
        flvr = g_out["flvr"]
        flpc = g_out["flpc"]
        pcons = g_out["pcons"]
        prate = g_out["prate"]

        hist["t"].append(t)
        hist["alt_km"].append((r_mag - R_MOON) / 1000.0)
        hist["downrange_km"].append(downrange_m / 1000.0)
        hist["r_dot"].append(r_dot)
        hist["z_dot"].append(z_dot)
        hist["vg"].append(g_out["vg_mag"])
        hist["tgo"].append(tgo)
        hist["pitch_deg"].append(g_out["pitch_deg"])
        hist["atr"].append(g_out["atr"])
        hist["atp"].append(g_out["atp"])
        hist["at_mag"].append(at_mag)
        hist["pcons"].append(pcons)
        hist["prate"].append(prate)
        hist["mass"].append(mass)

        # ENGOFF (lines 173-178, 470-505): when TGO < 4 s, schedule final partial step to TGO = 0
        step_dt = min(dt, tgo) if tgo <= T_ENGOFF_THRESH else dt

        # Integrate equations of motion over step_dt in spherical lunar coordinates
        n_sub = 20
        h_sub = step_dt / n_sub
        dv_accum = 0.0
        for _ in range(n_sub):
            a_thrust = APS_THRUST / mass
            dv_accum += a_thrust * h_sub
            a_r_net = a_thrust * g_out["u_r"] - MU_MOON / (r_mag * r_mag) + (z_dot * z_dot) / r_mag
            a_z_net = a_thrust * g_out["u_z"] - (r_dot * z_dot) / r_mag
            r_mag += r_dot * h_sub + 0.5 * a_r_net * h_sub * h_sub
            downrange_m += (z_dot * (R_MOON / r_mag)) * h_sub
            r_dot += a_r_net * h_sub
            z_dot += a_z_net * h_sub
            mass -= APS_MDOT * h_sub

        t += step_dt
        if step_dt < dt or tgo <= 0.15:
            hist["t"].append(t)
            hist["alt_km"].append((r_mag - R_MOON) / 1000.0)
            hist["downrange_km"].append(downrange_m / 1000.0)
            hist["r_dot"].append(r_dot)
            hist["z_dot"].append(z_dot)
            hist["vg"].append(0.0)
            hist["tgo"].append(0.0)
            hist["pitch_deg"].append(g_out["pitch_deg"])
            hist["atr"].append(g_out["atr"])
            hist["atp"].append(g_out["atp"])
            hist["at_mag"].append(APS_THRUST / mass)
            hist["pcons"].append(pcons)
            hist["prate"].append(prate)
            hist["mass"].append(mass)
            break

        tbup, at_mag, inv_dv_hist = atmag_filter(dv_accum, inv_dv_hist, tbup, dt)

    out = {k: np.array(v) for k, v in hist.items()}
    hp_km, ha_km = compute_orbit_apsides(
        R_MOON + out["alt_km"][-1] * 1000.0, out["r_dot"][-1], out["z_dot"][-1]
    )
    out["perilune_km"] = hp_km
    out["apolune_km"] = ha_km
    return out


def plot_altitude_velocity(sim: dict) -> None:
    """Plot 1: Altitude, horizontal & radial velocity components vs time."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 7.2), sharex=True)
    t = sim["t"]

    # Panel 1: Altitude & Radial Velocity
    ax1.plot(t, sim["alt_km"], color="#1f77b4", lw=2.4, label="Altitude h = |R| - /LAND/ (km)")
    ax1.axhline(H_INJECT / 1000.0, color="#1f77b4", ls="--", lw=1.1, label="HINJECT Target (18.29 km / 60,000 ft)")
    ax1.set_ylabel("Altitude (km)", color="#1f77b4")

    ax1_r = ax1.twinx()
    ax1_r.spines["top"].set_visible(False)
    ax1_r.plot(t, sim["r_dot"], color="#2ca02c", lw=2.0, label="Radial Rate RDOT (m/s)")
    ax1_r.axhline(RDOT_D_NOM, color="#2ca02c", ls=":", lw=1.1, label="RDOTDNOM Target (5.94 m/s / 19.5 ft/s)")
    ax1_r.set_ylabel("Radial Rate RDOT (m/s)", color="#2ca02c")

    ax1.set_title(
        f"Apollo 11 Powered Ascent (P12): Climb to {sim['alt_km'][-1]:.1f} km Cutoff "
        f"({sim['perilune_km']:.1f} x {sim['apolune_km']:.1f} km Lunar Orbit)"
    )
    l1, lb1 = ax1.get_legend_handles_labels()
    l2, lb2 = ax1_r.get_legend_handles_labels()
    ax1.legend(l1 + l2, lb1 + lb2, loc="upper left", fontsize=8.5)

    idx_peak_rdot = int(np.argmax(sim["r_dot"]))
    ax1_r.annotate(
        f"Peak climb rate\nRDOT = {sim['r_dot'][idx_peak_rdot]:.1f} m/s",
        xy=(t[idx_peak_rdot], sim["r_dot"][idx_peak_rdot]),
        xytext=(t[idx_peak_rdot] + 25.0, sim["r_dot"][idx_peak_rdot] - 6.0),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#2ca02c"},
    )

    # Panel 2: Horizontal Velocity & Velocity-to-be-gained VG
    ax2.plot(t, sim["z_dot"], color="#d62728", lw=2.3, label="Horizontal Speed ZDOT (m/s)")
    ax2.plot(t, sim["vg"], color="#9467bd", lw=1.9, ls="--", label="Velocity-to-be-Gained |VGVECT| (m/s)")
    ax2.axhline(VINJ_83KM, color="#555555", ls=":", lw=1.0, label=f"Target ZDOTD ({VINJ_83KM:.1f} m/s)")

    ax2.annotate(
        f"Engine Cutoff (ENGOFF)\nt = {t[-1]:.1f} s, ZDOT = {sim['z_dot'][-1]:.1f} m/s\n"
        f"Orbit: {sim['perilune_km']:.1f} x {sim['apolune_km']:.1f} km",
        xy=(t[-1], sim["z_dot"][-1]),
        xytext=(t[-1] - 135.0, sim["z_dot"][-1] - 480.0),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#333333"},
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#cccccc"},
    )
    ax2.set_ylabel("Speed (m/s)")
    ax2.set_xlabel("Time Since Liftoff, TIG (s)")
    ax2.legend(loc="center left", fontsize=8.5)

    save(fig, "lm_02_altitude_velocity")


def plot_pitch_profile(sim: dict) -> None:
    """Plot 2: Pitch profile and linear-tangent commanded acceleration components vs time."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 7.0), sharex=True)
    t = sim["t"]

    # Panel 1: Pitch angle from vertical
    ax1.plot(t, sim["pitch_deg"], color="#1f77b4", lw=2.4, label="Commanded Pitch from Vertical (deg)")
    ax1.axhline(90.0, color="#666666", ls=":", lw=1.0, label="Local Horizontal (90 deg)")
    ax1.annotate(
        "Vertical Rise (FLVR = 1)\nuntil RDOT >= 40 ft/s (12.2 m/s)",
        xy=(6.0, 0.0),
        xytext=(28.0, 12.0),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#333333"},
    )
    ax1.annotate(
        "Pitchover (EXITVR)\ninto linear-tangent steering",
        xy=(10.0, sim["pitch_deg"][5]),
        xytext=(48.0, 40.0),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#1f77b4"},
    )
    t_freeze = t[-1] - T3_RATE_FREEZE
    ax1.axvline(t_freeze, color="#ff7f0e", ls="--", lw=1.2, label="Rate Freeze at TGO = T3 (10 s)")
    ax1.set_ylabel("Pitch Angle from Vertical (deg)")
    ax1.set_title("Apollo 11 Ascent Guidance (ASCENT_GUIDANCE.agc): Pitch & Acceleration Profile")
    ax1.legend(loc="lower right", fontsize=8.5)

    # Panel 2: Commanded thrust accelerations (AT, ATP downrange, ATR radial)
    ax2.plot(t, sim["at_mag"], color="#333333", lw=2.0, label="Total Thrust Accel AT = VE / TBUP (m/s^2)")
    ax2.plot(t, sim["atp"], color="#d62728", lw=2.1, label="Downrange Accel ATP (m/s^2)")
    ax2.plot(t, sim["atr"], color="#2ca02c", lw=2.1, label="Radial Accel ATR = (A + B*dt)/TBUP - GEFF (m/s^2)")
    ax2.axhline(0.0, color="#666666", lw=0.8)
    ax2.axvline(t_freeze, color="#ff7f0e", ls="--", lw=1.2)
    ax2.set_ylabel("Acceleration (m/s^2)")
    ax2.set_xlabel("Time Since Liftoff, TIG (s)")
    ax2.legend(loc="upper left", fontsize=8.5)

    save(fig, "lm_02_pitch_profile")


def main() -> None:
    """Narrate and simulate the Apollo 11 Lunar Module powered ascent (P12)."""
    step(
        1,
        "P12 Initialization & Injection Targets (P12LM -> P12INIT -> COMMINIT)",
        f"Source: {src('Luminary099/P12.agc', 'P12LM')} & "
        f"{src('Luminary099/P12.agc', 'P12INIT')}\n"
        "COMMINIT sets cutoff radius RCO = /LAND/ + HINJECT (h = 18,288 m = 60,000 ft).\n"
        "P12LMB loads nominal radial rate RDOTD = 5.94 m/s (19.5 ft/s) and horizontal\n"
        "velocity ZDOTD (VINJNOM = 1679.2 m/s for 30 NM apolune, updated via V06N76 to\n"
        f"{VINJ_83KM:.2f} m/s for the ~17 x 83 km coelliptic staging orbit).",
    )

    sim = simulate_ascent_p12()

    step(
        2,
        "Vertical Rise & Pitchover (CHECKALT -> CHECKYAW -> EXITVR)",
        f"Source: {src('Luminary099/ASCENT_GUIDANCE.agc', 'CHECKALT')} & "
        f"{src('Luminary099/ASCENT_GUIDANCE.agc', 'EXITVR')}\n"
        "At liftoff, FLVR = 1 forces UNFC/2 = UNIT/R/ so the Ascent Stage rises straight up\n"
        "to clear the descent stage. Once radial rate RDOT reaches 40 ft/s (12.2 m/s, 40FPS),\n"
        "EXITVR clears FLVR and pitches the LM ~50 deg forward onto the explicit guidance arc.",
    )

    step(
        3,
        "ATMAG Mass Filter & Explicit Linear-Tangent Steering (ATMAG -> ASCENT -> MAINENG -> RATES)",
        f"Source: {src('Luminary099/ASCENT_GUIDANCE.agc', 'ATMAG')} & "
        f"{src('Luminary099/ASCENT_GUIDANCE.agc', 'ASCENT')}\n"
        "Unlike the DPS, the Ascent Propulsion System (3,500 lbf) is not throttleable.\n"
        "ATMAG smooths 4 samples of 1/DV to track burn-up time TBUP = m/mdot and AT = VE/TBUP.\n"
        "MAINENG computes TGO = TBUP*(VG/VE)*(1 - 0.5*VG/VE) - TTO, calls LOGSUB for\n"
        "L = ln(1 - TGO/TBUP), and solves RATES/CONST for radial acceleration ATR = (A + B*t)/TBUP - GEFF.",
    )

    step(
        4,
        f"Rate Freeze at TGO < 10 s & Engine Cutoff at t = {sim['t'][-1]:.1f} s (ENGOFF -> CUTOFF)",
        f"Source: {src('Luminary099/ASCENT_GUIDANCE.agc', 'ENGOFF')} & "
        f"{src('Luminary099/ASCENT_GUIDANCE.agc', 'CUTOFF')}\n"
        "At TGO < T3 (10 s), NORATES freezes PRATE (B = 0) and YRATE (D = 0) to prevent\n"
        "terminal attitude whip-sawing; at TGO < 4 s, ENGOFF schedules the waitlist timer\n"
        f"ENGOFF1 to shut off the APS at h = {sim['alt_km'][-1]:.2f} km, RDOT = {sim['r_dot'][-1]:.2f} m/s, "
        f"ZDOT = {sim['z_dot'][-1]:.2f} m/s,\n"
        f"achieving a {sim['perilune_km']:.1f} km x {sim['apolune_km']:.1f} km lunar orbit.",
    )

    plot_altitude_velocity(sim)
    plot_pitch_profile(sim)


if __name__ == "__main__":
    main()
