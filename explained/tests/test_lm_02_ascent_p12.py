from __future__ import annotations

import lm_02_ascent_p12 as lm02


def test_ascent_p12_insertion_orbit() -> None:
    sim = lm02.simulate_ascent_p12()

    # Insertion orbit perilune / apolune near 17 x 83 km
    assert 15.0 <= sim["perilune_km"] <= 19.5
    assert 79.0 <= sim["apolune_km"] <= 87.0

    # Cutoff altitude near HINJECT (18.29 km) and horizontal velocity near target (1685.65 m/s)
    assert 17.5 <= sim["alt_km"][-1] <= 19.0
    assert abs(sim["z_dot"][-1] - lm02.VINJ_83KM) <= 5.0
    assert abs(sim["r_dot"][-1] - lm02.RDOT_D_NOM) <= 3.0

    # Initial vertical rise has pitch = 0 deg before pitchover
    assert sim["pitch_deg"][0] == 0.0
    assert sim["pitch_deg"][-1] > 70.0
