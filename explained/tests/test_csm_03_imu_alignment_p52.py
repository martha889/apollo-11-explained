from __future__ import annotations

import numpy as np

import csm_03_imu_alignment_p52 as csm03


def test_gyro_torquing_angles_recover_injected_misalignment() -> None:
    catalog = csm03.decode_star_catalog()
    s1 = catalog[15]  # Sirius
    s2 = catalog[22]  # Regulus

    sep_deg, cross_mag, valid = csm03.score_star_pair(s1["u_ref"], s2["u_ref"])
    assert valid is True
    assert 30.0 <= sep_deg <= 150.0
    assert cross_mag > 0.5

    drift_deg_true = np.array([1.15, -0.78, 0.92])
    r_sm_true_from_ref = csm03.euler_xyz_matrix(np.radians(drift_deg_true))
    r_nb_from_sm_true = csm03.euler_xyz_matrix(np.radians([12.0, -8.5, 19.0]))

    # Exact (zero-noise) marks recover the misalignment to machine precision
    u1_sm_exact, _, _ = csm03.simulate_sextant_marks(
        s1["u_ref"], r_sm_true_from_ref, r_nb_from_sm_true, n_marks=5, noise_arcsec=0.0
    )
    u2_sm_exact, _, _ = csm03.simulate_sextant_marks(
        s2["u_ref"], r_sm_true_from_ref, r_nb_from_sm_true, n_marks=5, noise_arcsec=0.0
    )
    r_est_exact, _, _ = csm03.axisgen(s1["u_ref"], s2["u_ref"], u1_sm_exact, u2_sm_exact)
    torq_deg_exact = np.degrees(csm03.calcgta(r_est_exact))
    np.testing.assert_allclose(torq_deg_exact, drift_deg_true, rtol=1e-9, atol=1e-9)

    # With realistic 10-arcsec sextant noise, Noun 05 passes and residual is a few arcsec
    rng = np.random.default_rng(19690720)
    u1_sm_noisy, _, _ = csm03.simulate_sextant_marks(
        s1["u_ref"], r_sm_true_from_ref, r_nb_from_sm_true, n_marks=5, noise_arcsec=10.0, rng=rng
    )
    u2_sm_noisy, _, _ = csm03.simulate_sextant_marks(
        s2["u_ref"], r_sm_true_from_ref, r_nb_from_sm_true, n_marks=5, noise_arcsec=10.0, rng=rng
    )
    _, _, diff_deg, dsky_n05 = csm03.check_star_angle_difference(
        s1["u_ref"], s2["u_ref"], u1_sm_noisy, u2_sm_noisy
    )
    assert diff_deg <= 0.02
    assert dsky_n05 <= 2

    r_est_noisy, _, _ = csm03.axisgen(s1["u_ref"], s2["u_ref"], u1_sm_noisy, u2_sm_noisy)
    torq_deg_noisy = np.degrees(csm03.calcgta(r_est_noisy))
    np.testing.assert_allclose(torq_deg_noisy, drift_deg_true, atol=0.01)
