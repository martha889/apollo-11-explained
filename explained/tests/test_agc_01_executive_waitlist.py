from __future__ import annotations

import agc_01_executive_waitlist as agc01


def test_normal_landing_load_has_no_alarm() -> None:
    agc = agc01.run_landing_simulation(duration_s=12.0, rr_steal_fraction=0.0, vac_heavy_displays=False)
    assert agc.alarm_events == []
    assert agc.redoctr == 0
    assert agc.prog_alarm_light is False
    assert max(agc.history_cores_used) < agc01.MAX_CORESETS


def test_radar_cycle_stealing_raises_1202_and_high_prio_survives() -> None:
    agc = agc01.run_landing_simulation(duration_s=12.0, rr_steal_fraction=0.15, vac_heavy_displays=False)
    codes = [code for _, code, _ in agc.alarm_events]
    assert 0o01202 in codes
    assert agc.redoctr >= 1
    assert agc.prog_alarm_light is True
    assert agc.failreg[0] == 0o01202

    # High-priority protected jobs (SERVICER in Group 5 and LUNLAND in Group 3)
    # must survive and continue executing after the first 1202 alarm restart
    first_alarm_t = agc.alarm_events[0][0]
    post_alarm_jobs = [
        job for t, job in zip(agc.history_t, agc.history_running_job) if t > first_alarm_t
    ]
    assert "SERVICER" in post_alarm_jobs
    assert "LUNLAND" in post_alarm_jobs
    assert 5 in agc.phase_table


def test_radar_cycle_stealing_with_vac_displays_raises_1201() -> None:
    agc = agc01.run_landing_simulation(duration_s=12.0, rr_steal_fraction=0.15, vac_heavy_displays=True)
    codes = [code for _, code, _ in agc.alarm_events]
    assert 0o01201 in codes
    assert agc.redoctr >= 1
    assert agc.failreg[0] == 0o01201

    first_alarm_t = agc.alarm_events[0][0]
    post_alarm_jobs = [
        job for t, job in zip(agc.history_t, agc.history_running_job) if t > first_alarm_t
    ]
    assert "SERVICER" in post_alarm_jobs
    assert "LUNLAND" in post_alarm_jobs
