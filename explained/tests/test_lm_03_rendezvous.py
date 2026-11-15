from __future__ import annotations

import numpy as np

import lm_03_rendezvous as lm03


def test_rendezvous_trajectory_and_potter_filter() -> None:
    sim = lm03.simulate_rendezvous()

    # Rendezvous intercept ends near zero range in CSM LVLH frame
    final_range_km = float(np.hypot(sim["x_tpi_tpf"][-1], sim["z_tpi_tpf"][-1]))
    assert final_range_km <= 0.05  # within 50 m of CSM

    # Navigation error and uncertainty shrink substantially across RR marks
    assert sim["pos_sigma"][-1] < 0.1 * sim["pos_sigma"][0]
    assert sim["vel_sigma"][-1] < 0.2 * sim["vel_sigma"][0]
    assert sim["pos_err_actual"][-1] < 0.1 * sim["pos_err_actual"][0]
    assert sim["vel_err_actual"][-1] < 0.2 * sim["vel_err_actual"][0]


def test_potter_w_matrix_covariance_stays_psd() -> None:
    rng = np.random.default_rng(19690721)
    w_mat = np.diag([
        lm03.W_REND_POS, lm03.W_REND_POS, lm03.W_REND_POS,
        lm03.W_REND_VEL, lm03.W_REND_VEL, lm03.W_REND_VEL,
    ])
    x_true = np.array([-160_000.0, 1_500.0, -27_780.0, 37.1, -0.4, 0.0])
    x_est = x_true + np.array([1_250.0, -680.0, 920.0, -1.35, 0.75, -1.10])

    prev_trace = float(np.trace(w_mat @ w_mat.T))
    for _ in range(10):
        x_est, w_mat = lm03.lsr22_3_radar_mark(x_true, x_est, w_mat, rng)
        cov_p = w_mat @ w_mat.T
        # Symmetry and positive semi-definiteness of P = W @ W.T
        np.testing.assert_allclose(cov_p, cov_p.T, atol=1e-12)
        eigvals = np.linalg.eigvalsh(cov_p)
        assert np.all(eigvals >= -1e-9)
        cur_trace = float(np.trace(cov_p))
        assert cur_trace <= prev_trace
        prev_trace = cur_trace
