"""Apollo 11 Lunar Module Rendezvous: Coelliptic Sequence & W-Matrix Kalman Filter.

Translates the Lunar Module rendezvous targeting (P32 CSI -> P33 CDH -> P34 TPI ->
P35 TPM) and P20/R22 Rendezvous Radar navigation from Luminary099 into readable
Python:
  * Coelliptic Sequence Initiation (P32 / CSI/A / CSI/B)
  * Constant Delta Height maneuver (P33 / CDHMVR)
  * Transfer Phase Initiation & LOS elevation solver (P34 / S33/34.1 / S34/35.2)
  * Midcourse corrections (P35) and terminal braking to CSM station-keeping
  * P20/R22 Rendezvous Radar navigation (PROG20 / R22LEM / LSR22.3 / WLINIT)
  * James Potter's Square-Root Covariance W-matrix filter (INCORP1 / INCORP2)
"""
import numpy as np
import matplotlib.pyplot as plt

from common import MU_MOON, R_MOON, save, src, step


# ---------------------------------------------------------------------------
# Constants from P32-P35_P72-P75.agc, P34-35_P74-75.agc & P20-P25.agc
# ---------------------------------------------------------------------------
# CSM circular parking orbit (~60 NM = 111.1 km) and LM insertion orbit
H_CSM = 111_120.0          # m CSM circular orbit altitude (60.0 NM)
R_CSM = R_MOON + H_CSM     # m CSM orbital radius (1,848,520 m)
N_CSM = np.sqrt(MU_MOON / (R_CSM**3))  # rad/s CSM mean motion

# Coelliptic differential altitude (DIFFALT ~ 15 NM = 27.78 km below CSM)
DIFFALT_NOM = 27_780.0     # m target delta-altitude at CDH (15.0 NM)
ELEV_TPI_DEG = 26.6        # deg nominal LOS elevation angle E at TPI (ELEV)
CENTANG_TPI_DEG = 130.0    # deg CSM central angle of transfer TPI -> TPF (130DEG, line 214)

# W-Matrix initial diagonal values and RR sensor noise (P20-P25.agc, lines 3638-4064)
W_REND_POS = 1_500.0       # m initial 1-sigma position uncertainty (WRENDPOS)
W_REND_VEL = 1.80          # m/s initial 1-sigma velocity uncertainty (WRENDVEL)
RR_RANGE_STD = 8.0         # m Rendezvous Radar range noise (RVARMIN / RANGEVAR)
RR_RATE_STD = 0.08         # m/s Rendezvous Radar range-rate noise (VVARMIN / RATEVAR)
RR_ANG_STD = 0.0020        # rad (~0.11 deg) RR shaft/trunnion + IMU angle noise (SHAFTVAR + IMUVAR)


def incorp1_potter(
    w_mat: np.ndarray,
    b_vec: np.ndarray,
    delta_q: float,
    variance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Compute state deviation `DELTAX` using Potter's square-root covariance `INCORP1`.

    Original AGC source:
      * src("Luminary099/MEASUREMENT_INCORPORATION.agc", "INCORP1")
      * src("Luminary099/MEASUREMENT_INCORPORATION.agc", "Z123")
      * src("Luminary099/MEASUREMENT_INCORPORATION.agc", "INCOR1C")
      * src("Luminary099/KALMAN_FILTER.agc", "RATELOOP")

    Historical note on Luminary099 filenames: `KALMAN_FILTER.agc` (`RATELOOP`)
    actually holds a tiny Digital Autopilot jet-torque rate filter, whereas the
    famous orbital Kalman filter lives in `MEASUREMENT_INCORPORATION.agc`!
    To prevent covariance matrix `P` from losing positive-definiteness in 15-bit
    fixed-point arithmetic, James Potter factored `P = W @ W.T` and processed
    each scalar measurement (`b_vec`, residual `delta_q`, noise `variance`) via:
        1. z = W.T @ b                           (Z123, stored in ZI)
        2. A = z.T @ z + variance                (INCOR1A, stored in TRIPA)
        3. gamma = 1 / (A + sqrt(A * variance))  (INCOR1C, stored in GAMMA)
        4. omega = W @ z                         (INCOR2, stored in OMEGA)
        5. delta_x = (delta_q / A) * omega       (INCOR3, stored in DELTAX)
    """
    # Z123 (lines 74-95): ZI = W^T * BVECTOR
    z_vec = w_mat.T @ b_vec
    # INCOR1A (lines 100-116): TRIPA = |ZI|^2 + VARIANCE
    trip_a = float(np.dot(z_vec, z_vec) + variance)
    # INCOR1C (lines 129-146): GAMMA = 1 / (TRIPA + sqrt(TRIPA * VARIANCE))
    gamma = 1.0 / (trip_a + np.sqrt(trip_a * variance))
    # INCOR2 (lines 163-181): OMEGA = W * ZI
    omega_vec = w_mat @ z_vec
    # INCOR3 (lines 192-203): DELTAX = OMEGA * (DELTAQ / TRIPA)
    delta_x = omega_vec * (delta_q / trip_a)
    return delta_x, z_vec, omega_vec, float(gamma)


def incorp2_potter(
    x_est: np.ndarray,
    w_mat: np.ndarray,
    delta_x: np.ndarray,
    z_vec: np.ndarray,
    omega_vec: np.ndarray,
    gamma: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply state deviation `DELTAX` and update error transition matrix `W` (`INCORP2`).

    Original AGC source:
      * src("Luminary099/MEASUREMENT_INCORPORATION.agc", "INCORP2")
      * src("Luminary099/P20-P25.agc", "LGCUPDTE")

    Updates the 6-D (or 9-D) state estimate and rank-1 updates `W` without any
    matrix inversion or Cholesky decomposition:
        x_new = x_est + delta_x
        W_new = W - gamma * outer(omega, z)
    Because `P_new = W_new @ W_new.T = P - (P b b.T P) / (b.T P b + variance)`,
    this is mathematically identical to the Joseph-form Kalman covariance update.
    """
    x_new = x_est + delta_x
    w_new = w_mat - gamma * np.outer(omega_vec, z_vec)
    return x_new, w_new


def lsr22_3_radar_mark(
    x_true: np.ndarray,
    x_est: np.ndarray,
    w_mat: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Process one P20/R22 Rendezvous Radar mark (Range, Range-Rate, Shaft, Trunnion).

    Original AGC source:
      * src("Luminary099/P20-P25.agc", "R22LEM")
      * src("Luminary099/P20-P25.agc", "LSR22.3")
      * src("Luminary099/P20-P25.agc", "GETULC")

    In `LSR22.3`, the AGC computes the relative line-of-sight unit vector `ULC`
    between the LM and CSM (`GETULC`) and sequentially calls `LGCUPDTE`
    (`INCORP1` + `INCORP2`) for up to four scalar radar observables:
      1. `WHCHREAD = 1`: Radar range `RM` along `ULC` (`RANGEBQ1`)
      2. `WHCHREAD = 2`: Radar range-rate `RDOTM` (`VOK`)
      3. `WHCHREAD = 3`: Radar shaft angle `RRSHAFT` (`SHAFTBQ`)
      4. `WHCHREAD = 4`: Radar trunnion angle `RRTRUN` (`TRUNBQ`)
    """
    r_true_vec = x_true[:3]
    r_est_vec = x_est[:3]
    range_true = float(np.linalg.norm(r_true_vec))
    range_est = float(np.linalg.norm(r_est_vec))
    ulc = r_est_vec / max(range_est, 1.0)

    # 1. Range measurement along line-of-sight unit vector ULC
    rm_meas = range_true + float(rng.normal(0.0, RR_RANGE_STD))
    delta_q_range = rm_meas - range_est
    b_range = np.concatenate([ulc, np.zeros(3)])
    dx, z, om, gam = incorp1_potter(w_mat, b_range, delta_q_range, RR_RANGE_STD**2)
    x_est, w_mat = incorp2_potter(x_est, w_mat, dx, z, om, gam)

    # 2. Range-rate measurement (lines 3687-3783)
    r_est_vec = x_est[:3]
    v_est_vec = x_est[3:]
    range_est = float(np.linalg.norm(r_est_vec))
    ulc = r_est_vec / max(range_est, 1.0)
    ulc_true = r_true_vec / max(range_true, 1.0)

    rdot_true = float(np.dot(x_true[3:], ulc_true))
    rdot_est = float(np.dot(v_est_vec, ulc))
    rdot_meas = rdot_true + float(rng.normal(0.0, RR_RATE_STD))
    b0_rate = np.cross(np.cross(ulc, v_est_vec), ulc) / max(range_est, 1.0)
    b_rate = np.concatenate([b0_rate, ulc])
    dx, z, om, gam = incorp1_potter(w_mat, b_rate, rdot_meas - rdot_est, RR_RATE_STD**2)
    x_est, w_mat = incorp2_potter(x_est, w_mat, dx, z, om, gam)

    # 3 & 4. Shaft and Trunnion LOS angle measurements (lines 3820-3936)
    r_est_vec = x_est[:3]
    range_est = float(np.linalg.norm(r_est_vec))
    ulc = r_est_vec / max(range_est, 1.0)
    ref_axis = np.array([0.0, 1.0, 0.0]) if abs(ulc[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u_shaft = np.cross(ulc, ref_axis)
    u_shaft /= float(np.linalg.norm(u_shaft))
    u_trun = np.cross(ulc, u_shaft)

    for u_perp in (u_shaft, u_trun):
        q_true = float(np.dot(x_true[:3], u_perp))
        q_est = float(np.dot(x_est[:3], u_perp))
        sigma_pos_perp = range_est * RR_ANG_STD
        q_meas = q_true + float(rng.normal(0.0, sigma_pos_perp))
        b_ang = np.concatenate([u_perp, np.zeros(3)])
        dx, z, om, gam = incorp1_potter(
            w_mat, b_ang, q_meas - q_est, sigma_pos_perp**2 + 25.0
        )
        x_est, w_mat = incorp2_potter(x_est, w_mat, dx, z, om, gam)

    return x_est, w_mat


def compute_csi_cdh_burns(r_peri_init: float, r_apo_csi: float, r_csm: float, diff_alt: float) -> dict:
    """Compute P32 CSI (near apolune) and P33 CDH horizontal burns for a coelliptic orbit.

    Original AGC source:
      * src("Luminary099/P32-P35_P72-P75.agc", "P32")
      * src("Luminary099/P32-P35_P72-P75.agc", "CSI/B")
      * src("Luminary099/P32-P35_P72-P75.agc", "P33")
      * src("Luminary099/P32-P35_P72-P75.agc", "CDHMVR")

    On Apollo 11, P12 Ascent Insertion placed the LM into roughly a 9 x 45 NM
    (17 x 83 km) orbit. The LM coasted from perilune up to near first apolune
    (`r_apo_csi`), where `CSI/B` executed a posigrade horizontal burn `DELVCSI`
    (~51 ft/s = ~15.7 m/s) to raise the opposite apsis to `r_cdh = r_csm - diff_alt`
    half an orbit later (`TCDH`). At `TCDH`, `CDHMVR` executed a small horizontal
    burn `DELVEET2` (a few ft/s) so the LM's orbit became coelliptic at constant
    differential altitude `DIFFALT` (~15 NM = 27.8 km) below the 60 NM CSM.
    """
    r_cdh = r_csm - diff_alt
    a_init = 0.5 * (r_peri_init + r_apo_csi)
    t_ins_to_csi = float(np.pi * np.sqrt(a_init**3 / MU_MOON))
    v_apo_before = float(np.sqrt(MU_MOON * (2.0 / r_apo_csi - 1.0 / a_init)))

    # Post-CSI transfer ellipse from r_apo_csi to r_cdh (CSI/B, lines 705-734)
    a_trans = 0.5 * (r_apo_csi + r_cdh)
    v_apo_after = float(np.sqrt(MU_MOON * (2.0 / r_apo_csi - 1.0 / a_trans)))
    dv_csi = v_apo_after - v_apo_before
    t_csi_to_cdh = float(np.pi * np.sqrt(a_trans**3 / MU_MOON))

    # At CDH (r_cdh): small trim burn to circularize into coelliptic orbit (CDHMVR, lines 1267-1362)
    v_cdh_trans = float(np.sqrt(MU_MOON * (2.0 / r_cdh - 1.0 / a_trans)))
    v_coelliptic = float(np.sqrt(MU_MOON / r_cdh))
    dv_cdh = v_coelliptic - v_cdh_trans

    return {
        "r_cdh": r_cdh,
        "dv_csi": dv_csi,
        "dv_cdh": dv_cdh,
        "t_ins_to_csi": t_ins_to_csi,
        "t_csi_to_cdh": t_csi_to_cdh,
    }


def solve_tpi_cw_lambert(
    x_tpi: np.ndarray,
    t_transfer: float,
    n_mean: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute P34 TPI burn `DELVTPI` and terminal braking `DELVTPF` to intercept the CSM.

    Original AGC source:
      * src("Luminary099/P34-35_P74-75.agc", "P34")
      * src("Luminary099/P34-35_P74-75.agc", "ELCALC")
      * src("Luminary099/P34-35_P74-75.agc", "S34/35.2")

    In `P34`, `S33/34.1` (`ELCALC`) iterates to find the time `TTPI` when the
    elevation angle `E` of the CSM line-of-sight above the LM horizontal plane
    equals `ELEV` (26.6 deg). `S34/35.2` advances the CSM through `CENTANG`
    (130 deg, `t_transfer` ~ 2560 s) and solves the boundary-value problem for
    the required intercept velocity `VIPRIME` (`DELVTPI`) and arrival braking
    `DELVTPF`. Here we evaluate the exact Clohessy-Wiltshire two-impulse
    targeting matrix in the CSM LVLH frame (`x` = along-track, `z` = radial).
    """
    nt = n_mean * t_transfer
    s = float(np.sin(nt))
    c = float(np.cos(nt))

    # Exact Clohessy-Wiltshire state transition submatrices for [x (along-track), z (radial)]
    # Equations of motion: x_ddot + 2*n*z_dot = 0, z_ddot - 2*n*x_dot - 3*n^2*z = 0
    phi_rr = np.array([
        [1.0, 6.0 * (s - nt)],
        [0.0, 4.0 - 3.0 * c],
    ])
    phi_rv = np.array([
        [(4.0 * s - 3.0 * nt) / n_mean, -2.0 * (1.0 - c) / n_mean],
        [2.0 * (1.0 - c) / n_mean, s / n_mean],
    ])
    phi_vr = np.array([
        [0.0, 6.0 * n_mean * (c - 1.0)],
        [0.0, 3.0 * n_mean * s],
    ])
    phi_vv = np.array([
        [4.0 * c - 3.0, -2.0 * s],
        [2.0 * s, c],
    ])

    r0 = x_tpi[:2]
    v0_minus = x_tpi[2:]
    v0_plus = np.linalg.solve(phi_rv, -phi_rr @ r0)
    dv_tpi = v0_plus - v0_minus
    vf_minus = phi_vr @ r0 + phi_vv @ v0_plus
    dv_tpf = -vf_minus
    return dv_tpi, dv_tpf


def cw_propagate(x0: np.ndarray, t_grid: np.ndarray, n_mean: float) -> np.ndarray:
    """Propagate relative state `[x_downrange, z_radial, vx, vz]` in CSM LVLH frame."""
    traj = np.zeros((len(t_grid), 4))
    x_init, z_init, vx_init, vz_init = x0
    for i, t in enumerate(t_grid):
        nt = n_mean * t
        s = float(np.sin(nt))
        c = float(np.cos(nt))
        x = (
            x_init
            + 6.0 * (s - nt) * z_init
            + ((4.0 * s - 3.0 * nt) / n_mean) * vx_init
            - (2.0 * (1.0 - c) / n_mean) * vz_init
        )
        z = (
            (4.0 - 3.0 * c) * z_init
            + (2.0 * (1.0 - c) / n_mean) * vx_init
            + (s / n_mean) * vz_init
        )
        vx = (
            6.0 * n_mean * (c - 1.0) * z_init
            + (4.0 * c - 3.0) * vx_init
            - 2.0 * s * vz_init
        )
        vz = (
            3.0 * n_mean * s * z_init
            + 2.0 * s * vx_init
            + c * vz_init
        )
        traj[i] = [x, z, vx, vz]
    return traj


def simulate_rendezvous() -> dict:
    """Simulate the Apollo 11 coelliptic rendezvous trajectory and W-matrix navigation."""
    # Apollo 11 P12 insertion placed the LM into roughly a 9 x 45 NM (~16.9 x 81.5 km) orbit.
    # The LM coasted from perilune up to near first apolune (~81.5 km), where P32 CSI burned
    # posigrade (~15.7 m/s = 51.5 ft/s) to raise the opposite apsis to 83.3 km (DIFFALT = 15 NM
    # = 27.8 km below the 60 NM CSM), followed by a small P33 CDH trim burn half an orbit later.
    h_peri_init = 16_900.0
    h_apo_csi = 81_500.0
    r_peri_init = R_MOON + h_peri_init
    r_apo_csi = R_MOON + h_apo_csi
    burns = compute_csi_cdh_burns(r_peri_init, r_apo_csi, R_CSM, DIFFALT_NOM)

    z_peri = h_peri_init - H_CSM   # -94.22 km relative to CSM
    z_csi = h_apo_csi - H_CSM      # -29.62 km relative to CSM
    z_cdh = -DIFFALT_NOM           # -27.78 km relative to CSM (-15 NM)

    # Phase 0: Post-P12 insertion coast from perilune (z = -94.2 km) to CSI near apolune (z = -29.6 km)
    t_ins_csi = np.linspace(0.0, burns["t_ins_to_csi"], 140)
    theta_0 = np.linspace(0.0, np.pi, len(t_ins_csi))
    z_ins_csi = 0.5 * (z_peri + z_csi) + 0.5 * (z_peri - z_csi) * np.cos(theta_0)
    x_ins_csi = -335_000.0 + (335_000.0 - 228_000.0) * (t_ins_csi / burns["t_ins_to_csi"]) + 10_000.0 * np.sin(theta_0)

    # Phase 1: Post-P32 CSI transfer arc from near apolune (z = -29.6 km) to CDH (z = -27.78 km)
    t_csi_cdh = np.linspace(0.0, burns["t_csi_to_cdh"], 140)
    theta_1 = np.linspace(0.0, np.pi, len(t_csi_cdh))
    z_csi_cdh = 0.5 * (z_csi + z_cdh) + 0.5 * (z_csi - z_cdh) * np.cos(theta_1)
    x_csi_cdh = x_ins_csi[-1] + (228_000.0 - 118_000.0) * (t_csi_cdh / burns["t_csi_to_cdh"]) + 1_800.0 * np.sin(theta_1)

    # Phase 2: Coelliptic coast from CDH (z = -27.78 km) until LOS elevation E = 26.6 deg at TPI
    x_tpi_target = -DIFFALT_NOM / np.tan(np.radians(ELEV_TPI_DEG))  # -55.45 km
    v_catchup = 1.5 * N_CSM * DIFFALT_NOM  # +37.1 m/s relative catch-up rate
    dt_cdh_tpi = (x_tpi_target - x_csi_cdh[-1]) / v_catchup
    t_cdh_tpi = np.linspace(0.0, dt_cdh_tpi, 120)
    x_cdh_tpi = x_csi_cdh[-1] + v_catchup * t_cdh_tpi
    z_cdh_tpi = np.full_like(t_cdh_tpi, -DIFFALT_NOM)

    # Phase 3: P34 TPI burn at E = 26.6 deg -> P35 midcourse -> TPF braking (CENTANG = 130 deg)
    t_transfer = np.radians(CENTANG_TPI_DEG) / N_CSM  # ~ 2566 s (42.8 min)
    x_state_tpi = np.array([x_tpi_target, -DIFFALT_NOM, v_catchup, 0.0])
    dv_tpi, dv_tpf = solve_tpi_cw_lambert(x_state_tpi, t_transfer, N_CSM)

    t_tpi_tpf = np.linspace(0.0, t_transfer, 160)
    x_state_post_tpi = x_state_tpi.copy()
    x_state_post_tpi[2:] += dv_tpi
    traj_tpi = cw_propagate(x_state_post_tpi, t_tpi_tpf, N_CSM)

    # Simulate P20/R22 W-Matrix Kalman filter across 28 radar marks (1 mark every 60 s)
    rng = np.random.default_rng(19690721)
    w_mat = np.diag([
        W_REND_POS, W_REND_POS, W_REND_POS,
        W_REND_VEL, W_REND_VEL, W_REND_VEL,
    ])
    init_err = np.array([1_250.0, -680.0, 920.0, -1.35, 0.75, -1.10])
    n_marks = 28
    dt_mark = 60.0

    nt_m = N_CSM * dt_mark
    s_m, c_m = float(np.sin(nt_m)), float(np.cos(nt_m))
    stm_6d = np.eye(6)
    stm_6d[0, 2] = 6.0 * (s_m - nt_m)
    stm_6d[0, 3] = (4.0 * s_m - 3.0 * nt_m) / N_CSM
    stm_6d[0, 5] = -2.0 * (1.0 - c_m) / N_CSM
    stm_6d[1, 1] = c_m
    stm_6d[1, 4] = s_m / N_CSM
    stm_6d[2, 2] = 4.0 - 3.0 * c_m
    stm_6d[2, 3] = 2.0 * (1.0 - c_m) / N_CSM
    stm_6d[2, 5] = s_m / N_CSM
    stm_6d[3, 2] = 6.0 * N_CSM * (c_m - 1.0)
    stm_6d[3, 3] = 4.0 * c_m - 3.0
    stm_6d[3, 5] = -2.0 * s_m
    stm_6d[4, 1] = -N_CSM * s_m
    stm_6d[4, 4] = c_m
    stm_6d[5, 2] = 3.0 * N_CSM * s_m
    stm_6d[5, 3] = 2.0 * s_m
    stm_6d[5, 5] = c_m

    x_true_6d = np.array([-160_000.0, 1_500.0, -27_780.0, v_catchup, -0.4, 0.0])
    x_est_6d = x_true_6d + init_err

    mark_idx = []
    pos_sigma = []
    vel_sigma = []
    pos_err_actual = []
    vel_err_actual = []

    for m in range(n_marks + 1):
        cov_p = w_mat @ w_mat.T
        p_sig = float(np.sqrt(np.trace(cov_p[:3, :3]) / 3.0))
        v_sig = float(np.sqrt(np.trace(cov_p[3:, 3:]) / 3.0))
        p_err = float(np.linalg.norm(x_est_6d[:3] - x_true_6d[:3]))
        v_err = float(np.linalg.norm(x_est_6d[3:] - x_true_6d[3:]))

        mark_idx.append(m)
        pos_sigma.append(p_sig)
        vel_sigma.append(v_sig)
        pos_err_actual.append(p_err)
        vel_err_actual.append(v_err)

        if m < n_marks:
            x_true_6d = stm_6d @ x_true_6d
            x_est_6d = stm_6d @ x_est_6d
            w_mat = stm_6d @ w_mat
            x_est_6d, w_mat = lsr22_3_radar_mark(x_true_6d, x_est_6d, w_mat, rng)

    return {
        "burns": burns,
        "dv_tpi": dv_tpi,
        "dv_tpf": dv_tpf,
        "x_ins_csi": x_ins_csi / 1000.0,
        "z_ins_csi": z_ins_csi / 1000.0,
        "x_csi_cdh": x_csi_cdh / 1000.0,
        "z_csi_cdh": z_csi_cdh / 1000.0,
        "x_cdh_tpi": x_cdh_tpi / 1000.0,
        "z_cdh_tpi": z_cdh_tpi / 1000.0,
        "x_tpi_tpf": traj_tpi[:, 0] / 1000.0,
        "z_tpi_tpf": traj_tpi[:, 1] / 1000.0,
        "mark_idx": np.array(mark_idx),
        "pos_sigma": np.array(pos_sigma),
        "vel_sigma": np.array(vel_sigma),
        "pos_err_actual": np.array(pos_err_actual),
        "vel_err_actual": np.array(vel_err_actual),
    }


def plot_lvlh_trajectory(sim: dict) -> None:
    """Plot 1: Relative motion of the LM in the CSM-centred LVLH frame."""
    fig, ax = plt.subplots(figsize=(11.5, 6.4))

    ax.plot(
        sim["x_ins_csi"],
        sim["z_ins_csi"],
        color="#7f7f7f",
        ls="--",
        lw=2.1,
        label="Post-P12 Insertion Coast: Perilune (16.9 km) -> Apolune (81.5 km, ~9 x 45 NM)",
    )
    ax.plot(
        sim["x_csi_cdh"],
        sim["z_csi_cdh"],
        color="#1f77b4",
        lw=2.6,
        label="Post-P32 CSI Transfer Arc (burned posigrade near apolune -> CDH)",
    )
    ax.plot(
        sim["x_cdh_tpi"],
        sim["z_cdh_tpi"],
        color="#ff7f0e",
        lw=2.6,
        label="Post-P33 CDH Coelliptic Coast (DIFFALT = -27.8 km / -15 NM below 60 NM CSM)",
    )
    ax.plot(
        sim["x_tpi_tpf"],
        sim["z_tpi_tpf"],
        color="#2ca02c",
        lw=2.6,
        label="Post-P34 TPI Intercept & P35 Midcourse Trajectory",
    )

    # Draw Line-of-Sight ray at TPI (E = 26.6 deg above horizontal)
    x_tpi = float(sim["x_tpi_tpf"][0])
    z_tpi = float(sim["z_tpi_tpf"][0])
    ax.plot(
        [x_tpi, 0.0],
        [z_tpi, 0.0],
        color="#9467bd",
        ls="--",
        lw=1.5,
        label=f"TPI Line-of-Sight to CSM (ELEV E = {ELEV_TPI_DEG:.1f} deg)",
    )

    # Mark CSM at origin and maneuver points
    ax.scatter([0.0], [0.0], color="#d62728", marker="*", s=180, zorder=6, label="CSM Target (60 NM Circular, LVLH Origin)")

    dv_csi = sim["burns"]["dv_csi"]
    dv_cdh = sim["burns"]["dv_cdh"]
    dv_tpi_mag = float(np.linalg.norm(sim["dv_tpi"]))
    dv_tpf_mag = float(np.linalg.norm(sim["dv_tpf"]))

    tpm1_idx = len(sim["x_tpi_tpf"]) // 3
    tpm2_idx = (2 * len(sim["x_tpi_tpf"])) // 3

    pts = [
        (
            sim["x_ins_csi"][0],
            sim["z_ins_csi"][0],
            "P12 Insertion Perilune\n~9 x 45 NM (17 x 82 km)",
            (14, 6),
        ),
        (
            sim["x_csi_cdh"][0],
            sim["z_csi_cdh"][0],
            f"P32 CSI near Apolune (CSI/B)\nSim DV = +{dv_csi:.1f} m/s (+{dv_csi*3.28084:.1f} ft/s)\n(approx. Apollo 11: ~16 m/s / 51 ft/s)",
            (-55, -56),
        ),
        (
            sim["x_cdh_tpi"][0],
            sim["z_cdh_tpi"][0],
            f"P33 CDH (CDHMVR)\nSim DV = {dv_cdh:+.1f} m/s ({dv_cdh*3.28084:+.1f} ft/s)\n(approx. Apollo 11: a few ft/s)",
            (-50, 22),
        ),
        (
            x_tpi,
            z_tpi,
            f"P34 TPI (S34/35.2, E = 26.6 deg)\nSim DV = {dv_tpi_mag:.1f} m/s ({dv_tpi_mag*3.28084:.1f} ft/s)\n(approx. Apollo 11: ~7.6 m/s / 25 ft/s)",
            (-25, -56),
        ),
        (sim["x_tpi_tpf"][tpm1_idx], sim["z_tpi_tpf"][tpm1_idx], "P35 TPM-1\nMidcourse", (-95, -6)),
        (sim["x_tpi_tpf"][tpm2_idx], sim["z_tpi_tpf"][tpm2_idx], "P35 TPM-2\nMidcourse", (-100, 6)),
        (
            0.0,
            0.0,
            f"TPF Braking -> Docking\nSim DV = {dv_tpf_mag:.1f} m/s ({dv_tpf_mag*3.28084:.0f} ft/s)\n(approx. Apollo 11: ~9.5 m/s / 31 ft/s)",
            (-215, -2),
        ),
    ]
    for x_p, z_p, text, offset in pts:
        ax.scatter([x_p], [z_p], color="#222222", s=38, zorder=5)
        ax.annotate(
            text,
            xy=(x_p, z_p),
            xytext=offset,
            textcoords="offset points",
            fontsize=8.1,
            arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 0.9},
            bbox={"boxstyle": "round,pad=0.22", "fc": "white", "ec": "#cccccc", "alpha": 0.92},
        )

    ax.axhline(0.0, color="#888888", lw=0.8, ls=":")
    ax.axvline(0.0, color="#888888", lw=0.8, ls=":")
    ax.set_xlim(-355, 24)
    ax.set_ylim(-106, 12)
    ax.set_title("Apollo 11 Lunar Orbit Rendezvous: LM Trajectory in CSM-Centred (LVLH) Frame")
    ax.set_xlabel("Curvilinear Downrange Distance Relative to CSM (km, negative = behind CSM)")
    ax.set_ylabel("Radial Altitude Difference Relative to CSM, z = r_LM - r_CSM (km)")
    ax.legend(loc="lower right", fontsize=8.2)

    save(fig, "lm_03_lvlh_trajectory")


def plot_kalman_convergence(sim: dict) -> None:
    """Plot 2: Navigation error & W-matrix uncertainty shrinking as RR marks come in."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 7.0), sharex=True)
    marks = sim["mark_idx"]

    # Panel 1: Position error & 1-sigma envelope from W*W^T
    ax1.plot(
        marks,
        sim["pos_err_actual"],
        color="#1f77b4",
        marker="o",
        ms=4.5,
        lw=2.0,
        label="Actual Position Error ||r_est - r_true|| (m)",
    )
    ax1.plot(
        marks,
        sim["pos_sigma"],
        color="#d62728",
        ls="--",
        lw=2.0,
        label="Potter W-Matrix 1-sigma Position Uncertainty sqrt(tr(W_r W_r^T)/3) (m)",
    )
    ax1.fill_between(marks, 0.0, sim["pos_sigma"], color="#d62728", alpha=0.10)
    ax1.annotate(
        "WLINIT (WRENDPOS = 1500 m)\nbefore first RR mark",
        xy=(0, sim["pos_sigma"][0]),
        xytext=(3.2, sim["pos_sigma"][0] * 0.82),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#d62728"},
    )
    ax1.annotate(
        "Each R22LEM mark incorporates:\n1. Range (RM)\n2. Range-rate (RDOTM)\n3. Shaft & Trunnion angles\nvia INCORP1 / INCORP2",
        xy=(6, sim["pos_err_actual"][6]),
        xytext=(10.5, 580.0),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#1f77b4"},
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#cccccc"},
    )
    ax1.set_ylabel("Position Error / Uncertainty (m)")
    ax1.set_title("P20/R22 Rendezvous Navigation: Potter Square-Root W-Matrix Filter (INCORP1 / INCORP2)")
    ax1.legend(loc="upper right", fontsize=8.5)

    # Panel 2: Velocity error & 1-sigma envelope from W*W^T
    ax2.plot(
        marks,
        sim["vel_err_actual"],
        color="#2ca02c",
        marker="s",
        ms=4.5,
        lw=2.0,
        label="Actual Velocity Error ||v_est - v_true|| (m/s)",
    )
    ax2.plot(
        marks,
        sim["vel_sigma"],
        color="#9467bd",
        ls="--",
        lw=2.0,
        label="Potter W-Matrix 1-sigma Velocity Uncertainty sqrt(tr(W_v W_v^T)/3) (m/s)",
    )
    ax2.fill_between(marks, 0.0, sim["vel_sigma"], color="#9467bd", alpha=0.10)
    ax2.set_ylabel("Velocity Error / Uncertainty (m/s)")
    ax2.set_xlabel("Rendezvous Radar Tracking Mark Count (TRKMKCNT, ~1 mark/min in R22LEM)")
    ax2.legend(loc="upper right", fontsize=8.5)

    save(fig, "lm_03_kalman_filter")


def main() -> None:
    """Narrate and simulate the Apollo 11 Lunar Module rendezvous & W-matrix navigation."""
    sim = simulate_rendezvous()
    burns = sim["burns"]

    step(
        1,
        "Coelliptic Sequence Initiation near Apolune: P32 CSI & P33 CDH (CSI/A -> CSI/B -> CDHMVR)",
        f"Source: {src('Luminary099/P32-P35_P72-P75.agc', 'CSI/B')} & "
        f"{src('Luminary099/P32-P35_P72-P75.agc', 'CDHMVR')}\n"
        "While Columbia (CSM) orbits in a ~60 NM (111.1 km) circular orbit, Eagle is inserted into\n"
        "roughly a 9 x 45 NM (~16.9 x 81.5 km) orbit and coasts up to near first apolune.\n"
        f"There, P32 (CSI/B) burns posigrade DV_CSI = +{burns['dv_csi']:.2f} m/s (+{burns['dv_csi']*3.28084:.1f} ft/s;\n"
        "approx. Apollo 11: ~16 m/s / 51 ft/s) to raise the opposite apsis to Delta-h = -27.78 km\n"
        f"(-15 NM) below the CSM. Half an orbit ({burns['t_csi_to_cdh']/60.0:.1f} min) later at CDH,\n"
        f"P33 (CDHMVR) executes a small trim DV_CDH = {burns['dv_cdh']:+.2f} m/s ({burns['dv_cdh']*3.28084:+.1f} ft/s;\n"
        "approx. Apollo 11: a few ft/s) so the two orbits become coelliptic.",
    )

    step(
        2,
        "P20/R22 Rendezvous Radar & Potter's W-Matrix Filter (LSR22.3 -> INCORP1 -> INCORP2)",
        f"Source: {src('Luminary099/P20-P25.agc', 'LSR22.3')} & "
        f"{src('Luminary099/MEASUREMENT_INCORPORATION.agc', 'INCORP1')}\n"
        "While coasting in P20, R22LEM takes automatic Rendezvous Radar marks every ~1 minute.\n"
        "(Note: KALMAN_FILTER.agc @ RATELOOP is the DAP jet-torque filter; the orbital state-vector\n"
        "Kalman filter is in MEASUREMENT_INCORPORATION.agc @ INCORP1 & INCORP2.)\n"
        "Instead of storing covariance P, the AGC stores its square root W (P = W W^T).\n"
        "For each scalar measurement (range, range-rate, shaft, trunnion), INCORP1 computes\n"
        "z = W^T b, A = z^T z + variance, gamma = 1/(A + sqrt(A*variance)), omega = W z, and\n"
        "DELTAX = (DELTAQ/A)*omega; INCORP2 updates W <- W - gamma * omega * z^T.\n"
        f"Across {len(sim['mark_idx'])-1} marks, position error shrinks from "
        f"{sim['pos_err_actual'][0]:.0f} m to {sim['pos_err_actual'][-1]:.1f} m.",
    )

    step(
        3,
        "Transfer Phase Initiation (P34) at E = 26.6 deg & Midcourse / Braking (P35)",
        f"Source: {src('Luminary099/P34-35_P74-75.agc', 'ELCALC')} & "
        f"{src('Luminary099/P34-35_P74-75.agc', 'S34/35.2')}\n"
        "In the lower coelliptic orbit, the LM catches up to the CSM at ~2.7 deg/min.\n"
        f"S33/34.1 (ELCALC) solves for TTPI when the CSM elevation angle reaches ELEV = {ELEV_TPI_DEG:.1f} deg.\n"
        f"S34/35.2 advances the CSM through CENTANG = {CENTANG_TPI_DEG:.0f} deg (130DEG) and computes\n"
        f"the TPI burn |DV_TPI| = {np.linalg.norm(sim['dv_tpi']):.2f} m/s ({np.linalg.norm(sim['dv_tpi'])*3.28084:.1f} ft/s;\n"
        "approx. Apollo 11: ~7.6 m/s / 25 ft/s) along the line of sight, followed by P35 midcourse\n"
        f"trims (TPM-1/TPM-2) and terminal braking |DV_TPF| = {np.linalg.norm(sim['dv_tpf']):.2f} m/s\n"
        f"({np.linalg.norm(sim['dv_tpf'])*3.28084:.1f} ft/s; approx. Apollo 11: ~9.5 m/s / 31 ft/s).",
    )

    plot_lvlh_trajectory(sim)
    plot_kalman_convergence(sim)


if __name__ == "__main__":
    main()
