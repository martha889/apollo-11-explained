from __future__ import annotations

import numpy as np

import lm_01_powered_descent as lm01


def test_powered_descent_phases_and_touchdown() -> None:
    sim = lm01.simulate_powered_descent()

    # Phases go 63 -> 64 -> 66 in order
    phases = sim["phase"]
    unique_ordered = []
    for p in phases:
        if not unique_ordered or unique_ordered[-1] != int(p):
            unique_ordered.append(int(p))
    assert unique_ordered == [63, 64, 66]

    # Touchdown near zero altitude and near the landing site
    assert abs(sim["alt_true"][-1]) <= 5.0
    assert abs(sim["downrange"][-1]) <= 1.0  # within 1 km of target origin

    # Small vertical and horizontal speed at touchdown
    assert -2.0 <= sim["v_vert"][-1] <= 0.0
    assert abs(sim["v_horiz"][-1]) <= 2.0

    # First 26 s held at 10% throttle (ZOOMTIME), followed by full throttle (~94%)
    assert np.all(np.isclose(sim["throttle"][sim["t"] < 26.0], 10.0))
    assert np.max(sim["throttle"]) >= 90.0
