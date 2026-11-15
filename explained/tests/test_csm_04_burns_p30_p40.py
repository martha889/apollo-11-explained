from __future__ import annotations

import numpy as np

from common import MU_MOON, R_MOON
import csm_04_burns_p30_p40 as csm04


def test_loi1_burn_captures_into_bound_lunar_orbit() -> None:
    h_p_target = 112_786.8
    r_p = R_MOON + h_p_target
    v_hyp_peri = 2_556.8
    r_peri_nom = np.array([r_p, 0.0, 0.0])
    v_peri_nom = np.array([0.0, v_hyp_peri, 0.0])

    # Back-propagate 193 s before perilune to TIG
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
    m0_docked_kg = 43_700.0
    delv_lv = np.array([-889.0, 0.0, 0.0])

    p30_data = csm04.p30_external_delta_v(
        r_tig, v_tig, delv_lv, m0_docked_kg, r_peri_nom=r_peri_nom, v_peri_nom=v_peri_nom
    )
    assert np.isclose(p30_data["dv_mag"], 889.0, atol=1e-6)

    history = csm04.simulate_p40_burn(r_tig, v_tig, p30_data, m0_docked_kg)
    post_orb = csm04.compute_orbit_apsides(history["r"][-1], history["v"][-1])

    # Bound elliptical lunar orbit
    assert post_orb["a"] > 0.0
    assert 0.0 < post_orb["e"] < 1.0

    # Impulsive preview at perilune gives ~304.4 x 112.8 km; finite 6-min P40 burn gives ~315.4 x 104.6 km
    assert 300.0 <= p30_data["post_orb_perilune"]["h_apo_m"] / 1e3 <= 320.0
    assert 110.0 <= p30_data["post_orb_perilune"]["h_peri_m"] / 1e3 <= 115.0

    h_apo_km = post_orb["h_apo_m"] / 1e3
    h_peri_km = post_orb["h_peri_m"] / 1e3
    assert 310.0 <= h_apo_km <= 320.0
    assert 104.0 <= h_peri_km <= 115.0

    # Sensed delta-v near 889 m/s and residual VGO near zero
    assert 887.0 <= history["dv_total"][-1] <= 891.0
    assert history["vgo_mag"][-1] <= 0.1
