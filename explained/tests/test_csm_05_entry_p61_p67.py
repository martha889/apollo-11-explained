from __future__ import annotations

import numpy as np

import csm_05_entry_p61_p67 as csm05


def test_lunar_return_entry_peak_g_and_target_range() -> None:
    target_range_km = 2_320.0
    history, transitions, steeroff_event = csm05.simulate_lunar_return_entry(
        v_ei_ms=11_032.0, gamma_ei_deg=-6.38, target_range_km=target_range_km
    )

    peak_g = float(np.max(history["g_load"]))
    assert 6.0 <= peak_g <= 7.0

    # Ends near the target downrange distance
    final_range_km = float(history["downrange_km"][-1])
    assert abs(final_range_km - target_range_km) <= 25.0

    # Verify entry guidance phases progress through P63 -> P64 -> P65 -> P66 -> P67 -> STEEROFF
    phase_seq = []
    for p in history["phase"]:
        if not phase_seq or phase_seq[-1] != p:
            phase_seq.append(p)
    assert phase_seq == ["P63", "P64", "P65", "P66", "P67", "STEEROFF"]
    assert steeroff_event is not None


def test_decode_agc_vrefer_table() -> None:
    vref = csm05.decode_agc_vrefer_table()
    assert len(vref["v_ms"]) == 13
    # Velocities in VREFER are monotonically increasing
    assert np.all(np.diff(vref["v_ms"]) > 0)
