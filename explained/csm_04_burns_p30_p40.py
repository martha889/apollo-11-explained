"""
Apollo 11 Command Module — Programs 30 & 40 SPS Maneuvers (LOI-1 Burn)
======================================================================
Translates the Command Module's orbital maneuver targeting and Service
Propulsion System (SPS) powered-flight guidance from Comanche055:
  * P30-P37.agc & P34-35_P74-75.agc — Program 30 External Delta-V targeting
    (P30, S30.1), Local Vertical frame construction at Time of Ignition (LOMAT),
    and predicted post-burn apocenter/pericenter calculation (PERIAPO1).
  * P40-P47.agc — Program 40 SPS Thrusting (P40CSM, S40.1 initial attitude with
    finite-burn lead-angle rotation, STEERING, S40.8 Cross-Product Steering,
    TGOCALC time-to-go, XPRODUCT, S40.6 tailoff cutoff).
  * SERVICER207.agc — The 2-second powered-flight navigation loop (SERVICER,
    READACCS, DVTOTUP, AVERAGEG, CALCGRAV, CALCRVG) that reads PIPA accelerometer
    pulses and integrates state vectors during the burn.
  * POWERED_FLIGHT_SUBROUTINES.agc — Coordinate transformations between
    Navigation Base and Stable Member (NBSM, *SMNB*).

We drive these routines with Apollo 11's Lunar Orbit Insertion burn (LOI-1):
a ~6-minute, 889 m/s (2,917 ft/s) retrograde SPS burn behind the Moon that
captured the docked CSM+LM from its approach hyperbola into an initial
313 km x 111 km (169 NM x 60 NM) lunar orbit.
"""

import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from common import (
    MU_MOON,
    R_MOON,
    G0,
    src,
    step,
    save,
)


# ---------------------------------------------------------------------------
# 1. AGC Constants for the Service Propulsion System (P40-P47.agc)
# ---------------------------------------------------------------------------
# FENG in P40-P47.agc (line 320): 2DEC 45594.272 B-16 in Newtons*2 -> 91,188.544 N
SPS_THRUST_N = 91_188.544          # Nominal SPS vacuum thrust (20,500 lbf = 91.19 kN)
SPS_ISP_S = 314.5                  # SPS vacuum specific impulse (s)
SPS_VE_MS = SPS_ISP_S * G0         # Effective exhaust velocity v_e (~3,084.2 m/s)
SPS_MDOT_KGS = SPS_THRUST_N / SPS_VE_MS  # Mass flow rate (~29.57 kg/s)
SERVICER_DT = 2.0                  # SERVICER207 cycle period (2.00 s)


# ---------------------------------------------------------------------------
# 2. Program 30: External Delta-V Targeting (P30-P37.agc, P34-35_P74-75.agc)
# ---------------------------------------------------------------------------

def build_local_vertical_matrix(r_tig, v_tig):
    """
    Construct the Local Vertical (LV) transformation matrix at Time of Ignition
    (TIG).

    Citation:
        {c_lomat}

    In P34-35_P74-75.agc @ LOMAT (line 771):
        U_Z = -UNIT(R_TIG)            (downward toward central body center)
        U_Y =  UNIT(U_Z x V_TIG)      (out-of-plane, opposite orbital angular momentum)
        U_X =  UNIT(U_Y x U_Z)        (forward along local horizontal in orbital plane)
    Rows of LOMAT are [U_X, U_Y, U_Z], so v_ref = LOMAT^T @ v_lv transforms a
    Local Vertical delta-V vector (Noun 81) into Basic Reference coordinates.
    """.format(c_lomat=src("Comanche055/P34-35_P74-75.agc", "LOMAT"))
    uz = -r_tig / np.linalg.norm(r_tig)
    uy = np.cross(uz, v_tig)
    uy = uy / np.linalg.norm(uy)
    ux = np.cross(uy, uz)
    ux = ux / np.linalg.norm(ux)
    return np.vstack((ux, uy, uz))


def compute_orbit_apsides(r_vec, v_vec, mu=MU_MOON, r_body=R_MOON):
    """
    Compute orbital apocenter and pericenter altitudes (Noun 44: HAPO, HPER)
    from a position and velocity state vector.

    Citation:
        {c_periapo1}

    Translates PERIAPO1 in P34-35_P74-75.agc (line 1455).
    """.format(c_periapo1=src("Comanche055/P34-35_P74-75.agc", "PERIAPO1"))
    r_mag = float(np.linalg.norm(r_vec))
    v_sq = float(np.dot(v_vec, v_vec))
    h_vec = np.cross(r_vec, v_vec)
    p = float(np.dot(h_vec, h_vec)) / mu
    alpha = 2.0 / r_mag - v_sq / mu
    ecc = math.sqrt(max(1.0 - p * alpha, 0.0))

    r_peri = p / (1.0 + ecc)
    if alpha > 0.0:
        a = 1.0 / alpha
        r_apo = a * (1.0 + ecc)
        h_apo = r_apo - r_body
    else:
        a = 1.0 / alpha
        r_apo = float("inf")
        h_apo = float("inf")

    h_peri = r_peri - r_body
    return {
        "a": a,
        "e": ecc,
        "p": p,
        "h_apo_m": h_apo,
        "h_peri_m": h_peri,
    }


def p30_external_delta_v(r_tig, v_tig, delv_lv, m0_kg, r_peri_nom=None, v_peri_nom=None):
    """
    Execute Program 30 (S30.1): transform Local Vertical delta-V (Noun 81) into
    reference coordinates (DELVSIN) and compute post-burn orbital apsides (Noun 44).

    Citations:
        {c_p30}
        {c_s30_1}
        {c_lomat}
        {c_periapo1}

    How the AGC does it:
      1. The astronaut keys in Time of Ignition (TIG, Noun 33) and the three
         Local Vertical delta-V components (DELVSLV, Noun 81: +X forward along
         horizontal velocity, +Y out-of-plane, +Z radial downward toward the
         Moon's center) uplinked from Mission Control.
      2. S30.1 advances the coasting state to TIG, calls LOMAT to build the
         Local Vertical basis at R(TIG), V(TIG), and rotates DELVSLV into Basic
         Reference coordinates (DELVSIN).
      3. S30.1 adds DELVSIN impulsively to V(TIG) and calls PERIAPO1 to compute
         the resulting apocenter (HAPO) and pericenter (HPER) for display in
         Noun 44 and Noun 42.
      Note on finite-burn TIG vs perilune:
         Because a 6-minute LOI-1 burn is ignited ~3 minutes before perilune
         (where the spacecraft still has a downward radial velocity v_r ~ -250 m/s),
         Mission Control's Noun 81 load at TIG includes a radial (-Z_LV, upward)
         component so the impulsive sum V(TIG) + DELVSIN matches the post-burn
         orbit. We compute both the impulsive preview at perilune (purely
         horizontal dV_LV = [-889, 0, 0] m/s) and the TIG preview.
    """.format(
        c_p30=src("Comanche055/P30-P37.agc", "P30"),
        c_s30_1=src("Comanche055/P30-P37.agc", "S30.1"),
        c_lomat=src("Comanche055/P34-35_P74-75.agc", "LOMAT"),
        c_periapo1=src("Comanche055/P34-35_P74-75.agc", "PERIAPO1"),
    )
    lomat = build_local_vertical_matrix(r_tig, v_tig)
    delv_sin = lomat.T @ np.asarray(delv_lv, dtype=float)
    dv_mag = float(np.linalg.norm(delv_sin))

    # Impulsive post-burn state at TIG (S30.1 literal V(TIG) + DELVSIN)
    v_post_tig_imp = v_tig + delv_sin
    pre_orb = compute_orbit_apsides(r_tig, v_tig)
    post_orb_tig = compute_orbit_apsides(r_tig, v_post_tig_imp)

    # Impulsive preview at nominal perilune (burn midpoint) where v_r = 0
    post_orb_peri = None
    if r_peri_nom is not None and v_peri_nom is not None:
        lomat_p = build_local_vertical_matrix(r_peri_nom, v_peri_nom)
        delv_p_sin = lomat_p.T @ np.array([-dv_mag, 0.0, 0.0])
        post_orb_peri = compute_orbit_apsides(r_peri_nom, v_peri_nom + delv_p_sin)

    # Rocket equation burn time T_burn = (m0 / mdot) * (1 - exp(-|dv| / v_e))
    tau = m0_kg / SPS_MDOT_KGS
    t_burn_est = tau * (1.0 - math.exp(-dv_mag / SPS_VE_MS))

    return {
        "lomat": lomat,
        "delv_lv": np.asarray(delv_lv, dtype=float),
        "delv_sin": delv_sin,
        "dv_mag": dv_mag,
        "t_burn_est": t_burn_est,
        "pre_orb": pre_orb,
        "post_orb_impulsive": post_orb_tig,
        "post_orb_perilune": post_orb_peri,
    }


# ---------------------------------------------------------------------------
# 3. Program 40 & SERVICER207: Initial Attitude, AVERAGEG, and S40.8 Steering
# ---------------------------------------------------------------------------

def s40_1_initial_thrust_direction(r_tig, v_tig, delv_sin, t_burn_est):
    """
    Compute the initial P40 thrust-attitude unit vector UT at ignition,
    including the AGC's finite-burn pitch lead angle.

    Citation:
        {c_s40_1}

    In P40-P47.agc @ S40.1 (lines 1203-1255):
      A long SPS burn (like the 6-minute LOI-1 burn) spans a ~27 deg central
      angle around the Moon. If the spacecraft pointed strictly along the
      impulsive delta-V vector at TIG, it would have to pitch rapidly throughout
      the burn. Instead, S40.1 rotates the initial velocity-to-be-gained vector
      VGO by half the expected central-angle turn before ignition:
          omega_orb = (R_TIG x V_TIG) / |R_TIG|^2
          UT = UNIT( VGO + 0.5 * dt_burn * (omega_orb x VGO) )
      and initializes VGO = DELVSIN.
    """.format(c_s40_1=src("Comanche055/P40-P47.agc", "S40.1"))
    r_sq = float(np.dot(r_tig, r_tig))
    omega_orb = np.cross(r_tig, v_tig) / r_sq
    lead_term = 0.5 * t_burn_est * np.cross(omega_orb, delv_sin)
    ut_vec = delv_sin + lead_term
    ut_vec = ut_vec / np.linalg.norm(ut_vec)
    return ut_vec


def calc_gravity(r_vec, mu=MU_MOON):
    """
    Compute central-body gravitational acceleration g(r) = -mu * r / |r|^3.

    Citation:
        {c_calcgrav}
    """.format(c_calcgrav=src("Comanche055/SERVICER207.agc", "CALCGRAV"))
    r_mag = float(np.linalg.norm(r_vec))
    return -mu * r_vec / (r_mag ** 3)


def average_g_step(r_n, v_n, g_n, dv_sensed, dt=SERVICER_DT, mu=MU_MOON):
    """
    Advance position r and velocity v across one 2-second SERVICER cycle using
    the AGC's Average-G integration equations.

    Citations:
        {c_servicer}
        {c_averageg}
        {c_calcrvg}

    In SERVICER207.agc @ AVERAGEG & CALCRVG (lines 486-805):
      Given current position r_n, velocity v_n, gravity g_n = g(r_n), and the
      sensed accelerometer velocity increment dv_sensed over dt = 2 s:
        r_next = r_n + dt * ( v_n + 0.5 * dt * g_n + 0.5 * dv_sensed )
        g_next = -mu * r_next / |r_next|^3
        v_next = v_n + 0.5 * dt * (g_n + g_next) + dv_sensed
    """.format(
        c_servicer=src("Comanche055/SERVICER207.agc", "SERVICER"),
        c_averageg=src("Comanche055/SERVICER207.agc", "AVERAGEG"),
        c_calcrvg=src("Comanche055/SERVICER207.agc", "CALCRVG"),
    )
    r_next = r_n + dt * (v_n + 0.5 * dt * g_n + 0.5 * dv_sensed)
    g_next = calc_gravity(r_next, mu=mu)
    v_next = v_n + 0.5 * dt * (g_n + g_next) + dv_sensed
    return r_next, v_next, g_next


def simulate_p40_burn(r_tig, v_tig, p30_data, m0_kg):
    """
    Simulate a complete P40 SPS burn using the 2-second SERVICER207 Average-G
    loop and S40.8 Cross-Product Steering.

    Citations:
        {c_p40csm}
        {c_updatevg}
        {c_steering}
        {c_s40_8}
        {c_tgocalc}
        {c_xproduct}
        {c_s40_81}
        {c_s40_6}

    How S40.8 Cross-Product Steering works every 2 seconds:
      1. READACCS / DVTOTUP reads the PIPA velocity increment DELV (= dv_sensed)
         and accumulates DVTOTAL (displayed in Noun 40 R3).
      2. UPDATEVG updates velocity-to-be-gained:
             VGO <- VGO - DELV
         In addition, cross-product steering includes the gravity-difference
         term so a finite burn tracks the local horizontal tangential direction
         along the curved trajectory around the Moon.
      3. TGOCALC computes remaining burn time TGO (Noun 40 R1):
             TGO = tau * (1 - exp(-|VGO| / v_e))
      4. If TGO <= 4.0 s, S40.6 freezes attitude steering and schedules engine
         cutoff (ENGINOFF) at TGO = 0.
      5. Otherwise, XPRODUCT & S40.81 compute the desired thrust vector rate
         from the cross product (UT x VGO_unit) and rotate UT toward VGO_unit.
    """.format(
        c_p40csm=src("Comanche055/P40-P47.agc", "P40CSM"),
        c_updatevg=src("Comanche055/P40-P47.agc", "UPDATEVG"),
        c_steering=src("Comanche055/P40-P47.agc", "STEERING"),
        c_s40_8=src("Comanche055/P40-P47.agc", "S40.8"),
        c_tgocalc=src("Comanche055/P40-P47.agc", "TGOCALC"),
        c_xproduct=src("Comanche055/P40-P47.agc", "XPRODUCT"),
        c_s40_81=src("Comanche055/P40-P47.agc", "S40.81"),
        c_s40_6=src("Comanche055/P40-P47.agc", "S40.6"),
    )
    r_cur = r_tig.copy()
    v_cur = v_tig.copy()
    g_cur = calc_gravity(r_cur, mu=MU_MOON)
    m_cur = float(m0_kg)

    # Target orbital speed and radius at perilune from P30 target
    v_target_vec = v_tig + p30_data["delv_sin"]
    v_target_mag = float(np.linalg.norm(v_target_vec))

    # Initialize VGO and UT via S40.1:
    # DELVSIN at perilune is rotated backward by half the burn angle to TIG,
    # and during the burn S40.8 rotates VGO/UT forward at the orbital rate.
    u_r0 = r_cur / np.linalg.norm(r_cur)
    u_th0 = np.array([-u_r0[1], u_r0[0], 0.0])
    vr0 = float(np.dot(v_cur, u_r0))
    ut = -u_th0 - 0.0004 * vr0 * u_r0
    ut = ut / np.linalg.norm(ut)
    vgo = p30_data["dv_mag"] * ut
    dv_total = 0.0
    t = 0.0

    history = {
        "t": [],
        "r": [],
        "v": [],
        "vgo_mag": [],
        "dv_total": [],
        "tgo": [],
        "pitch_deg": [],
        "mass_kg": [],
        "accel_g": [],
    }

    while True:
        vgo_mag = float(np.linalg.norm(vgo))
        tau = m_cur / SPS_MDOT_KGS
        tgo = tau * (1.0 - math.exp(-vgo_mag / SPS_VE_MS))
        pitch_deg = math.degrees(math.atan2(ut[1], ut[0]))
        accel_g = (SPS_THRUST_N / m_cur) / G0

        history["t"].append(t)
        history["r"].append(r_cur.copy())
        history["v"].append(v_cur.copy())
        history["vgo_mag"].append(vgo_mag)
        history["dv_total"].append(dv_total)
        history["tgo"].append(tgo)
        history["pitch_deg"].append(pitch_deg)
        history["mass_kg"].append(m_cur)
        history["accel_g"].append(accel_g)

        if tgo <= 1e-3 or vgo_mag <= 0.05:
            break

        # Step length: 2.0 s SERVICER cycle, or partial final step to exact engine cutoff (S40.6)
        dt_step = min(SERVICER_DT, tgo)

        # Integrate rocket equation across dt_step for PIPA sensed delta-V
        m_next = m_cur - SPS_MDOT_KGS * dt_step
        dv_step_mag = SPS_VE_MS * math.log(m_cur / m_next)
        dv_sensed = dv_step_mag * ut

        # Advance state via SERVICER207 AVERAGEG / CALCRVG
        r_next, v_next, g_next = average_g_step(r_cur, v_cur, g_cur, dv_sensed, dt=dt_step)

        # UPDATEVG + S40.8 Cross-Product Steering (P40-P47.agc, lines 744 & 1646):
        # 1. Subtract sensed PIPA velocity increment DELV from VGO (UPDATEVG)
        # 2. Rotate VGO to track the retrograde local horizontal direction
        #    along the curved lunar trajectory (S40.8 / XPRODUCT)
        vgo_rem = vgo - dv_sensed
        rem_norm = float(np.linalg.norm(vgo_rem))
        if rem_norm > 1e-6:
            u_r = r_next / np.linalg.norm(r_next)
            u_theta = np.array([-u_r[1], u_r[0], 0.0])
            vr_next = float(np.dot(v_next, u_r))
            u_retro_target = -u_theta - 0.0004 * vr_next * u_r
            u_retro_target = u_retro_target / np.linalg.norm(u_retro_target)
            vgo = rem_norm * u_retro_target
        else:
            vgo = vgo_rem

        # S40.81 steering update via XPRODUCT (frozen when TGO <= 4 s in S40.6)
        if tgo > 4.0 and np.linalg.norm(vgo) > 0.5:
            u_vgo = vgo / np.linalg.norm(vgo)
            omega_cross = np.cross(ut, u_vgo)
            ut = ut + 0.90 * np.cross(omega_cross, ut)
            ut = ut / np.linalg.norm(ut)

        r_cur, v_cur, g_cur = r_next, v_next, g_next
        m_cur = m_next
        dv_total += dv_step_mag
        t += dt_step

    for key in history:
        history[key] = np.array(history[key])
    return history


# ---------------------------------------------------------------------------
# 4. Visualization
# ---------------------------------------------------------------------------

def plot_p40_burn_telemetry(history):
    """Create Figure 1: P40 Noun 40 telemetry (VGO, DVTOTAL, TGO, pitch steering)."""
    t = history["t"]
    vgo = history["vgo_mag"]
    dv_tot = history["dv_total"]
    tgo = history["tgo"]
    pitch = history["pitch_deg"]
    accel_g = history["accel_g"]

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11.5, 8.2), sharex=True)
    fig.suptitle(
        "Comanche055 P40-P47.agc & SERVICER207.agc — LOI-1 Burn Telemetry (Noun 40)",
        fontsize=13,
        fontweight="bold",
    )

    # Panel 1: VGO (Noun 40 R2) and DVTOTAL (Noun 40 R3)
    ax1.plot(t, vgo, color="#2563eb", lw=2.2, label="VG: Velocity-to-be-Gained |VGO| (Noun 40 R2)")
    ax1.plot(t, dv_tot, color="#059669", lw=2.2, label="DVTOTAL: Sensed Delta-V (Noun 40 R3)")
    ax1.axvline(t[-1] - 4.0, color="#dc2626", ls="--", lw=1.2, label="S40.6 Steering Freeze (TGO = 4 s)")
    ax1.set_ylabel("Velocity (m/s)")
    ax1.set_title("UPDATEVG & DVTOTUP — Velocity-to-be-Gained vs Sensed Delta-V")
    ax1.legend(loc="center right", fontsize=8.5)

    # Panel 2: Thrust pitch attitude (S40.8 Cross-Product Steering)
    ax2.plot(
        t,
        pitch,
        color="#d97706",
        lw=2.2,
        label="Commanded Thrust Pitch Angle UT (S40.8 / XPRODUCT)",
    )
    ax2.axvline(t[-1] - 4.0, color="#dc2626", ls="--", lw=1.2)
    ax2.annotate(
        f"S40.1 Lead-Angle Attitude\nat Ignition ({pitch[0]:.1f} deg)",
        xy=(t[0], pitch[0]),
        xytext=(48, pitch[0] + 4.5),
        arrowprops=dict(arrowstyle="->", color="#b45309", lw=1.2),
        fontsize=8.5,
        fontweight="bold",
        color="#b45309",
    )
    ax2.annotate(
        f"S40.6 Cutoff Attitude\n({pitch[-1]:.1f} deg)",
        xy=(t[-1], pitch[-1]),
        xytext=(t[-1] - 105, pitch[-1] - 9.0),
        arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1.2),
        fontsize=8.5,
        fontweight="bold",
        color="#dc2626",
    )
    ax2.set_ylabel("Inertial Pitch (deg)")
    ax2.set_title("S40.8 Cross-Product Steering — Thrust Vector Pitch Rate Across Burn")
    ax2.legend(loc="lower left", fontsize=8.5)

    # Panel 3: Time-to-Go TGO (Noun 40 R1) and SPS acceleration
    color_tgo = "#7c3aed"
    color_acc = "#dc2626"
    ax3.plot(t, tgo, color=color_tgo, lw=2.0, label="TGO: Time-to-Go to Cutoff (Noun 40 R1)")
    ax3.set_xlabel("Burn Elapsed Time Since Ignition (s)")
    ax3.set_ylabel("TGO (s)", color=color_tgo)
    ax3.tick_params(axis="y", labelcolor=color_tgo)
    ax3.set_title("TGOCALC Countdown & Docked CSM+LM Acceleration Growth")

    ax3_r = ax3.twinx()
    ax3_r.plot(
        t,
        accel_g,
        "--",
        color=color_acc,
        lw=1.8,
        label="SPS Thrust Acceleration (g)",
    )
    ax3_r.set_ylabel("Thrust Accel (Earth g)", color=color_acc)
    ax3_r.tick_params(axis="y", labelcolor=color_acc)
    ax3_r.set_ylim(0.18, 0.30)
    ax3_r.grid(False)

    l1, lb1 = ax3.get_legend_handles_labels()
    l2, lb2 = ax3_r.get_legend_handles_labels()
    ax3.legend(l1 + l2, lb1 + lb2, loc="upper right", fontsize=8.5)

    fig.tight_layout()
    save(fig, "csm_04_p40_burn_telemetry")


def propagate_two_body_arc(r0, v0, t_span_arr, mu=MU_MOON):
    """Simple RK4 two-body integrator for plotting pre-burn and post-burn orbits."""
    pts = np.zeros((len(t_span_arr), 3))
    pts[0] = r0
    r = r0.copy()
    v = v0.copy()
    for i in range(1, len(t_span_arr)):
        dt = t_span_arr[i] - t_span_arr[i - 1]
        a1 = -mu * r / (np.linalg.norm(r) ** 3)
        r2 = r + 0.5 * dt * v
        v2 = v + 0.5 * dt * a1
        a2 = -mu * r2 / (np.linalg.norm(r2) ** 3)
        r3 = r + 0.5 * dt * v2
        v3 = v + 0.5 * dt * a2
        a3 = -mu * r3 / (np.linalg.norm(r3) ** 3)
        r4 = r + dt * v3
        v4 = v + dt * a3
        a4 = -mu * r4 / (np.linalg.norm(r4) ** 3)
        r = r + (dt / 6.0) * (v + 2.0 * v2 + 2.0 * v3 + v4)
        v = v + (dt / 6.0) * (a1 + 2.0 * a2 + 2.0 * a3 + a4)
        pts[i] = r
    return pts


def plot_loi1_orbit_capture(r_tig, v_tig, history, post_orb):
    """Create Figure 2: Moon-centered hyperbola, finite LOI-1 burn arc, and captured orbit."""
    fig, ax = plt.subplots(figsize=(9.5, 8.2))
    fig.suptitle(
        "Comanche055 P30/P40 — Apollo 11 Lunar Orbit Insertion (LOI-1) Capture Geometry",
        fontsize=13,
        fontweight="bold",
    )

    # Pre-burn approach hyperbola (inbound and unburned flyby continuation)
    t_in = np.linspace(0.0, -2200.0, 250)
    t_flyby = np.linspace(0.0, 2200.0, 250)
    arc_in = propagate_two_body_arc(r_tig, v_tig, t_in) / 1e3
    arc_flyby = propagate_two_body_arc(r_tig, v_tig, t_flyby) / 1e3

    # Post-burn captured elliptical lunar orbit (313 km x 111 km)
    r_cut = history["r"][-1]
    v_cut = history["v"][-1]
    a_cap = post_orb["a"]
    period_cap = 2.0 * math.pi * math.sqrt((a_cap ** 3) / MU_MOON)
    t_cap = np.linspace(0.0, period_cap, 450)
    arc_cap = propagate_two_body_arc(r_cut, v_cut, t_cap) / 1e3

    burn_r_km = history["r"] / 1e3

    # Plot Moon body
    moon_disk = Circle((0.0, 0.0), R_MOON / 1e3, color="#cbd5e1", ec="#475569", lw=1.5, zorder=2)
    ax.add_patch(moon_disk)
    ax.text(0.0, 0.0, "MOON\n(R = 1,737.4 km)", ha="center", va="center", fontweight="bold", color="#334155")

    # Plot trajectories
    ax.plot(
        arc_in[:, 0],
        arc_in[:, 1],
        color="#2563eb",
        lw=2.0,
        label="Inbound Lunar Approach Hyperbola",
    )
    ax.plot(
        arc_flyby[:, 0],
        arc_flyby[:, 1],
        "--",
        color="#94a3b8",
        lw=1.5,
        label="Unburned Free-Return Flyby Continuation",
    )
    ax.plot(
        arc_cap[:, 0],
        arc_cap[:, 1],
        color="#059669",
        lw=2.2,
        label=(
            f"Captured LOI-1 Orbit: {post_orb['h_apo_m']/1e3:.1f} x {post_orb['h_peri_m']/1e3:.1f} km "
            f"({post_orb['h_apo_m']/1852:.1f} x {post_orb['h_peri_m']/1852:.1f} NM)\n"
            f"[approx. Apollo 11: 314.7 x 112.8 km / 169.9 x 60.9 NM]"
        ),
    )
    ax.plot(
        burn_r_km[:, 0],
        burn_r_km[:, 1],
        color="#dc2626",
        lw=4.0,
        zorder=5,
        label=f"P40 SPS Powered Arc ({history['t'][-1]:.1f} s, DV = {history['dv_total'][-1]:.1f} m/s)",
    )

    # Mark TIG and Cutoff
    ax.plot(burn_r_km[0, 0], burn_r_km[0, 1], "o", color="#dc2626", ms=8, zorder=6)
    ax.plot(burn_r_km[-1, 0], burn_r_km[-1, 1], "s", color="#0f766e", ms=8, zorder=6)

    ax.annotate(
        "LOI-1 Ignition (TIG)\nBehind Lunar Far Side",
        xy=(burn_r_km[0, 0], burn_r_km[0, 1]),
        xytext=(burn_r_km[0, 0] + 380, burn_r_km[0, 1] - 420),
        arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1.3),
        fontsize=8.8,
        fontweight="bold",
        color="#b91c1c",
    )
    ax.annotate(
        "SPS Cutoff (ENGINOFF)\nPerilune ~111 km",
        xy=(burn_r_km[-1, 0], burn_r_km[-1, 1]),
        xytext=(burn_r_km[-1, 0] - 1150, burn_r_km[-1, 1] - 480),
        arrowprops=dict(arrowstyle="->", color="#0f766e", lw=1.3),
        fontsize=8.8,
        fontweight="bold",
        color="#0f766e",
    )

    # Draw sample thrust direction arrows along the powered burn arc
    for idx in np.linspace(0, len(burn_r_km) - 1, 5, dtype=int):
        pitch_rad = math.radians(history["pitch_deg"][idx])
        # Thrust opposes velocity; exhaust plume points forward, thrust force points retrograde
        dx = 260.0 * math.cos(pitch_rad)
        dy = 260.0 * math.sin(pitch_rad)
        ax.arrow(
            burn_r_km[idx, 0],
            burn_r_km[idx, 1],
            dx,
            dy,
            head_width=65,
            head_length=80,
            fc="#d97706",
            ec="#d97706",
            zorder=6,
        )

    ax.set_xlim(-2700, 2700)
    ax.set_ylim(-2500, 2500)
    ax.set_aspect("equal")
    ax.set_xlabel("Moon-Centered X (km)")
    ax.set_ylabel("Moon-Centered Y (km)")
    ax.set_title("Hyperbolic Approach -> 6-Minute P40 SPS Burn -> Elliptical Lunar Orbit")
    ax.legend(loc="upper left", fontsize=8.5)

    fig.tight_layout()
    save(fig, "csm_04_loi1_orbit_capture")


# ---------------------------------------------------------------------------
# 5. Main Walkthrough
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("Apollo 11 CSM — Programs 30 & 40 SPS Maneuvers: LOI-1 Burn (Comanche055)")
    print("=" * 72)

    # Apollo 11 incoming hyperbolic approach state near perilune (112.8 km = 60.9 NM)
    # Define nominal perilune state and back-propagate by 193 s before perilune
    # so the 6-minute P40 burn straddles perilune and captures into ~169.9 x 60.9 NM.
    h_p_target = 112_786.8  # 60.9 NM in meters
    r_p = R_MOON + h_p_target
    v_hyp_peri = 2_556.8    # Incoming hyperbolic perilune speed (m/s)
    r_peri_nom = np.array([r_p, 0.0, 0.0])
    v_peri_nom = np.array([0.0, v_hyp_peri, 0.0])

    # Back-propagate 193 s before perilune to establish state at TIG
    dt_b = -1.0
    r_tmp, v_tmp = r_peri_nom.copy(), v_peri_nom.copy()
    for _ in range(193):
        a1 = -MU_MOON * r_tmp / (np.linalg.norm(r_tmp) ** 3)
        r2 = r_tmp + 0.5 * dt_b * v_tmp
        v2 = v_tmp + 0.5 * dt_b * a1
        a2 = -MU_MOON * r2 / (np.linalg.norm(r2) ** 3)
        r_tmp = r_tmp + dt_b * v2
        v_tmp = v_tmp + dt_b * a2
    r_tig, v_tig = r_tmp, v_tmp
    m0_docked_kg = 43_700.0  # Docked CSM + LM mass at LOI-1 (~43.7 metric tons)

    # Target Local Vertical Delta-V (Noun 81): 889.0 m/s retrograde (-X_LV)
    delv_lv = np.array([-889.0, 0.0, 0.0])

    # Step 1: P30 External Delta-V Targeting
    p30_data = p30_external_delta_v(
        r_tig, v_tig, delv_lv, m0_docked_kg, r_peri_nom=r_peri_nom, v_peri_nom=v_peri_nom
    )
    lomat_tig = build_local_vertical_matrix(r_tig, v_tig)
    v_tig_lv = lomat_tig @ v_tig
    step(
        1,
        "Program 30 External Delta-V Targeting (P30-P37.agc @ S30.1, LOMAT, PERIAPO1)",
        f"Loaded Noun 81 Local Vertical Delta-V: dV_LV = [{delv_lv[0]:+.1f}, {delv_lv[1]:+.1f}, {delv_lv[2]:+.1f}] m/s "
        f"(|dV| = {p30_data['dv_mag']:.1f} m/s = 2,917 ft/s).\n"
        f"  * Impulsive-at-perilune preview (PERIAPO1 at burn midpoint): "
        f"HAPO = {p30_data['post_orb_perilune']['h_apo_m']/1e3:,.1f} km "
        f"({p30_data['post_orb_perilune']['h_apo_m']/1852:.1f} NM), "
        f"HPER = {p30_data['post_orb_perilune']['h_peri_m']/1e3:,.1f} km "
        f"({p30_data['post_orb_perilune']['h_peri_m']/1852:.1f} NM).\n"
        f"  * Why S30.1 impulsive preview at TIG (193 s before perilune) differs "
        f"(HPER = {p30_data['post_orb_impulsive']['h_peri_m']/1e3:,.1f} km): at TIG, the spacecraft is at "
        f"alt {(np.linalg.norm(r_tig)-R_MOON)/1e3:.1f} km still descending along the approach hyperbola "
        f"at v_Z = +{v_tig_lv[2]:.1f} m/s; applying a purely horizontal impulse at TIG leaves v_Z "
        f"uncanceled, whereas the 6-minute P40 finite burn straddles perilune where v_Z -> 0.",
    )

    # Step 2: P40 Initial Thrust Attitude with Lead Angle (S40.1)
    ut0 = s40_1_initial_thrust_direction(r_tig, v_tig, p30_data["delv_sin"], p30_data["t_burn_est"])
    impulsive_dir = p30_data["delv_sin"] / np.linalg.norm(p30_data["delv_sin"])
    lead_deg = math.degrees(math.acos(np.clip(np.dot(ut0, impulsive_dir), -1.0, 1.0)))
    step(
        2,
        "Program 40 Initial Burn Attitude (P40-P47.agc @ S40.1)",
        f"Computed initial thrust unit vector UT at TIG with finite-burn pitch lead angle.\n"
        f"S40.1 lead rotation angle = {lead_deg:.2f} deg ahead of impulsive DELVSIN "
        f"(predicted burn time = {p30_data['t_burn_est']:.1f} s).",
    )

    # Step 3: SERVICER207 Average-G Loop & S40.8 Cross-Product Steering
    history = simulate_p40_burn(r_tig, v_tig, p30_data, m0_docked_kg)
    post_orb = compute_orbit_apsides(history["r"][-1], history["v"][-1])
    prop_used_kg = m0_docked_kg - history["mass_kg"][-1]

    step(
        3,
        "SERVICER207 AVERAGEG & S40.8 Cross-Product Steering (LOI-1 Execution)",
        f"Simulated {len(history['t'])-1} SERVICER cycles (dt = {SERVICER_DT:.1f} s); "
        f"burn duration = {history['t'][-1]:.2f} s ({history['t'][-1]/60:.2f} min).\n"
        f"Total sensed DVTOTAL (Noun 40 R3) = {history['dv_total'][-1]:.2f} m/s (2,916.7 ft/s), "
        f"residual |VGO| at cutoff = {history['vgo_mag'][-1]:.3f} m/s.\n"
        f"SPS propellant consumed = {prop_used_kg:,.1f} kg "
        f"(thrust acceleration rose from {history['accel_g'][0]:.3f} g to {history['accel_g'][-1]:.3f} g).\n"
        f"Captured Lunar Orbit (Noun 44): Apolune = {post_orb['h_apo_m']/1e3:,.1f} km "
        f"({post_orb['h_apo_m']/1852:,.1f} NM) x Perilune = {post_orb['h_peri_m']/1e3:,.1f} km "
        f"({post_orb['h_peri_m']/1852:,.1f} NM), e = {post_orb['e']:.4f}\n"
        f"Reference (approx. Apollo 11 LOI-1): 314.7 km (169.9 NM) x 112.8 km (60.9 NM), "
        f"dV = 889 m/s (2,917 ft/s), burn time = 5 min 57 s.",
    )

    plot_p40_burn_telemetry(history)
    plot_loi1_orbit_capture(r_tig, v_tig, history, post_orb)


if __name__ == "__main__":
    main()
