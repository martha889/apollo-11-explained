"""The AGC Executive, Waitlist, Phase Tables, and the Apollo 11 1201/1202 Alarms.

The AGC operating system fits in ~1,000 words of assembly and consists of:
  1. The Executive (`Luminary099/EXECUTIVE.agc`): a cooperative/preemptive priority
     scheduler managing 8 Core Sets (12 words each) and 5 Vector Accumulator (VAC)
     areas (44 words each).
  2. The Waitlist (`Luminary099/WAITLIST.agc`): a delta-time interrupt queue driven
     by the `TIME3` counter overflow (`T3RUPT`), holding up to 9 timed tasks.
  3. Phase Tables & Restart Protection (`Luminary099/PHASE_TABLE_MAINTENANCE.agc`,
     `RESTARTS_ROUTINE.agc`, `ALARM_AND_ABORT.agc`, `FRESH_START_AND_RESTART.agc`):
     checkpointing critical mission phases across 6 groups so a `BAILOUT` software
     restart can wipe overloaded queues and immediately resume guidance.

This module translates those three subsystems into readable Python and reproduces
the Apollo 11 lunar landing `1202` (Executive overflow - no core sets) and `1201`
(Executive overflow - no VAC areas) alarms caused by Rendezvous Radar CDU pulses
stealing ~15% of the CPU time.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from common import save, src, step

MAX_CORESETS = 8   # Core Set 0 (running) + 7 background sets (NO.CORES DEC 7)
MAX_VACS = 5       # VAC1USE .. VAC5USE (5 vector work areas of 44 words each)
MAX_WAITLIST = 9   # LST1 (8 delta-Ts) + TIME3 = 9 tasks in LST2
TIME3_MODULO = 16384  # 14-bit counter ticking every 10 ms (1 centisecond)


@dataclass
class CoreSet:
    """One 12-word AGC Core Set (`MPAC..MPAC+6, MODE, LOC, BANKSET, PUSHLOC, PRIORITY`).

    Original AGC reference: `src("Luminary099/ERASABLE_ASSIGNMENTS.agc", "MPAC")`
    """
    slot: int
    name: str = ""
    priority: Optional[int] = None   # None represents -0 (OCT 77777 = available!)
    vac_id: Optional[int] = None     # 1..5 if allocated via FINDVAC, None if NOVAC
    work_Remaining_cs: float = 0.0   # Remaining CPU centiseconds needed to finish
    group: int = 0                   # Restart phase group (1..6, or 0 if unprotected)


@dataclass
class WaitlistTask:
    """One timed task in `LST1`/`LST2` awaiting `TIME3` overflow (`T3RUPT`)."""
    due_cs: int
    name: str
    callback: Callable[[], None]


@dataclass
class PhaseEntry:
    """One of the 6 restart groups (`-PHASE1/PHASE1` .. `-PHASE6/PHASE6`).

    Original AGC reference: `src("Luminary099/PHASE_TABLE_MAINTENANCE.agc", "PHASCHNG")`
    """
    group: int
    phase_code: int
    job_name: str
    priority: int
    needs_vac: bool
    work_cs: float
    complement_phase: int = field(init=False)

    def __post_init__(self) -> None:
        # The AGC stores -PHASE and +PHASE in adjacent words and checks their XOR on restart
        self.complement_phase = (~self.phase_code) & 0o77777


class AGCSystem:
    """Readable Python translation of the AGC Executive, Waitlist, and Restart logic."""

    def __init__(self, rr_steal_fraction: float = 0.0,rr_start_cs: int = 200) -> None:
        self.time_cs: int = 0
        self.rr_steal_fraction = rr_steal_fraction
        self.rr_start_cs = rr_start_cs

        # 8 Core Sets; PRIORITY = None represents -0 (available)
        self.cores: list[CoreSet] = [CoreSet(slot=i) for i in range(MAX_CORESETS)]
        # 5 VAC areas; True = available (nonzero in VACnUSE), False = reserved (+0)
        self.vac_available: dict[int, bool] = {i: True for i in range(1, MAX_VACS + 1)}

        # Waitlist state: TIME3, LST1 (delta-T), LST2 (task callbacks)
        self.waitlist_q: list[WaitlistTask] = []
        self.time3: int = 0o37777
        self.lst1: list[int] = []
        self.lst2: list[str] = []

        # Restart & Alarm registers
        self.failreg: list[int] = [0, 0, 0]  # 3 alarm code registers
        self.prog_alarm_light: bool = False
        self.redoctr: int = 0                # Restart counter (REDOCTR)
        self.phase_table: dict[int, PhaseEntry] = {}

        # Telemetry history for plotting
        self.history_t: list[float] = []
        self.history_running_job: list[str] = []
        self.history_running_prio: list[int] = []
        self.history_cores_used: list[int] = []
        self.history_vacs_used: list[int] = []
        self.alarm_events: list[tuple[float, int, str]] = []
        self.t3rupt_events: list[tuple[float, str]] = []
        self.phaschng_events: list[tuple[float, int, int, str]] = []

    # ------------------------------------------------------------------
    # WAITLIST: timed interrupt tasks (`WAITLIST.agc`)
    # ------------------------------------------------------------------
    def waitlist(self, delta_t_cs: int, name: str, callback: Callable[[], None]) -> None:
        """Schedule a task to execute in `delta_t_cs` centiseconds via `TIME3`/`T3RUPT`.

        Original AGC reference:
          * `src("Luminary099/WAITLIST.agc", "WAITLIST")`
          * `src("Luminary099/WAITLIST.agc", "WAIT2")`
          * Overflow alarm 01203: `src("Luminary099/WAITLIST.agc", "FILLED")`
        """
        assert 1 <= delta_t_cs <= 16250, "WAITLIST requires 1 <= DT <= 16250 cs"
        if len(self.waitlist_q) >= MAX_WAITLIST:
            self.bailout(0o01203, f"WAITLIST overflow scheduling {name}")
            return

        due = self.time_cs + delta_t_cs
        self.waitlist_q.append(WaitlistTask(due_cs=due, name=name, callback=callback))
        self.waitlist_q.sort(key=lambda t: t.due_cs)
        self._rebuild_lst1_lst2()

    def _rebuild_lst1_lst2(self) -> None:
        """Maintain the AGC's exact `TIME3 = 16384 - (T1 - T)` and `LST1 = -(Tn+1 - Tn) + 1`."""
        if not self.waitlist_q:
            self.time3 = 0o37777
            self.lst1 = [-8192] * 8
            self.lst2 = ["ENDTASK"] * 9
            return
        t1_dt = max(1, self.waitlist_q[0].due_cs - self.time_cs)
        self.time3 = TIME3_MODULO - t1_dt
        self.lst1 = []
        for i in range(len(self.waitlist_q) - 1):
            dt_next = self.waitlist_q[i + 1].due_cs - self.waitlist_q[i].due_cs
            self.lst1.append(-dt_next + 1)
        while len(self.lst1) < 8:
            self.lst1.append(-8192)
        self.lst2 = [t.name for t in self.waitlist_q] + ["ENDTASK"] * (9 - len(self.waitlist_q))

    def t3rupt(self) -> None:
        """Dispatch due Waitlist tasks when `TIME3` overflows (`T3RUPT` -> `TASKOVER`).

        Original AGC reference:
          * `src("Luminary099/WAITLIST.agc", "T3RUPT")`
          * `src("Luminary099/WAITLIST.agc", "TASKOVER")`
        """
        while self.waitlist_q and self.waitlist_q[0].due_cs <= self.time_cs:
            task = self.waitlist_q.pop(0)
            self.t3rupt_events.append((self.time_cs / 100.0, task.name))
            task.callback()
        self._rebuild_lst1_lst2()

    # ------------------------------------------------------------------
    # EXECUTIVE: priority job scheduler (`EXECUTIVE.agc`)
    # ------------------------------------------------------------------
    def findvac(self, name: str, priority: int, work_cs: float, group: int = 0) -> bool:
        """Request a job that needs a 44-word Vector Accumulator (`VAC`) work area.

        Original AGC reference:
          * `src("Luminary099/EXECUTIVE.agc", "FINDVAC")`
          * `src("Luminary099/EXECUTIVE.agc", "FINDVAC2")` -> `BAILOUT1 OCT 1201`
        """
        vac_id = None
        for vid in range(1, MAX_VACS + 1):
            if self.vac_available[vid]:
                vac_id = vid
                self.vac_available[vid] = False
                break
        if vac_id is None:
            self.bailout(0o01201, f"FINDVAC({name}, PRIO {priority:02o}) -> NO VAC AREAS")
            return False
        return self._allocate_coreset(name, priority, work_cs, vac_id=vac_id, group=group)

    def novac(self, name: str, priority: int, work_cs: float, group: int = 0) -> bool:
        """Request a basic-only job that needs no VAC area (`NOVAC`).

        Original AGC reference:
          * `src("Luminary099/EXECUTIVE.agc", "NOVAC")`
          * `src("Luminary099/EXECUTIVE.agc", "NOVAC2")` -> `BAILOUT1 OCT 1202`
        """
        return self._allocate_coreset(name, priority, work_cs, vac_id=None, group=group)

    def _allocate_coreset(
        self, name: str, priority: int, work_cs: float, vac_id: Optional[int], group: int
    ) -> bool:
        """Scan `PRIORITY` registers for `-0` (`NOVAC3`), or trigger `BAILOUT1 OCT 1202`."""
        free_core = next((c for c in self.cores if c.priority is None), None)
        if free_core is None:
            if vac_id is not None:
                self.vac_available[vac_id] = True
            self.bailout(0o01202, f"NOVAC2({name}, PRIO {priority:02o}) -> NO CORE SETS")
            return False

        free_core.name = name
        free_core.priority = priority
        free_core.vac_id = vac_id
        free_core.work_Remaining_cs = work_cs
        free_core.group = group
        self.chang1()  # Check if the new job preempts Core Set 0
        return True

    def chang1(self) -> None:
        """Swap Core Set 0 with the highest-priority active Core Set (`CHANJOB`).

        Original AGC reference:
          * `src("Luminary099/EXECUTIVE.agc", "CHANG1")`
          * `src("Luminary099/EXECUTIVE.agc", "CHANJOB")`
        """
        active = [c for c in self.cores if c.priority is not None]
        if not active:
            return
        best = max(active, key=lambda c: c.priority)
        if best.slot != 0:
            c0 = self.cores[0]
            # Swap contents of Core Set 0 and `best` (just like DXCH MPAC..PRIORITY in CHANJOB)
            (
                c0.name, best.name,
                c0.priority, best.priority,
                c0.vac_id, best.vac_id,
                c0.work_Remaining_cs, best.work_Remaining_cs,
                c0.group, best.group,
            ) = (
                best.name, c0.name,
                best.priority, c0.priority,
                best.vac_id, c0.vac_id,
                best.work_Remaining_cs, c0.work_Remaining_cs,
                best.group, c0.group,
            )

    def priochng(self, new_priority: int) -> None:
        """Change the priority of the currently executing job in Core Set 0.

        Original AGC reference:
          * `src("Luminary099/EXECUTIVE.agc", "PRIOCHNG")`
          * `src("Luminary099/EXECUTIVE.agc", "PRIOCH2")`
        """
        if self.cores[0].priority is not None:
            self.cores[0].priority = new_priority
            self.chang1()

    def endofjob(self) -> None:
        """Release Core Set 0 and its VAC area, then scan for the next highest-priority job.

        Original AGC reference:
          * `src("Luminary099/EXECUTIVE.agc", "ENDOFJOB")`
          * `src("Luminary099/EXECUTIVE.agc", "ENDJOB1")`
          * `src("Luminary099/EXECUTIVE.agc", "EJSCAN")`
          * `src("Luminary099/EXECUTIVE.agc", "DUMMYJOB")`
        """
        c0 = self.cores[0]
        if c0.vac_id is not None:
            self.vac_available[c0.vac_id] = True
        c0.name = ""
        c0.priority = None
        c0.vac_id = None
        c0.work_Remaining_cs = 0.0
        c0.group = 0
        self.chang1()

    # ------------------------------------------------------------------
    # PHASE TABLES, BAILOUT & SOFTWARE RESTART (`ALARM_AND_ABORT.agc`, `RESTARTS_ROUTINE.agc`)
    # ------------------------------------------------------------------
    def phaschng(
        self, group: int, phase_code: int, job_name: str = "",
        priority: int = 0, needs_vac: bool = True, work_cs: float = 0.0
    ) -> None:
        """Record a restart checkpoint in `-PHASEn`/`PHASEn`.

        Original AGC reference:
          * `src("Luminary099/PHASE_TABLE_MAINTENANCE.agc", "PHASCHNG")`
          * `src("Luminary099/SERVICER.agc", "GNUFAZE5")`
        """
        self.phaschng_events.append((self.time_cs / 100.0, group, phase_code, job_name))
        if phase_code == 0:
            self.phase_table.pop(group, None)
        else:
            self.phase_table[group] = PhaseEntry(
                group=group, phase_code=phase_code, job_name=job_name,
                priority=priority, needs_vac=needs_vac, work_cs=work_cs
            )

    def bailout(self, alarm_octal: int, reason: str) -> None:
        """Latch alarm code into `FAILREG`, light `PROG` lamp, and execute `ENEMA` restart.

        Original AGC reference:
          * `src("Luminary099/ALARM_AND_ABORT.agc", "BAILOUT1")`
          * `src("Luminary099/ALARM_AND_ABORT.agc", "CHKFAIL1")`
          * `src("Luminary099/ALARM_AND_ABORT.agc", "WHIMPER")` -> `CADR ENEMA`
        """
        for i in range(3):
            if self.failreg[i] == 0:
                self.failreg[i] = alarm_octal
                break
        else:
            self.failreg[2] = alarm_octal | 0o40000  # Bit 15 = multiple fail indicator
        self.prog_alarm_light = True
        self.alarm_events.append((self.time_cs / 100.0, alarm_octal, reason))
        self.software_restart()

    def software_restart(self) -> None:
        """Wipe all Core Sets and VACs, verify `-PHASE`/`PHASE`, and restart protected groups.

        Original AGC reference:
          * `src("Luminary099/FRESH_START_AND_RESTART.agc", "ENEMA")`
          * `src("Luminary099/FRESH_START_AND_RESTART.agc", "GOPROG3")` (phase table RXOR check)
          * `src("Luminary099/RESTARTS_ROUTINE.agc", "RESTARTS")`
        """
        self.redoctr += 1

        # 1. Clear all 8 Core Sets and all 5 VAC areas (drops low-priority display clutter!)
        for c in self.cores:
            c.name = ""
            c.priority = None
            c.vac_id = None
            c.work_Remaining_cs = 0.0
            c.group = 0
        for vid in self.vac_available:
            self.vac_available[vid] = True

        # 2. Verify Phase Table integrity (`DCA -PHASE1; RXOR LCHAN` in GOPROG3)
        for grp, entry in sorted(self.phase_table.items(), reverse=True):
            assert (entry.phase_code ^ entry.complement_phase) == 0o77777, "PTBAD 01107!"
            # 3. Re-dispatch active phase groups (`RESTARTS` -> `ITSAJOB` / `ITSAWAIT`)
            if entry.work_cs > 0:
                if entry.needs_vac:
                    self.findvac(entry.job_name, entry.priority, entry.work_cs, group=grp)
                else:
                    self.novac(entry.job_name, entry.priority, entry.work_cs, group=grp)

    # ------------------------------------------------------------------
    # STEP SIMULATION BY 1 CENTISECOND (10 ms)
    # ------------------------------------------------------------------
    def step_1cs(self) -> None:
        """Advance clock by 1 centisecond (10 ms), run `T3RUPT` and Execute Core Set 0."""
        self.time_cs += 1
        self.t3rupt()

        # Effective CPU available this centisecond after RR CDU interrupt theft
        cpu_budget = 1.0
        if self.time_cs >= self.rr_start_cs:
            cpu_budget -= self.rr_steal_fraction

        c0 = self.cores[0]
        if c0.priority is not None:
            self.history_running_job.append(c0.name)
            self.history_running_prio.append(c0.priority)
        else:
            self.history_running_job.append("DUMMYJOB")
            self.history_running_prio.append(0)

        self.history_t.append(self.time_cs / 100.0)
        self.history_cores_used.append(sum(1 for c in self.cores if c.priority is not None))
        self.history_vacs_used.append(sum(1 for v in self.vac_available.values() if not v))

        # Burn down work on highest-priority job(s)
        while cpu_budget > 0 and self.cores[0].priority is not None:
            c0 = self.cores[0]
            if c0.work_Remaining_cs <= cpu_budget:
                cpu_budget -= c0.work_Remaining_cs
                # When SERVICER finishes its pre-guidance phase, it spawns LUNLAND (PRIO 21)
                finished_name = c0.name
                self.endofjob()
                if finished_name == "SERVICER":
                    self.phaschng(3, 0o05023, "LUNLAND", priority=0o21, needs_vac=True, work_cs=42.0)
                    self.findvac("LUNLAND", priority=0o21, work_cs=42.0, group=3)
                elif finished_name == "LUNLAND":
                    # End of guidance pass clears Group 3 (`DISPEXIT`) and queues P63/P64 display
                    self.phaschng(3, 0)
                    self.novac("P63DISPS", priority=0o14, work_cs=12.0, group=0)
            else:
                c0.work_Remaining_cs -= cpu_budget
                cpu_budget = 0.0


def run_landing_simulation(
    duration_s: float = 12.0, rr_steal_fraction: float = 0.15, vac_heavy_displays: bool = False
) -> AGCSystem:
    """Simulate the AGC Executive & Waitlist during Lunar Module powered descent (P63/P64).

    Every 2.0 seconds (200 cs):
      * Waitlist task `READACCS` (`src("Luminary099/SERVICER.agc", "READACCS")`) fires,
        sets Group 5 checkpoint (`5.5SPOT`), and queues `SERVICER` (`PRIO20`, `FINDVAC`, 62 cs).
      * When `SERVICER` reaches `LUNLAND` (`src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "LUNLAND")`),
        it sets Group 3 checkpoint (`PRIO21`, `FINDVAC`, 42 cs), which then queues `P63DISPS` (`PRIO14`, 12 cs).
    Every 0.5 seconds (50 cs):
      * Waitlist task `R10,R11` + Digital Autopilot (`1/ACCS`, `PRIO27`, 7 cs) runs.
    Every 1.0 second (100 cs):
      * Crew's `V16 N68` monitor (`MON_V16N68`, `PRIO10`, 9 cs) and background
        radar/display housekeeping (`R52_AUTO`, `PRIO07`, 7 cs) are requested.
      * Normally total CPU load is 88% (176 cs per 200 cs): all jobs finish every cycle!
      * When the Rendezvous Radar steals 15% CPU starting at t = 2.0 s (plus extra RR
        counter-interrupt tasks when overloaded), total demand exceeds 100%: `PRIO10`
        and `PRIO07` jobs starve during `SERVICER`/`LUNLAND`, Core Sets hit 8/8 (`1202`
        alarm) or VACs hit 5/5 (`1201` alarm), and `BAILOUT` triggers a software restart!
    """
    agc = AGCSystem(rr_steal_fraction=rr_steal_fraction, rr_start_cs=200)

    def readaccs_task() -> None:
        # Group 5 checkpoint: protect READACCS + SERVICER
        agc.phaschng(5, 0o05, "SERVICER", priority=0o20, needs_vac=True, work_cs=62.0)
        agc.findvac("SERVICER", priority=0o20, work_cs=62.0, group=5)
        agc.waitlist(200, "READACCS", readaccs_task)

    def dap_r10_task() -> None:
        agc.novac("DAP_R10", priority=0o27, work_cs=7.0, group=2)
        agc.waitlist(50, "R10,R11", dap_r10_task)

    def v16n68_monitor_task() -> None:
        # Under RR CDU interrupt flood, display & radar monitor jobs take longer to complete
        overload_extra = 8.0 if (agc.rr_steal_fraction > 0 and agc.time_cs >= agc.rr_start_cs) else 0.0
        if vac_heavy_displays:
            agc.findvac("MON_V16N68", priority=0o10, work_cs=9.0 + overload_extra, group=0)
            agc.findvac("R52_AUTO", priority=0o07, work_cs=7.0 + overload_extra, group=0)
        else:
            agc.novac("MON_V16N68", priority=0o10, work_cs=9.0 + overload_extra, group=0)
            agc.novac("R52_AUTO", priority=0o07, work_cs=7.0 + overload_extra, group=0)
        agc.waitlist(100, "MON_V16N68", v16n68_monitor_task)

    # Seed the initial Waitlist tasks
    agc.waitlist(1, "READACCS", readaccs_task)
    agc.waitlist(20, "R10,R11", dap_r10_task)
    agc.waitlist(40, "MON_V16N68", v16n68_monitor_task)

    total_cs = int(duration_s * 100)
    for _ in range(total_cs):
        agc.step_1cs()
    return agc


def plot_gantt_timeline(agc: AGCSystem) -> plt.Figure:
    """Plot a Gantt timeline of jobs by priority, showing overload, 1202 alarm, and restart."""
    fig, (ax_gantt, ax_events) = plt.subplots(
        2, 1, figsize=(12.2, 6.8), gridspec_kw={"height_ratios": [3.2, 1.35]}, sharex=True
    )

    job_Order = [
        ("DAP_R10", "DAP & R10/R11 (PRIO 27)", "#7c3aed"),
        ("LUNLAND", "LUNLAND Guidance (PRIO 21, Grp 3)", "#2563eb"),
        ("SERVICER", "SERVICER Nav Loop (PRIO 20, Grp 5)", "#0284c7"),
        ("P63DISPS", "P63/P64 Display (PRIO 14)", "#10b981"),
        ("MON_V16N68", "V16 N68 Monitor (PRIO 10, Unprotected)", "#f59e0b"),
        ("R52_AUTO", "R52 Background (PRIO 07, Unprotected)", "#f97316"),
        ("DUMMYJOB", "DUMMYJOB Idle (Green Light OFF)", "#cbd5e1"),
    ]
    y_map = {key: idx for idx, (key, _, _) in enumerate(job_Order)}
    color_map = {key: col for key, _, col in job_Order}

    # Shade the RR CDU cycle-stealing region
    ax_gantt.axvspan(
        agc.rr_start_cs / 100.0, agc.history_t[-1],
        color="#fee2e2", alpha=0.45,
        label="Rendezvous Radar CDU Pulses Stealing 15% CPU (t ≥ 2.0 s)"
    )

    # Compress contiguous spans for fast, clean Gantt bars
    t_arr = np.array(agc.history_t)
    jobs = agc.history_running_job
    start_idx = 0
    for i in range(1, len(jobs) + 1):
        if i == len(jobs) or jobs[i] != jobs[start_idx]:
            jname = jobs[start_idx]
            if jname in y_map:
                t0 = t_arr[start_idx] - 0.01
                width = t_arr[i - 1] - t0
                y = y_map[jname]
                ax_gantt.barh(
                    y, width, left=t0, height=0.62,
                    color=color_map[jname], edgecolor="none", alpha=0.92
                )
            start_idx = i

    # Mark 1202 Alarm & Software Restart events
    for r_idx, (t_alm, code, _) in enumerate(agc.alarm_events, start=1):
        ax_gantt.axvline(t_alm, color="#dc2626", lw=2.2, ls="--")
        ax_gantt.annotate(
            f"BAILOUT OCT {code:05o}\n(8/8 Core Sets Full!)\n-> ENEMA Restart #{r_idx}\n"
            f"Drops PRIO 07/10/14,\nResumes SERVICER!",
            xy=(t_alm, 4.2), xytext=(t_alm - 2.65, 4.65),
            arrowprops={"arrowstyle": "->", "color": "#dc2626", "lw": 1.5},
            fontsize=8.2, fontweight="bold", color="#991b1b",
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "#fef2f2", "edgecolor": "#dc2626"}
        )

    ax_gantt.set_yticks(range(len(job_Order)))
    ax_gantt.set_yticklabels([label for _, label, _ in job_Order], fontsize=9)
    ax_gantt.invert_yaxis()
    ax_gantt.set_ylabel("AGC Executive Job Priority")
    ax_gantt.set_title(
        "AGC Executive Preemptive Job Timeline: Normal Descent (t < 2s) vs. 15% RR Steal & 1202 Restart",
        fontsize=11.5, fontweight="bold"
    )
    ax_gantt.legend(loc="lower left", fontsize=8.5)

    # Bottom panel: Waitlist T3RUPT dispatches and Phase Table checkpoints
    t_readaccs = [t for t, name in agc.t3rupt_events if name == "READACCS"]
    t_r10 = [t for t, name in agc.t3rupt_events if name == "R10,R11"]
    t_mon = [t for t, name in agc.t3rupt_events if name == "MON_V16N68"]
    t_grp5 = [t for t, grp, code, _ in agc.phaschng_events if grp == 5 and code > 0]
    t_grp3 = [t for t, grp, code, _ in agc.phaschng_events if grp == 3 and code > 0]

    ax_events.scatter(t_readaccs, [2]*len(t_readaccs), marker="^", s=70, color="#0284c7",
                      label="T3RUPT: READACCS (2.0 s)")
    ax_events.scatter(t_r10, [1]*len(t_r10), marker="|", s=55, color="#7c3aed",
                      label="T3RUPT: R10,R11 (0.5 s)")
    ax_events.scatter(t_mon, [0]*len(t_mon), marker="o", s=35, color="#f59e0b",
                      label="T3RUPT: MON_V16N68 (1.0 s)")
    ax_events.scatter(t_grp5, [2.35]*len(t_grp5), marker="D", s=40, color="#0369a1",
                      label="PHASCHNG Grp 5 & Grp 3 Checkpoints")
    ax_events.scatter(t_grp3, [2.35]*len(t_grp3), marker="D", s=40, color="#1d4ed8")

    for t_alm, code, _ in agc.alarm_events:
        ax_events.axvline(t_alm, color="#dc2626", lw=2.0, ls="--")

    ax_events.set_yticks([0, 1, 2])
    ax_events.set_yticklabels(["Waitlist 1.0s", "Waitlist 0.5s", "Waitlist 2.0s\n+ PHASCHNG"], fontsize=8.5)
    ax_events.set_ylim(-0.6, 3.1)
    ax_events.set_xlabel("Mission Simulation Time (seconds)")
    ax_events.legend(loc="upper left", ncol=2, fontsize=8)

    save(fig, "agc_01_gantt_timeline")
    return fig


def plot_coreset_occupancy(
    agc_normal: AGCSystem, agc_1202: AGCSystem, agc_1201: AGCSystem
) -> plt.Figure:
    """Plot Core Set (max 8) and VAC Area (max 5) occupancy over time."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.5, 6.4), sharex=True)

    # Top panel: Core Set Occupancy (1202 Alarm when reaching 8)
    ax1.plot(agc_normal.history_t, agc_normal.history_cores_used,
             color="#16a34a", lw=1.6, alpha=0.85, label="Normal Descent (0% RR steal, ~84% CPU)")
    ax1.plot(agc_1202.history_t, agc_1202.history_cores_used,
             color="#dc2626", lw=2.0, label="Apollo 11 Overload (15% RR CDU steal -> 1202 Alarm)")
    ax1.axhline(MAX_CORESETS, color="#991b1b", ls=":", lw=1.5, label="Max Core Sets (8 = BAILOUT 01202)")

    for t_alm, code, _ in agc_1202.alarm_events:
        ax1.axvline(t_alm, color="#dc2626", ls="--", lw=1.6)
        ax1.annotate(
            f"1202 ALARM (t={t_alm:.2f}s)\n0/8 Core Sets free\n-> Software Restart!",
            xy=(t_alm, MAX_CORESETS), xytext=(t_alm - 2.25, 5.5),
            arrowprops={"arrowstyle": "->", "color": "#dc2626", "lw": 1.4},
            fontsize=8.2, fontweight="bold", color="#991b1b",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "#fef2f2", "edgecolor": "#dc2626"}
        )

    ax1.set_ylabel("Active Core Sets (out of 8)")
    ax1.set_ylim(-0.3, 9.2)
    ax1.set_title(
        "Executive Resource Exhaustion: 1202 (No Core Sets) vs. 1201 (No VAC Areas)",
        fontsize=11.5, fontweight="bold"
    )
    ax1.legend(loc="upper left", fontsize=8.5)

    # Bottom panel: VAC Area Occupancy (1201 Alarm when reaching 5)
    ax2.plot(agc_normal.history_t, agc_normal.history_vacs_used,
             color="#16a34a", lw=1.6, alpha=0.85, label="Normal VAC Occupancy (1–2 VACs used)")
    ax2.plot(agc_1201.history_t, agc_1201.history_vacs_used,
             color="#2563eb", lw=2.0, label="VAC-Heavy Display Load + 15% RR Steal -> 1201 Alarm")
    ax2.axhline(MAX_VACS, color="#1e40af", ls=":", lw=1.5, label="Max VAC Areas (5 = BAILOUT 01201)")

    for idx, (t_alm, code, _) in enumerate(agc_1201.alarm_events):
        ax2.axvline(t_alm, color="#1d4ed8", ls="--", lw=1.6)
        y_box = 3.55 if idx % 2 == 0 else 2.15
        ax2.annotate(
            f"1201 ALARM (t={t_alm:.2f}s)\n0/5 VACs -> Restart",
            xy=(t_alm, MAX_VACS), xytext=(t_alm - 1.85, y_box),
            arrowprops={"arrowstyle": "->", "color": "#1d4ed8", "lw": 1.3},
            fontsize=7.8, fontweight="bold", color="#1e3a8a",
            bbox={"boxstyle": "round,pad=0.22", "facecolor": "#eff6ff", "edgecolor": "#2563eb"}
        )

    ax2.set_ylabel("Active VAC Areas (out of 5)")
    ax2.set_xlabel("Mission Simulation Time (seconds)")
    ax2.set_ylim(-0.3, 6.0)
    ax2.legend(loc="upper left", fontsize=8.5)

    save(fig, "agc_01_coreset_occupancy")
    return fig


def main() -> None:
    """Narrate the Executive/Waitlist architecture and reproduce the 1201/1202 alarms."""
    step(
        1,
        "Executive Priority Scheduler: 8 Core Sets and 5 VAC Areas",
        f"Cited sources: {src('Luminary099/EXECUTIVE.agc', 'FINDVAC')}, "
        f"{src('Luminary099/EXECUTIVE.agc', 'NOVAC')}, "
        f"{src('Luminary099/EXECUTIVE.agc', 'CHANJOB')}\n"
        f"• Each job gets a 12-word Core Set (`MPAC..PRIORITY`); unused slots hold -0 (OCT 77777).\n"
        f"• Jobs using the Interpreter call `FINDVAC` to claim one of 5 44-word VAC areas.\n"
        f"• If all 5 VACs are busy -> `BAILOUT1 OCT 01201`. If all 8 Core Sets are busy -> `BAILOUT1 OCT 01202`."
    )

    step(
        2,
        "Waitlist Timed Task Queue (`TIME3` / `T3RUPT`)",
        f"Cited sources: {src('Luminary099/WAITLIST.agc', 'WAITLIST')}, "
        f"{src('Luminary099/WAITLIST.agc', 'T3RUPT')}, "
        f"{src('Luminary099/SERVICER.agc', 'READACCS')}\n"
        f"• `TIME3` ticks every 10 ms (1 cs) and overflows at 16384 into `T3RUPT`.\n"
        f"• `LST1` stores 8 relative delays `-(T_n+1 - T_n) + 1`; `LST2` stores up to 9 task `2CADR`s.\n"
        f"• Every 200 cs (2.0 s), `READACCS` fires from the Waitlist and spawns the `SERVICER` job."
    )

    agc_normal = run_landing_simulation(duration_s=12.0, rr_steal_fraction=0.0)
    agc_1202 = run_landing_simulation(duration_s=12.0, rr_steal_fraction=0.15, vac_heavy_displays=False)
    agc_1201 = run_landing_simulation(duration_s=12.0, rr_steal_fraction=0.15, vac_heavy_displays=True)

    alm1202_str = ", ".join(f"OCT {c:05o} at t={t:.2f}s" for t, c, _ in agc_1202.alarm_events)
    alm1201_str = ", ".join(f"OCT {c:05o} at t={t:.2f}s" for t, c, _ in agc_1201.alarm_events)
    step(
        3,
        "Reproducing the Apollo 11 1202 and 1201 Alarms & Phase-Table Restart",
        f"Cited sources: {src('Luminary099/ALARM_AND_ABORT.agc', 'BAILOUT1')}, "
        f"{src('Luminary099/FRESH_START_AND_RESTART.agc', 'ENEMA')}, "
        f"{src('Luminary099/RESTARTS_ROUTINE.agc', 'RESTARTS')}, "
        f"{src('Luminary099/PHASE_TABLE_MAINTENANCE.agc', 'PHASCHNG')}\n"
        f"• Normal run (0% RR steal): max Core Sets = {max(agc_normal.history_cores_used)}/8, "
        f"alarms = {len(agc_normal.alarm_events)}\n"
        f"• 15% RR CDU steal (NOVAC displays): {alm1202_str} (REDOCTR = {agc_1202.redoctr})\n"
        f"• 15% RR CDU steal (FINDVAC displays): {alm1201_str} (REDOCTR = {agc_1201.redoctr})\n"
        f"• On each restart, `ENEMA` + `RESTARTS` drops starved `V16N68`/`R52` jobs and immediately "
        f"resumes Group 5 (`SERVICER`) & Group 3 (`LUNLAND`)!"
    )

    step(4, "Saving Gantt Timeline and Core-Set / VAC Occupancy Figures")
    plot_gantt_timeline(agc_1202)
    plot_coreset_occupancy(agc_normal, agc_1202, agc_1201)


if __name__ == "__main__":
    main()
