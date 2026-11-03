"""Command Module Phase 1: P11 Earth Orbit Insertion Monitor (Saturn V Launch).

During the Saturn V launch, the Saturn Instrument Unit (IU) in the S-IVB stage
steered the booster while the Command Module Computer (CMC) ran Program 11 (P11)
to monitor the trajectory, compute Noun 62 (inertial velocity, altitude rate,
altitude above the pad) every 2 seconds, and drive the FDAI attitude-error
needles against a preloaded pitch/roll polynomial so the crew could verify
booster performance (or take over manual stick control if the IU failed).

Original AGC sources:
  * Comanche055/P11.agc (P11, MATRXJOB, VHHDOT, S11.1, ATERJOB, ATTDISP, SATSTICK)
  * Comanche055/SERVICER207.agc (PREREAD1, READACCS, SERVICER, AVERAGEG, CALCRVG)
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from common import G0, MU_EARTH, R_EARTH, save, src, step

# ---------------------------------------------------------------------------
# Constants from Comanche055/P11.agc and Comanche055/P34-35_P74-75.agc
# ---------------------------------------------------------------------------
# Earth sidereal rotation rate (-ERTHRAT in P11.agc: -7.292115138 E-7 rad/cs)
OMEGA_EARTH = 7.292115138e-5  # rad/s
# Standard launch pad radius (RPAD in P34-35_P74-75.agc: 6,373,338 m)
R_PAD = 6_373_338.0  # m
# Earth J2 oblateness coefficient used by CALCGRAV in SERVICER207.agc
J2_EARTH = 1.0823e-3

# Unit conversions for DSKY Noun 62 display units
M_PER_S_TO_FPS = 1.0 / 0.3048  # ft/s per m/s
M_TO_NM = 1.0 / 1852.0  # nautical miles per meter

# Pad 39A Kennedy Space Center coordinates & Apollo 11 launch azimuth (approx.)
PAD39A_LAT_DEG = 28.608389
PAD39A_LON_DEG = -80.604333
LAUNCH_AZIMUTH_DEG = 72.0


def initialize_p11_pad_state(
    lat_deg: float = PAD39A_LAT_DEG,
    lon_deg: float = PAD39A_LON_DEG,
    launch_az_deg: float = LAUNCH_AZIMUTH_DEG,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Initialize liftoff state vector (RN1, VN1) and REFSMMAT at Pad 39A.

    Cites:
      * src("Comanche055/P11.agc", "P11")
      * src("Comanche055/P11.agc", "MATRXJOB")

    When the liftoff discrete arrives from the Saturn V (or the crew keys V75E),
    P11 zeroes the CMC mission clock (TIME2/TIME1) and MATRXJOB computes:
      1. RN1: Initial pad position vector in Basic Reference (inertial) coords.
      2. VN1: Initial inertial velocity from Earth's rotation,
         VN1 = OMEGA_EARTH * (UNITW x RN1).
      3. REFSMMAT: Prelaunch Stable Member orientation matrix where
         - Z_SM points along local vertical (downward toward Earth center),
         - X_SM points horizontally along the launch azimuth (72 deg for Apollo 11),
         - Y_SM completes the right-handed triad (Z_SM x X_SM).
    """
    lat = np.radians(lat_deg)
    lon = np.radians(lon_deg)
    az = np.radians(launch_az_deg)

    # Pad position vector RN1 in Earth-centered inertial (ECI) coordinates at t = 0
    rn1 = R_PAD * np.array([
        np.cos(lat) * np.cos(lon),
        np.cos(lat) * np.sin(lon),
        np.sin(lat),
    ])

    # Earth rotation axis unit vector (UNITW)
    unit_w = np.array([0.0, 0.0, 1.0])

    # Initial inertial velocity from Earth's sidereal rotation: V = W x R
    # In P11.agc @ MATRXJOB: RN1 VXV UNITW VXSC -ERTHRAT
    vn1 = -OMEGA_EARTH * np.cross(rn1, unit_w)

    # Construct prelaunch REFSMMAT (rows are X_SM, Y_SM, Z_SM in Reference coords)
    # Z_SM = unit(-RN1) (local vertical pointing down, GETDOWN in P11.agc)
    u_z = -rn1 / np.linalg.norm(rn1)
    # East and North unit vectors in the local horizontal plane
    east = np.cross(u_z, unit_w)
    east /= np.linalg.norm(east)
    south = -np.cross(east, u_z)
    south /= np.linalg.norm(south)
    # X_SM = sin(LAUNCHAZ)*East - cos(LAUNCHAZ)*South (downrange along launch azimuth)
    u_x = np.sin(az) * east - np.cos(az) * south
    u_x /= np.linalg.norm(u_x)
    # Y_SM = Z_SM x X_SM
    u_y = np.cross(u_z, u_x)
    u_y /= np.linalg.norm(u_y)

    refsmmat = np.vstack([u_x, u_y, u_z])
    return rn1, vn1, refsmmat


def compute_gravity_calcrvg(r_vec: np.ndarray) -> np.ndarray:
    """Compute Earth gravitational acceleration including J2 oblateness.

    Cites:
      * src("Comanche055/SERVICER207.agc", "CALCGRAV")

    In the AGC, CALCGRAV computes 0.5 * g * dt (with dt = 2 s, so Numerically
    equal to g in m/s^2 when scaled) including the first zonal harmonic J2:
      g = -mu / r^2 * [ u_r + J2 * (R_E / r)^2 * ((1 - 5*(u_r . u_w)^2)*u_r + 2*(u_r . u_w)*u_w) ]
    """
    r_mag = np.linalg.norm(r_vec)
    u_r = r_vec / r_mag
    u_w = np.array([0.0, 0.0, 1.0])
    cos_lat = float(np.dot(u_r, u_w))

    re_over_r_sq = (R_EARTH / r_mag) ** 2
    oblate_vec = (
        1.5 * J2_EARTH * re_over_r_sq
        * ((1.0 - 5.0 * cos_lat**2) * u_r + 2.0 * cos_lat * u_w)
    )
    return -(MU_EARTH / r_mag**2) * (u_r + oblate_vec)


def average_g_step(
    rn: np.ndarray,
    vn: np.ndarray,
    g_prev: np.ndarray,
    delv_ref: np.ndarray,
    dt: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Advance (RN, VN) by one 2-second AVERAGEG cycle using sensed PIPA delta-V.

    Cites:
      * src("Comanche055/SERVICER207.agc", "AVERAGEG")
      * src("Comanche055/SERVICER207.agc", "CALCRVG")

    Every 2 seconds during powered flight or launch monitoring, READACCS reads
    the PIPA accelerometers (DELV) and CALCRVG updates position and velocity
    using the trapezoidal average of thrust and gravity over the 2 s interval:
      RN1 = RN + dt * (VN + 0.5 * DELVREF + 0.5 * g_prev * dt)
      g_new = CALCGRAV(RN1)
      VN1 = VN + DELVREF + 0.5 * (g_prev + g_new) * dt
    """
    rn1 = rn + dt * (vn + 0.5 * delv_ref + 0.5 * g_prev * dt)
    g_new = compute_gravity_calcrvg(rn1)
    vn1 = vn + delv_ref + 0.5 * (g_prev + g_new) * dt
    return rn1, vn1, g_new


def compute_noun62_s11_1(rn: np.ndarray, vn: np.ndarray) -> dict[str, float]:
    """Compute P11 Noun 62 trajectory parameters (VI, HDOT, H) and flight-path angle.

    Cites:
      * src("Comanche055/P11.agc", "VHHDOT")
      * src("Comanche055/P11.agc", "S11.1")

    At the end of every 2-second AVERAGEG cycle, SERVICER jumps through AVGEXIT
    to VHHDOT, which calls S11.1 and refreshes DSKY Verb 06 Noun 62:
      * R1 (VMAGI): Inertial velocity magnitude |VN| (displayed in ft/s)
      * R2 (HDOT):  Altitude rate (RN / |RN|) . VN (displayed in ft/s)
      * R3 (ALTI):  Altitude above launch pad |RN| - RPAD (displayed in NM)
    From VI and HDOT, the inertial flight-path angle is gamma = arcsin(HDOT / VI).
    """
    v_mag = float(np.linalg.norm(vn))
    r_mag = float(np.linalg.norm(rn))
    u_r = rn / r_mag

    # S11.1: RN UNIT DOT VN SL1 -> HDOT
    h_dot = float(np.dot(u_r, vn))
    # S11.1: |RN| - RPAD -> ALTI
    alt_m = r_mag - R_PAD

    # Flight-path angle above local horizontal: sin(gamma) = h_dot / v_mag
    sin_gamma = np.clip(h_dot / max(v_mag, 1e-9), -1.0, 1.0)
    gamma_deg = float(np.degrees(np.arcsin(sin_gamma)))

    return {
        "vi_m_s": v_mag,
        "hdot_m_s": h_dot,
        "alt_m": alt_m,
        "alt_km": alt_m / 1000.0,
        "vi_fps": v_mag * M_PER_S_TO_FPS,
        "hdot_fps": h_dot * M_PER_S_TO_FPS,
        "alt_nm": alt_m * M_TO_NM,
        "gamma_deg": gamma_deg,
    }


def evaluate_p11_pitch_roll_program(t_sec: float) -> tuple[float, float, bool]:
    """Evaluate the P11 S-IC boost pitch polynomial and roll program.

    Cites:
      * src("Comanche055/P11.agc", "ATERJOB")
      * src("Comanche055/P11.agc", "ATTDISP")
      * src("Comanche055/P11.agc", "ATTDISP1")

    Between RPSTART (~10 s after liftoff) and POLYSTOP (~133 s after liftoff),
    ATTDISP evaluates a 6th-degree polynomial POWRSERS for desired pitch P(t)
    measured from the liftoff pad vertical, and a linear rollout ramp for roll.
    Outside [RPSTART, RPSTART + |POLYSTOP|], ATTDISP branches to NOPOLY (attitude hold).
    (Polynomial coefficients were pad-loaded into erasable POLYNUM; here we use a
    realistic Saturn V S-IC gravity-turn pitch polynomial approximation.)
    """
    rp_start = 10.0  # s (RPSTART)
    poly_duration = 123.0  # s (-POLYSTOP, ending at t = 133 s)
    if t_sec < rp_start:
        return 0.0, 0.0, False
    if t_sec > rp_start + poly_duration:
        return 62.5, 18.0, False

    tau = (t_sec - rp_start) / poly_duration  # normalized [0, 1] over polynomial window
    # 6th-order polynomial in tau matching Saturn V S-IC pitchover (0 deg to 62.5 deg from vertical)
    coeffs = [0.0, 22.0, 95.0, -78.0, 31.0, -7.5, 0.0]
    pitch_from_vert_deg = sum(c * (tau**i) for i, c in enumerate(coeffs))

    # Roll program rolls spacecraft from pad azimuth (90 deg) to launch azimuth (72 deg) in ~18 s
    roll_rate_deg_s = 1.0  # SATRLRT approx
    roll_deg = min(18.0, (t_sec - rp_start) * roll_rate_deg_s)
    return float(pitch_from_vert_deg), float(roll_deg), True


def simulate_saturn_v_ascent() -> dict[str, np.ndarray]:
    """Drive P11's AVERAGEG + S11.1 monitor loop with a simulated Saturn V ascent.

    Cites:
      * src("Comanche055/P11.agc", "VHHDOT")
      * src("Comanche055/P11.agc", "S11.1")
      * src("Comanche055/SERVICER207.agc", "CALCRVG")

    Note: Because the Saturn V Instrument Unit (IU) flew the ascent and the CMC
    only read the PIPAs, the booster thrust profile is not stored in Comanche055.
    We use a clearly-labelled 3-stage Saturn V guidance approximation (S-IC, S-II,
    S-IVB first burn) that inserts the CSM/LM/S-IVB stack into a 185.2 km (100.0 NM)
    circular Earth parking orbit at t = 700 s.
    """
    rn, vn, _refsmmat = initialize_p11_pad_state()
    g_vec = compute_gravity_calcrvg(rn)

    dt = 2.0  # AGC SERVICER / AVERAGEG period = 2.0 seconds
    t_end = 700.0
    times = np.arange(0.0, t_end + 0.1, dt)

    # Target parking orbit parameters (100.0 NM = 185.2 km circular orbit)
    h_target = 185_200.0  # m
    r_target = R_PAD + h_target
    v_circ_target = np.sqrt(MU_EARTH / r_target)

    # Storage arrays
    alt_km = np.zeros_like(times)
    alt_nm = np.zeros_like(times)
    vi_m_s = np.zeros_like(times)
    vi_fps = np.zeros_like(times)
    hdot_m_s = np.zeros_like(times)
    hdot_fps = np.zeros_like(times)
    gamma_deg = np.zeros_like(times)
    sensed_g = np.zeros_like(times)
    poly_pitch_deg = np.zeros_like(times)
    poly_active = np.zeros(len(times), dtype=bool)

    for k, t in enumerate(times):
        # 1. Run P11's S11.1 Noun 62 computation on current state (RN, VN)
        n62 = compute_noun62_s11_1(rn, vn)
        alt_km[k] = n62["alt_km"]
        alt_nm[k] = n62["alt_nm"]
        vi_m_s[k] = n62["vi_m_s"]
        vi_fps[k] = n62["vi_fps"]
        hdot_m_s[k] = n62["hdot_m_s"]
        hdot_fps[k] = n62["hdot_fps"]
        gamma_deg[k] = n62["gamma_deg"]

        p_deg, _r_deg, is_poly = evaluate_p11_pitch_roll_program(float(t))
        poly_pitch_deg[k] = 90.0 - p_deg  # convert pitch-from-vertical to pitch above horizon
        poly_active[k] = is_poly

        # 2. Local vertical / horizontal basis at current position
        r_mag = float(np.linalg.norm(rn))
        u_r = rn / r_mag  # radially outward (up)
        h_vec = np.cross(rn, vn)
        u_perp = h_vec / np.linalg.norm(h_vec)
        u_horiz = np.cross(u_perp, u_r)  # forward along ground track

        v_r = float(np.dot(vn, u_r))
        v_h = float(np.dot(vn, u_horiz))

        # 3. Simulated Saturn V stage thrust/guidance profile (producing sensed DELVREF)
        # Stage 1: S-IC (0 - 162 s), Stage 2: S-II (162 - 548 s), Stage 3: S-IVB (548 - 700 s)
        if t < 162.0:
            # S-IC stage: accelerate from 1.25 g at liftoff to ~3.9 g at OECO (with CECO dip at 135 s)
            tau1 = t / 162.0
            accel_mag = G0 * (1.25 + 2.75 * tau1**1.35)
            if 135.0 <= t < 162.0:
                accel_mag *= 0.80  # Center engine cutoff (CECO) limits peak g to ~4g
            # Pitch program from vertical (90 deg) down toward ~24 deg above horizon
            if t < 10.0:
                pitch_horiz_rad = np.radians(90.0)
            else:
                pitch_horiz_rad = np.radians(90.0 - 66.0 * ((t - 10.0) / 152.0) ** 0.82)
            a_sensed = accel_mag * (
                np.sin(pitch_horiz_rad) * u_r + np.cos(pitch_horiz_rad) * u_horiz
            )
        else:
            # S-II (162 - 548 s) and S-IVB (548 - 700 s): closed-loop Iterative Guidance Mode (IGM)
            # approximation steering (r, v_r, v_h) smoothly to (r_target, 0, v_circ_target) at t = 700 s
            t_rem = max(t_end - t, dt)
            # Required horizontal acceleration to reach orbital speed at t_end
            a_horiz_req = (v_circ_target - v_h) / t_rem
            # Required radial acceleration (PD controller on altitude and altitude rate + gravity/centrifugal)
            h_err = r_target - r_mag
            centrifugal = (v_h**2) / r_mag
            g_radial = float(np.dot(g_vec, u_r))  # negative (~ -9.3 m/s^2)
            a_net_r_des = (6.0 * h_err / (t_rem**2)) - (4.0 * v_r / t_rem)
            a_sensed_r = a_net_r_des - g_radial - centrifugal
            a_sensed = a_sensed_r * u_r + a_horiz_req * u_horiz

        sensed_g[k] = float(np.linalg.norm(a_sensed)) / G0
        delv_ref = a_sensed * dt

        # 4. Run the AGC's 2-second AVERAGEG state update (CALCRVG)
        if k < len(times) - 1:
            rn, vn, g_vec = average_g_step(rn, vn, g_vec, delv_ref, dt=dt)

    return {
        "t": times,
        "alt_km": alt_km,
        "alt_nm": alt_nm,
        "vi_m_s": vi_m_s,
        "vi_fps": vi_fps,
        "hdot_m_s": hdot_m_s,
        "hdot_fps": hdot_fps,
        "gamma_deg": gamma_deg,
        "sensed_g": sensed_g,
        "poly_pitch_deg": poly_pitch_deg,
        "poly_active": poly_active,
    }


def plot_p11_ascent_monitor(sim: dict[str, np.ndarray]) -> None:
    """Create and save the 3-panel P11 Earth Orbit Insertion Monitor figure."""
    t = sim["t"]
    fig, axes = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True)

    events = [
        (10.0, "Pitch/Roll Start\n(RPSTART)", "#555555"),
        (133.0, "Poly End\n(POLYSTOP)", "#555555"),
        (162.0, "S-IC / S-II Staging\n(2 min 42 s)", "#d95f02"),
        (548.0, "S-II / S-IVB Staging\n(9 min 08 s)", "#7570b3"),
        (700.0, "EOI Cutoff\n(185.2 km / 100 NM)", "#1b9e77"),
    ]

    # Panel 1: Altitude H (Noun 62 R3)
    ax0 = axes[0]
    ax0.plot(t, sim["alt_km"], color="#1f77b4", lw=2.2, label="Altitude H above pad (km)")
    ax0.axhline(185.2, color="#1b9e77", ls=":", lw=1.2, label="Target Parking Orbit (185.2 km / 100.0 NM)")
    ax0.set_ylim(-10, 245)
    ax0.set_ylabel("Altitude H (km)")
    ax0.set_title("Apollo 11 CMC P11: Earth Orbit Insertion Monitor (Noun 62 Display vs Time)")
    ax0_nm = ax0.twinx()
    ax0_nm.set_ylim(np.array(ax0.get_ylim()) * (1000.0 * M_TO_NM))
    ax0_nm.set_ylabel("N62 R3: Altitude (NM)", color="#1f77b4")
    ax0_nm.grid(False)
    ax0.legend(loc="upper left")

    # Panel 2: Inertial Velocity VI (Noun 62 R1) and Altitude Rate HDOT (Noun 62 R2)
    ax1 = axes[1]
    ax1.plot(t, sim["vi_m_s"], color="#e41a1c", lw=2.2, label="N62 R1: Inertial Velocity $V_I = |\\mathbf{v}_N|$ (m/s)")
    ax1.plot(t, sim["hdot_m_s"] * 10.0, color="#ff7f00", lw=1.8, ls="--",
             label="N62 R2: Altitude Rate $\\dot{h} = \\hat{\\mathbf{r}}_N \\cdot \\mathbf{v}_N \\times 10$ (m/s)")
    ax1.set_ylabel("Velocity (m/s)")
    ax1.legend(loc="upper left")

    # Panel 3: Flight-path angle gamma and S-IC pitch polynomial
    ax2 = axes[2]
    ax2.plot(t, sim["gamma_deg"], color="#2ca02c", lw=2.2,
             label="Inertial Flight-Path Angle $\\gamma = \\arcsin(\\dot{h}/V_I)$ (deg)")
    poly_mask = sim["poly_active"]
    ax2.plot(t[poly_mask], sim["poly_pitch_deg"][poly_mask], color="#984ea3", lw=2.0, ls="-.",
             label="ATTDISP Pitch Polynomial $P(t)$ above horizon (10–133 s)")
    ax2.axvspan(10.0, 133.0, color="#984ea3", alpha=0.08, label="P11 FDAI Pitch/Roll Polynomial Window")
    ax2.set_ylabel("Angle (deg)")
    ax2.set_xlabel("Time from Liftoff (s)")
    ax2.set_ylim(-5, 95)
    ax2.legend(loc="upper right")

    for ax in axes:
        for t_ev, _label, color in events:
            ax.axvline(t_ev, color=color, ls="--", lw=1.0, alpha=0.7)

    # Annotate key events on top panel
    offsets_y = {162.0: 32.0, 548.0: -52.0, 700.0: 26.0}
    offsets_x = {162.0: -85.0, 548.0: -125.0, 700.0: -115.0}
    for t_ev, label, color in events[2:]:
        y_ev = float(np.interp(t_ev, t, sim["alt_km"]))
        ax0.annotate(
            label,
            xy=(t_ev, y_ev),
            xytext=(t_ev + offsets_x[t_ev], y_ev + offsets_y[t_ev]),
            fontsize=8.5,
            color=color,
            weight="bold",
            arrowprops={"arrowstyle": "->", "color": color, "lw": 1.0},
        )

    save(fig, "csm_01_p11_ascent_monitor")


def main() -> None:
    """Narrate and execute the P11 Earth Orbit Insertion Monitor walkthrough."""
    step(
        1,
        "Liftoff Initialization & Prelaunch REFSMMAT",
        f"Source: {src('Comanche055/P11.agc', 'P11')} & {src('Comanche055/P11.agc', 'MATRXJOB')}\n"
        "When the Saturn V liftoff discrete arrives, P11 zeroes the CMC clock (TIME2/TIME1),\n"
        "initializes the PIPA accelerometers via PREREAD1, and computes initial pad position RN1\n"
        "and Earth-rotation velocity VN1 = -ERTHRAT * (RN1 x UNITW).",
    )
    rn1, vn1, refsmmat = initialize_p11_pad_state()
    print(f"     Pad radius |RN1|       = {np.linalg.norm(rn1):,.1f} m (RPAD)")
    print(f"     Inertial speed at pad  = {np.linalg.norm(vn1):.2f} m/s ({np.linalg.norm(vn1)*M_PER_S_TO_FPS:.1f} ft/s)")
    print(f"     REFSMMAT det           = {np.linalg.det(refsmmat):.6f} (orthonormal launch triad)")

    step(
        2,
        "FDAI Attitude Error Polynomial (ATERTASK / ATTDISP)",
        f"Source: {src('Comanche055/P11.agc', 'ATERJOB')} & {src('Comanche055/P11.agc', 'ATTDISP')}\n"
        "From RPSTART (+10 s) to POLYSTOP (+133 s), the CMC evaluates a 6th-order pitch\n"
        "polynomial (POWRSERS) and roll rollout rate (SATRLRT) every 0.5 s to drive the FDAI\n"
        "attitude-error needles via CALCGTA and NEEDLER.",
    )
    p60, r60, _ = evaluate_p11_pitch_roll_program(60.0)
    print(f"     At T+60 s: desired pitch from vertical = {p60:.1f} deg, roll = {r60:.1f} deg")

    step(
        3,
        "Every-2-Second AVERAGEG Integration & Noun 62 Display (VHHDOT / S11.1)",
        f"Source: {src('Comanche055/P11.agc', 'VHHDOT')}, {src('Comanche055/P11.agc', 'S11.1')}, "
        f"{src('Comanche055/SERVICER207.agc', 'CALCRVG')}\n"
        "Every 2 seconds, SERVICER integrates PIPA velocity increments (DELV) and J2 gravity,\n"
        "then jumps via AVGEXIT to VHHDOT -> S11.1 to display Verb 06 Noun 62:\n"
        "  R1 = VI (ft/s), R2 = HDOT (ft/s), R3 = H above pad (NM).",
    )
    sim = simulate_saturn_v_ascent()
    for t_sample in [0.0, 162.0, 548.0, 700.0]:
        idx = int(round(t_sample / 2.0))
        print(
            f"     T+{t_sample:5.0f} s | N62 R1 VI = {sim['vi_fps'][idx]:7.0f} ft/s ({sim['vi_m_s'][idx]:6.1f} m/s) | "
            f"R2 HDOT = {sim['hdot_fps'][idx]:6.0f} ft/s ({sim['hdot_m_s'][idx]:5.1f} m/s) | "
            f"R3 H = {sim['alt_nm'][idx]:5.1f} NM ({sim['alt_km'][idx]:5.1f} km) | "
            f"gamma = {sim['gamma_deg'][idx]:5.1f} deg"
        )

    step(
        4,
        "Saving P11 Ascent Monitor Figure",
        "Generating 3-panel plot of Altitude, Inertial Velocity / Altitude Rate, and Flight-Path Angle.",
    )
    plot_p11_ascent_monitor(sim)


if __name__ == "__main__":
    main()
