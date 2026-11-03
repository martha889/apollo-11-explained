"""Run the complete Apollo 11 AGC mission walkthrough in chronological order.

Usage (from repository root):
  python explained/mission.py              # Run prologue + all mission phases
  python explained/mission.py --no-intro   # Skip agc_00..agc_03 prologue, run flight phases only
  python explained/mission.py --list       # List all phases with GET and module names
  python explained/mission.py --only lm_02 # Run a single phase by module prefix, name, or number
"""
from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


@dataclass(frozen=True)
class PhaseSpec:
    idx: int
    short_id: str
    module_name: str
    is_intro: bool
    title: str
    get_str: str
    agc_programs: str
    summary: str


PHASES: list[PhaseSpec] = [
    PhaseSpec(
        idx=1,
        short_id="agc_00",
        module_name="agc_00_numbers",
        is_intro=True,
        title="Prologue 0: AGC Number Representation & Fixed-Point Scaling",
        get_str="PRE-LAUNCH (Architecture)",
        agc_programs="SP / DP / B-n Fixed-Point",
        summary=(
            "How the Block II AGC represents physical quantities without floating-point "
            "hardware using 15-bit ones'-complement words, +0/-0 sentinels, and B-n binary scaling."
        ),
    ),
    PhaseSpec(
        idx=2,
        short_id="agc_01",
        module_name="agc_01_executive_waitlist",
        is_intro=True,
        title="Prologue 1: Executive, Waitlist, Phase Tables & 1201/1202 Alarms",
        get_str="PRE-LAUNCH / 102:38 GET",
        agc_programs="EXEC / WAITLIST / BAILOUT",
        summary=(
            "The priority-scheduled multitasking OS (8 Core Sets, 5 VACs), T3RUPT timer queue, "
            "and how phase-table restart checkpoints saved the landing during the 1202/1201 alarms."
        ),
    ),
    PhaseSpec(
        idx=3,
        short_id="agc_02",
        module_name="agc_02_interpreter",
        is_intro=True,
        title="Prologue 2: Hal Laning's Vector/Matrix Bytecode Interpreter",
        get_str="PRE-LAUNCH (Architecture)",
        agc_programs="INTPRET / RGVGCALC",
        summary=(
            "The stack-based virtual machine that packs two 7-bit vector/matrix opcodes per word, "
            "traced step-by-step on the Lunar Module's RGVGCALC landing guidance routine."
        ),
    ),
    PhaseSpec(
        idx=4,
        short_id="agc_03",
        module_name="agc_03_dsky",
        is_intro=True,
        title="Prologue 3: PINBALL GAME BUTTONS AND LIGHTS (The DSKY Interface)",
        get_str="PRE-LAUNCH / 102:38 GET",
        agc_programs="PINBALL / V16N68 / V05N09",
        summary=(
            "How astronauts talked to the AGC via two-digit Verbs and Nouns on the DSKY keypad "
            "and electroluminescent display during P63 braking and the 1202 alarm inspection."
        ),
    ),
    PhaseSpec(
        idx=5,
        short_id="csm_01",
        module_name="csm_01_earth_orbit_p11",
        is_intro=False,
        title="Phase 1: Saturn V Launch & Earth Orbit Insertion Monitor",
        get_str="000:00:00 - 000:11:49 GET",
        agc_programs="Comanche055 P11",
        summary=(
            "While the Saturn V Instrument Unit steers the booster to a 100 NM parking orbit, "
            "the CMC integrates PIPA accelerations every 2 s (Noun 62) and drives FDAI attitude needles."
        ),
    ),
    PhaseSpec(
        idx=6,
        short_id="csm_02",
        module_name="csm_02_conics_coast",
        is_intro=False,
        title="Phase 2: Translunar Coast, Universal Kepler/Lambert & Encke Integration",
        get_str="002:50:00 - 075:49:00 GET",
        agc_programs="Comanche055 P00 / P20 / Conics",
        summary=(
            "Across the 3-day coast from TLI to the Moon, the CMC propagates state vectors via "
            "Encke's method, rectifies reference conics, and switches origin at the Moon's SOI."
        ),
    ),
    PhaseSpec(
        idx=7,
        short_id="csm_03",
        module_name="csm_03_imu_alignment_p52",
        is_intro=False,
        title="Phase 3: Inflight Optical Star Sightings & IMU Realignment",
        get_str="~073:30:00 GET (Pre-LOI & Pre-Burn)",
        agc_programs="Comanche055 P52",
        summary=(
            "Collins sights two catalog stars (Sirius & Regulus) through the 28x Sextant, checks "
            "Star Angle Difference (Noun 05), and torques the drifted IMU platform back to REFSMMAT."
        ),
    ),
    PhaseSpec(
        idx=8,
        short_id="csm_04",
        module_name="csm_04_burns_p30_p40",
        is_intro=False,
        title="Phase 4: Lunar Orbit Insertion (LOI-1) Targeting & SPS Burn",
        get_str="075:49:50 - 075:55:48 GET",
        agc_programs="Comanche055 P30 / P40",
        summary=(
            "Behind the lunar far side, P30 transforms the Local Vertical delta-V target and P40 "
            "steers a 6-minute retrograde SPS burn via cross-product steering into a 313x111 km orbit."
        ),
    ),
    PhaseSpec(
        idx=9,
        short_id="lm_01",
        module_name="lm_01_powered_descent",
        is_intro=False,
        title="Phase 5: Eagle Powered Descent & Touchdown at Tranquility Base",
        get_str="102:33:05 - 102:45:40 GET",
        agc_programs="Luminary099 P63 / P64 / P66",
        summary=(
            "Eagle throttles up for P63 braking, blends Landing Radar updates, rides through 1202/1201 "
            "alarms into P64 approach, and lands manually under P66 Rate-of-Descent control."
        ),
    ),
    PhaseSpec(
        idx=10,
        short_id="lm_02",
        module_name="lm_02_ascent_p12",
        is_intro=False,
        title="Phase 6: Eagle Liftoff from the Moon & Powered Ascent",
        get_str="124:22:00 - 124:29:15 GET",
        agc_programs="Luminary099 P12",
        summary=(
            "The Ascent Stage rises vertically to clear the descent stage, pitches over, and uses "
            "ATMAG 1/DV mass filtering and linear-tangent guidance to reach a 17x83 km lunar orbit."
        ),
    ),
    PhaseSpec(
        idx=11,
        short_id="lm_03",
        module_name="lm_03_rendezvous",
        is_intro=False,
        title="Phase 7: Lunar Orbit Rendezvous & Potter Square-Root Kalman Filter",
        get_str="125:19:00 - 128:03:00 GET",
        agc_programs="Luminary099 P20 / P32 / P33 / P34 / P35",
        summary=(
            "Eagle tracks Columbia with the Rendezvous Radar, updates Potter's W-matrix square-root "
            "covariance filter, and flies the CSI -> CDH -> TPI -> TPF coelliptic rendezvous sequence."
        ),
    ),
    PhaseSpec(
        idx=12,
        short_id="csm_05",
        module_name="csm_05_entry_p61_p67",
        is_intro=False,
        title="Phase 8: Earth Atmospheric Entry & Double-Pulse Skip Guidance",
        get_str="195:03:05 - 195:18:35 GET",
        agc_programs="Comanche055 P61 / P63 / P64 / P65 / P66 / P67",
        summary=(
            "Hitting Entry Interface at 11.03 km/s, Columbia modulates its lift vector via bank angle "
            "(ROLLC) across P63-P67 to fly a double-pulse skip entry to Pacific splashdown."
        ),
    ),
]


def print_banner(phase: PhaseSpec) -> None:
    """Print a prominent mission-phase banner with GET and astronaut/AGC context."""
    bar = "#" * 78
    sub = "-" * 78
    print(f"\n{bar}")
    print(f"# [{phase.idx:02d}/{len(PHASES):02d}] {phase.title}")
    print(f"# {sub[2:]}")
    print(f"#   Mission Elapsed Time (GET) : {phase.get_str}")
    print(f"#   AGC Software / Program(s)  : {phase.agc_programs}")
    print(f"#   Python Translation Module  : explained/{phase.module_name}.py")
    print(f"#   What's Happening           : {phase.summary}")
    print(f"{bar}")


def print_phase_list() -> None:
    """Print a table of all available prologue and flight phases."""
    print("Apollo 11 AGC Mission Walkthrough Phases:")
    print("=" * 96)
    print(f"{'#':<4} {'Short ID':<10} {'Module Name':<28} {'Approx. GET':<26} {'AGC Program(s)'}")
    print("-" * 96)
    for p in PHASES:
        tag = f"{p.idx:2d}"
        print(f"{tag:<4} {p.short_id:<10} {p.module_name:<28} {p.get_str:<26} {p.agc_programs}")
    print("=" * 96)


def resolve_only_target(query: str) -> list[PhaseSpec]:
    """Match --only <module_name_or_number> against phase index, short_id, or module_name."""
    q = query.strip()
    if q.endswith(".py"):
        q = q[:-3]
    q_lower = q.lower()

    # Check integer index (1..12)
    if q.isdigit():
        idx_val = int(q)
        for p in PHASES:
            if p.idx == idx_val:
                return [p]

    # Exact match on short_id or module_name
    for p in PHASES:
        if q_lower in (p.short_id.lower(), p.module_name.lower()):
            return [p]

    # Prefix or substring match
    matches = [
        p for p in PHASES
        if p.module_name.lower().startswith(q_lower) or q_lower in p.module_name.lower()
    ]
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Apollo 11 AGC explained Python walkthroughs in mission order."
    )
    parser.add_argument(
        "--no-intro",
        action="store_true",
        help="Skip the agc_00..agc_03 'How the computer works' prologue.",
    )
    parser.add_argument(
        "--only",
        metavar="MODULE_OR_NUM",
        help="Run only one phase (e.g., --only lm_02, --only lm_02_ascent_p12, or --only 10).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all prologue and mission phases and exit.",
    )
    args = parser.parse_args(argv)

    if args.list:
        print_phase_list()
        return 0

    if args.only:
        selected = resolve_only_target(args.only)
        if not selected:
            print(f"ERROR: Unknown phase '{args.only}'. Use --list to see valid phases.", file=sys.stderr)
            return 2
        if len(selected) > 1:
            names = ", ".join(p.module_name for p in selected)
            print(f"ERROR: Ambiguous phase '{args.only}' matches: {names}", file=sys.stderr)
            return 2
    else:
        selected = [p for p in PHASES if not (args.no_intro and p.is_intro)]

    failures: list[tuple[PhaseSpec, Exception]] = []

    for phase in selected:
        print_banner(phase)
        try:
            mod = importlib.import_module(phase.module_name)
            mod.main()
        except Exception as exc:  # noqa: BLE001
            failures.append((phase, exc))
            print(f"\n[ERROR] Phase {phase.module_name} failed with {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc()

    print("\n" + "=" * 78)
    if failures:
        print(f"MISSION WALKTHROUGH COMPLETED WITH {len(failures)} FAILURE(S):")
        for phase, exc in failures:
            print(f"  - [{phase.idx:02d}] {phase.module_name}: {type(exc).__name__}: {exc}")
        print("=" * 78)
        return 1

    print(f"MISSION WALKTHROUGH SUCCEEDED ({len(selected)}/{len(selected)} phase(s) completed, all figures saved).")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
