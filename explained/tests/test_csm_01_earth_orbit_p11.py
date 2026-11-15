from __future__ import annotations

import numpy as np

import csm_01_earth_orbit_p11 as csm01


def test_initialize_p11_pad_state() -> None:
    rn1, vn1, refsmmat = csm01.initialize_p11_pad_state()
    assert np.isclose(np.linalg.norm(rn1), csm01.R_PAD, rtol=1e-9)
    # Earth rotation speed at 28.6 deg latitude ~ 408 m/s
    assert 400.0 <= np.linalg.norm(vn1) <= 420.0
    # REFSMMAT is a right-handed orthonormal matrix
    np.testing.assert_allclose(refsmmat @ refsmmat.T, np.eye(3), atol=1e-12)
    assert np.isclose(np.linalg.det(refsmmat), 1.0, atol=1e-12)


def test_saturn_v_ascent_insertion_orbit() -> None:
    sim = csm01.simulate_saturn_v_ascent()
    assert np.isclose(sim["t"][-1], 700.0)
    # Insertion altitude near 185.2 km (100 NM)
    assert 183.0 <= sim["alt_km"][-1] <= 187.0
    assert 99.0 <= sim["alt_nm"][-1] <= 101.0
    # Insertion inertial speed near 7.8 km/s
    assert 7_750.0 <= sim["vi_m_s"][-1] <= 7_850.0
    # Near-zero radial speed and flight-path angle at circular orbit insertion
    assert abs(sim["hdot_m_s"][-1]) <= 2.0
    assert abs(sim["gamma_deg"][-1]) <= 0.2
