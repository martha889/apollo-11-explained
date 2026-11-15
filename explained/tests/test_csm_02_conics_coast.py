from __future__ import annotations

import numpy as np

from common import MU_EARTH, R_EARTH
import csm_02_conics_coast as csm02


def test_kepler_conserves_energy_and_angular_momentum_and_reverses() -> None:
    r0 = np.array([R_EARTH + 185_200.0, 0.0, 0.0])
    v0 = np.array([0.0, 10_842.0, 0.0])
    dt = 6.0 * 3600.0

    e0 = 0.5 * float(np.dot(v0, v0)) - MU_EARTH / float(np.linalg.norm(r0))
    h0 = np.cross(r0, v0)

    r1, v1, hist_fwd = csm02.kepler_propagate(r0, v0, dt, MU_EARTH)
    assert abs(hist_fwd[-1]["err_t"]) <= 1e-6

    e1 = 0.5 * float(np.dot(v1, v1)) - MU_EARTH / float(np.linalg.norm(r1))
    h1 = np.cross(r1, v1)

    assert np.isclose(e1, e0, rtol=1e-9, atol=1e-6)
    np.testing.assert_allclose(h1, h0, rtol=1e-9, atol=1e-3)

    # Propagating backward by -dt returns the start state
    r_back, v_back, hist_back = csm02.kepler_propagate(r1, v1, -dt, MU_EARTH)
    assert abs(hist_back[-1]["err_t"]) <= 1e-6
    np.testing.assert_allclose(r_back, r0, rtol=1e-7, atol=1.0)
    np.testing.assert_allclose(v_back, v0, rtol=1e-7, atol=1e-3)


def test_lambert_reproduces_kepler_arc() -> None:
    r0 = np.array([R_EARTH + 185_200.0, 0.0, 0.0])
    v0 = np.array([0.0, 10_842.0, 0.0])
    dt = 6.0 * 3600.0

    r_target, _, _ = csm02.kepler_propagate(r0, v0, dt, MU_EARTH)
    v1_lamb, lamb_hist = csm02.lambert_solve(
        r0, r_target, dt, MU_EARTH, transfer_less_than_pi=True
    )
    assert abs(lamb_hist[-1]["err_t"]) <= 1e-3
    np.testing.assert_allclose(v1_lamb, v0, rtol=1e-5, atol=1e-2)

    r_check, _, _ = csm02.kepler_propagate(r0, v1_lamb, dt, MU_EARTH)
    assert np.linalg.norm(r_check - r_target) <= 5.0
