"""The DSKY and Verb/Noun Interface (`PINBALL_GAME_BUTTONS_AND_LIGHTS.agc`).

The Apollo Guidance Computer's user interface—christened "PINBALL GAME BUTTONS AND LIGHTS"
by MIT Instrumentation Lab programmers Ramón Alonso, Robert Filene, and Alan Green—communicates
through two-digit decimal **Verbs** (actions) and **Nouns** (data targets) on the Display and
Keyboard unit (**DSKY**).

This module translates the DSKY state machine into readable Python:
  1. Keycode interrupt (`KEYRUPT1` -> `CHARIN` at `PRIO 30`, `NOVAC`) and state machine for
     `VERB`, `NOUN`, `0`–`9`, `ENTR`, `KEY REL`, `PRO`, and `RSET`
  2. Mixed and Normal Noun tables (`NNADTAB`, `NNTYPTAB`, `IDADDTAB` in `PINBALL_NOUN_TABLES.agc`)
  3. The real Apollo 11 crew sequence during P63 Braking (`V16 N68 ENTR`) and the `1202`
     Executive Overflow alarm check (`V05 N09 ENTR` -> `RSET` / `KEY REL`)
  4. ASCII DSKY terminal printout, matplotlib DSKY panel rendering, and reference table of
     Apollo 11 Programs, Verbs, and Nouns.
"""
from dataclasses import dataclass, field
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

from common import save, src, step

# 5-bit keycodes from `src("Luminary099/PINBALL_GAME_BUTTONS_AND_LIGHTS.agc", "CHARIN")`
KEYCODES_OCTAL = {
    "0": 0o20, "1": 0o01, "2": 0o02, "3": 0o03, "4": 0o04,
    "5": 0o05, "6": 0o06, "7": 0o07, "8": 0o10, "9": 0o11,
    "VERB": 0o21, "RSET": 0o22, "KEY REL": 0o31, "+": 0o32,
    "-": 0o33, "ENTR": 0o34, "CLR": 0o36, "NOUN": 0o37,
    "PRO": 0o00,  # PROCEED is read via Channel 32 bit 14 rather than Channel 15
}

# Most important Programs (Major Modes), Verbs, and Nouns on Apollo 11
APOLLO11_REFERENCE = {
    "programs": [
        ("P00", "CMC/LGC Idling", "Fresh start / idle state (`GOTOPOOH`)"),
        ("P12", "Powered Ascent Guidance", "Lunar liftoff to orbit insertion (`P12.agc`)"),
        ("P20", "Rendezvous Navigation", "Radar/optical tracking + Kalman filter (`P20-P25.agc`)"),
        ("P30", "External Delta-V Target", "Pre-burn orbital maneuver targeting (`P30,P37.agc`)"),
        ("P40", "DPS Thrusting", "Descent Propulsion System orbital burns (`P40-P47.agc`)"),
        ("P52", "IMU Realignment", "AOT star sighting platform alignment (`P51-P53.agc`)"),
        ("P63", "Braking Phase (Landing)", "Powered descent ignition to High Gate (`THE_LUNAR_LANDING.agc`)"),
        ("P64", "Approach Phase (Landing)", "High Gate to Low Gate; LPD window redesignation"),
        ("P66", "Rate of Descent (ROD)", "Manual attitude + ROD switch clicks (Armstrong's landing!)"),
        ("P68", "Landing Confirmation", "Touchdown state vector freeze (`LANDJUNK`)"),
    ],
    "verbs": [
        ("V05", "Display Octal 1,2,3", "Show 3 components in octal in R1, R2, R3 (e.g. V05 N09)"),
        ("V06", "Display Decimal", "Snapshot display of 1–3 decimal components in R1–R3"),
        ("V16", "Monitor Decimal (1/sec)", "Re-fetch and update decimal display once per second"),
        ("V21–25", "Load Data into R1–R3", "Operator decimal/octal entry into erasable memory"),
        ("V33", "Proceed without Input", "Continue program defaults (`JAMPROC`)"),
        ("V34", "Terminate Function", "Abort current display/test (`JAMTERM`)"),
        ("V35", "Lamp Test", "Illuminate all DSKY warning lamps & 88888 segments"),
        ("V37", "Change Program (MM)", "Switch Major Mode (`V37 ENTR 63 ENTR` -> P63)"),
        ("V50", "Please Perform", "Flashing checklist prompt (e.g. `00500` LR antenna pos 1)"),
        ("V57", "Permit LR Updates", "Enable Landing Radar altitude/velocity incorporation"),
    ],
    "nouns": [
        ("N09", "FAILREG Alarm Codes", "R1=1st alarm, R2=2nd alarm, R3=3rd/multi alarm (octal)"),
        ("N20", "ICDU Gimbal Angles", "R1=Outer, R2=Inner, R3=Middle IMU CDU angles (deg)"),
        ("N33", "Time of Ignition (TIG)", "R1=00xxx hr, R2=000xx min, R3=0xx.xx sec"),
        ("N43", "Lat / Long / Altitude", "R1=Latitude (deg), R2=Longitude (deg), R3=Altitude (NM)"),
        ("N49", "State Vector Update", "R1=Delta-R (NM), R2=Delta-V (ft/s), R3=Source code"),
        ("N60", "P65/P66 Landing State", "R1=Fwd Vel (ft/s), R2=Alt Rate (ft/s), R3=Calc Alt (ft)"),
        ("N63", "P63 Braking Display", "R1=Total Vel (ft/s), R2=Alt Rate (ft/s), R3=Calc Alt (ft)"),
        ("N64", "P64 Approach Display", "R1=TREDES + LPD Angle (deg), R2=Alt Rate, R3=Calc Alt"),
        ("N66", "Landing Radar Range", "R1=LR Slant Range (ft), R2=LR Antenna Position (1 or 2)"),
        ("N68", "Landing Site & Delta-H", "R1=Slant Range (NM), R2=TGO Braking (m:s), R3=LR-Calc Alt (ft)"),
    ],
}


@dataclass
class DSKYModel:
    """Readable Python state machine of the AGC's PINBALL keyboard and DSKY display.

    Original AGC references:
      * Keyboard interrupt: `src("Luminary099/KEYRUPT_UPRUPT.agc", "KEYRUPT1")`
      * Keycode dispatch: `src("Luminary099/PINBALL_GAME_BUTTONS_AND_LIGHTS.agc", "CHARIN")`
      * Verb/Noun entry: `src("Luminary099/PINBALL_GAME_BUTTONS_AND_LIGHTS.agc", "VERB")`,
        `src("Luminary099/PINBALL_GAME_BUTTONS_AND_LIGHTS.agc", "NOUN")`,
        `src("Luminary099/PINBALL_GAME_BUTTONS_AND_LIGHTS.agc", "ENTER")`
      * Noun tables: `src("Luminary099/PINBALL_NOUN_TABLES.agc", "NNADTAB")`,
        `src("Luminary099/PINBALL_NOUN_TABLES.agc", "IDADDTAB")`
    """
    prog: str = "00"
    verb: str = "00"
    noun: str = "00"
    r1: str = "     "
    r2: str = "     "
    r3: str = "     "
    comp_acty: bool = False
    vn_flash: bool = False

    # 12 Warning/Status Lamps (left bank of DSKY)
    lamps: dict[str, bool] = field(default_factory=lambda: {
        "UPLINK ACTY": False, "TEMP": False,
        "NO ATT": False,      "GIMBAL LOCK": False,
        "STBY": False,        "PROG": False,
        "KEY REL": False,     "RESTART": False,
        "OPR ERR": False,     "TRACKER": False,
        "ALT": False,         "VEL": False,
    })

    # Internal PINBALL registers (`VERBREG`, `NOUNREG`, `CADRSTOR`, `MONSAVE`, `FAILREG`)
    entry_target: str = ""   # "VERB", "NOUN", "MM", or ""
    entry_buf: str = ""
    cadrstor_bg: tuple[str, str, str, str, str] | None = None  # Background interrupted display
    failreg: list[int] = field(default_factory=lambda: [0, 0, 0])
    erasable: dict[str, Any] = field(default_factory=dict)
    key_history: list[str] = field(default_factory=list)

    def set_background_display(self, verb: str, noun: str, r1: str, r2: str, r3: str, flash: bool = False) -> None:
        """Internal AGC routine (`REGODSPR` / `REFLASHR` / `NVSUB`) puts up a display."""
        self.verb = verb
        self.noun = noun
        self.r1 = r1
        self.r2 = r2
        self.r3 = r3
        self.vn_flash = flash
        self.comp_acty = True
        self.cadrstor_bg = (verb, noun, r1, r2, r3)

    def trigger_alarm(self, octal_code: int, restart: bool = True) -> None:
        """Record an alarm in `FAILREG` (`CHKFAIL1`) and light `PROG` (and `RESTART`).

        Original AGC reference: `src("Luminary099/ALARM_AND_ABORT.agc", "CHKFAIL1")`,
        `src("Luminary099/ALARM_AND_ABORT.agc", "PROGLARM")`
        """
        for i in range(3):
            if self.failreg[i] == 0:
                self.failreg[i] = octal_code
                break
        self.lamps["PROG"] = True
        if restart:
            self.lamps["RESTART"] = True

    def press_key(self, key: str) -> None:
        """Process a single DSKY button press via `KEYRUPT1` -> `CHARIN`."""
        assert key in KEYCODES_OCTAL, f"Unknown DSKY key: {key}"
        self.key_history.append(key)

        # In `CHARIN` (lines 466-473 of PINBALL_GAME_BUTTONS_AND_LIGHTS.agc):
        # Any key except RSET turns on KEY REL light if CADRSTOR is holding an internal display
        if self.cadrstor_bg is not None and key not in ("RSET", "KEY REL", "PRO"):
            self.lamps["KEY REL"] = True

        if key == "VERB":
            self.entry_target = "VERB"
            self.entry_buf = ""
            self.verb = "  "  # `2BLANK` blanks the two VERB digits
        elif key == "NOUN":
            self.entry_target = "NOUN"
            self.entry_buf = ""
            self.noun = "  "  # `2BLANK` blanks the two NOUN digits
        elif key in "0123456789":
            if self.entry_target == "VERB":
                self.entry_buf = (self.entry_buf + key)[:2]
                self.verb = f"{self.entry_buf:<2s}"
            elif self.entry_target == "NOUN":
                self.entry_buf = (self.entry_buf + key)[:2]
                self.noun = f"{self.entry_buf:<2s}"
            elif self.entry_target == "MM":
                self.entry_buf = (self.entry_buf + key)[:2]
                self.noun = f"{self.entry_buf:<2s}"
            else:
                self.lamps["OPR ERR"] = True
        elif key == "CLR":
            self.entry_buf = ""
            if self.entry_target == "VERB":
                self.verb = "  "
            elif self.entry_target == "NOUN":
                self.noun = "  "
        elif key == "RSET":
            # `ERROR` (`OCT 22`): turns off OPR ERR, PROG, RESTART lights
            self.lamps["OPR ERR"] = False
            self.lamps["PROG"] = False
            self.lamps["RESTART"] = False
        elif key == "KEY REL":
            # `VBRELDSP` (`OCT 31`): releases keyboard back to interrupted internal display
            self.lamps["KEY REL"] = False
            if self.cadrstor_bg is not None:
                self.verb, self.noun, self.r1, self.r2, self.r3 = self.cadrstor_bg
        elif key == "PRO":
            # `PROCEED`: acknowledges flashing V/N display (`REFLASHR`)
            self.vn_flash = False
        elif key == "ENTR":
            self._execute_enter()

    def press_sequence(self, keys: list[str]) -> None:
        """Press a sequence of DSKY keys in order."""
        for k in keys:
            self.press_key(k)

    def _execute_enter(self) -> None:
        """Execute `ENTPAS0` / `VERBFAN` (`src("Luminary099/PINBALL_GAME_BUTTONS_AND_LIGHTS.agc", "ENTPAS0")`)."""
        if self.entry_target == "MM":
            self.prog = f"{int(self.entry_buf):02d}"
            self.vn_flash = False
            self.entry_target = ""
            return

        self.entry_target = ""
        v = int(self.verb.strip() or "0")
        n = int(self.noun.strip() or "0")

        if v == 37:
            # Verb 37: Change Program (Major Mode) -> flashes V37 and awaits 2-digit MM in NOUN
            self.vn_flash = True
            self.noun = "  "
            self.entry_target = "MM"
            self.entry_buf = ""
            return

        if v == 5 and n == 9:
            # V05 N09: Display Octal 3 Components of FAILREG (`NNADTAB` index 09)
            self.r1 = f" {self.failreg[0]:05o}"
            self.r2 = f" {self.failreg[1]:05o}"
            self.r3 = f" {self.failreg[2]:05o}"
            self.vn_flash = False
            return

        if v in (6, 16) and n == 68:
            # V06 / V16 N68 (`IDADDTAB` index 68: RANGEDSP, TTFDISP, DELTAH)
            # R1: Slant range in 0.1 NM (`POS7`: xxxx.x NM -> +00157 = +15.7 NM)
            # R2: Time-to-go in Braking (`MIN/SEC`: xxBxx -> 04 12 = 04m 12s)
            # R3: LR Alt - Computed Alt (`COMP ALT`: xxxxx. ft -> -02700 ft)
            slant_nm = self.erasable.get("RANGEDSP_NM", 15.7)
            ttf_min, ttf_sec = self.erasable.get("TTFDISP_MS", (4, 12))
            deltah_ft = self.erasable.get("DELTAH_FT", -2700)
            self.r1 = f"{'+' if slant_nm >= 0 else '-'}{abs(int(round(slant_nm * 10))):05d}"
            self.r2 = f" {ttf_min:02d} {ttf_sec:02d}"
            self.r3 = f"{'+' if deltah_ft >= 0 else '-'}{abs(int(round(deltah_ft))):05d}"
            self.vn_flash = False
            # Remember as background monitor if V16
            if v == 16:
                self.cadrstor_bg = (self.verb, self.noun, self.r1, self.r2, self.r3)
                self.lamps["KEY REL"] = False
            return

        if v in (6, 16) and n == 63:
            abvel = self.erasable.get("ABVEL_FPS", 4215.6)
            hdot = self.erasable.get("HDOT_FPS", -84.2)
            hcalc = self.erasable.get("HCALC_FT", 38400)
            self.r1 = f"+{int(round(abvel * 10)):05d}"
            self.r2 = f"{'+' if hdot >= 0 else '-'}{abs(int(round(hdot * 10))):05d}"
            self.r3 = f"+{int(round(hcalc)):05d}"
            self.vn_flash = False
            return

        self.lamps["OPR ERR"] = True

    def format_ascii(self, title: str = "") -> str:
        """Render an ASCII DSKY panel for terminal output."""
        def lamp(name: str, width: int = 11) -> str:
            on = self.lamps.get(name, False)
            tag = f"*{name}*" if on else f" {name} "
            return f"{tag:^{width}s}"

        ca = "[COMP ACTY]" if self.comp_acty else "           "
        fl = "*" if self.vn_flash else " "
        lines = [
            f"  +-------------------------+-------------------------------+  {title}",
            f"  | {lamp('UPLINK ACTY')} | {lamp('TEMP')} |  {ca:<13s}      PROG        |",
            f"  | {lamp('NO ATT')} | {lamp('GIMBAL LOCK')} |                     [{self.prog:2s}]        |",
            f"  | {lamp('STBY')} | {lamp('PROG')} |   VERB{fl}              NOUN{fl}      |",
            f"  | {lamp('KEY REL')} | {lamp('RESTART')} |   [{self.verb:2s}]               [{self.noun:2s}]       |",
            f"  | {lamp('OPR ERR')} | {lamp('TRACKER')} |   R1:  [ {self.r1:6s} ]               |",
            f"  | {lamp('ALT')} | {lamp('VEL')} |   R2:  [ {self.r2:6s} ]               |",
            f"  |                         |   R3:  [ {self.r3:6s} ]               |",
            f"  +-------------------------+-------------------------------+",
        ]
        return "\n".join(lines)


def _draw_single_dsky(ax: plt.Axes, dsky: DSKYModel, subtitle: str, r_notes: tuple[str, str, str]) -> None:
    """Draw a realistic Apollo DSKY panel (status lamps, EL digital display, and keypad)."""
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12.2)
    ax.axis("off")

    # Outer metallic bezel
    bezel = FancyBboxPatch(
        (0.2, 0.2), 9.6, 11.4,
        boxstyle="round,pad=0.1,rounding_size=0.3",
        facecolor="#374151", edgecolor="#111827", linewidth=2.2
    )
    ax.add_patch(bezel)
    ax.text(5.0, 11.85, subtitle, ha="center", va="center", fontsize=10.5, fontweight="bold", color="#111827")

    # Left-top Warning Lamp Matrix (2 columns x 6 rows)
    lamp_bg = FancyBboxPatch(
        (0.55, 4.4), 4.1, 6.8,
        boxstyle="round,pad=0.05,rounding_size=0.15",
        facecolor="#1f2937", edgecolor="#4b5563", linewidth=1.4
    )
    ax.add_patch(lamp_bg)

    lamp_pairs = [
        ("UPLINK ACTY", "TEMP", "#f9fafb", "#f59e0b"),
        ("NO ATT", "GIMBAL LOCK", "#f9fafb", "#f59e0b"),
        ("STBY", "PROG", "#f9fafb", "#f59e0b"),
        ("KEY REL", "RESTART", "#f9fafb", "#f59e0b"),
        ("OPR ERR", "TRACKER", "#f9fafb", "#f59e0b"),
        ("ALT", "VEL", "#f9fafb", "#f59e0b"),
    ]
    for row_i, (l_name, r_name, l_col, r_col) in enumerate(lamp_pairs):
        y = 10.15 - row_i * 1.05
        for col_i, (lname, active_col) in enumerate([(l_name, l_col), (r_name, r_col)]):
            x = 0.75 + col_i * 1.95
            is_on = dsky.lamps.get(lname, False)
            face = active_col if is_on else "#374151"
            text_col = "#111827" if is_on else "#9ca3af"
            edge = "#ffffff" if is_on else "#4b5563"
            rect = FancyBboxPatch(
                (x, y), 1.75, 0.80,
                boxstyle="round,pad=0.02,rounding_size=0.08",
                facecolor=face, edgecolor=edge, linewidth=1.5 if is_on else 0.8
            )
            ax.add_patch(rect)
            ax.text(x + 0.875, y + 0.40, lname, ha="center", va="center",
                    fontsize=7.2, fontweight="bold", color=text_col)

    # Right-top Electroluminescent (EL) Digital Display Window
    el_bg = FancyBboxPatch(
        (4.95, 4.4), 4.5, 6.8,
        boxstyle="round,pad=0.05,rounding_size=0.15",
        facecolor="#051b11", edgecolor="#4b5563", linewidth=1.6
    )
    ax.add_patch(el_bg)

    # COMP ACTY green square + PROG
    ca_face = "#22c55e" if dsky.comp_acty else "#143322"
    ca_box = FancyBboxPatch(
        (5.25, 9.75), 1.35, 1.05,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor=ca_face, edgecolor="#16a34a" if dsky.comp_acty else "#1f2937", lw=1.2
    )
    ax.add_patch(ca_box)
    ax.text(5.925, 10.27, "COMP\nACTY", ha="center", va="center",
            fontsize=7.8, fontweight="bold", color="#052e16" if dsky.comp_acty else "#2d5a40")

    ax.text(8.35, 10.88, "PROG", ha="center", va="center", fontsize=8, fontweight="bold", color="#86efac")
    prog_box = Rectangle((7.65, 9.75), 1.4, 0.90, facecolor="#03110a", edgecolor="#15803d", lw=1.1)
    ax.add_patch(prog_box)
    ax.text(8.35, 10.20, dsky.prog, ha="center", va="center",
            fontsize=17, fontweight="bold", family="monospace", color="#4ade80")

    # VERB and NOUN
    vn_edge = "#facc15" if dsky.vn_flash else "#15803d"
    ax.text(5.92, 9.35, "VERB", ha="center", va="center", fontsize=8, fontweight="bold", color="#86efac")
    vb_box = Rectangle((5.22, 8.25), 1.4, 0.90, facecolor="#03110a", edgecolor=vn_edge, lw=1.2)
    ax.add_patch(vb_box)
    ax.text(5.92, 8.70, dsky.verb, ha="center", va="center",
            fontsize=17, fontweight="bold", family="monospace", color="#4ade80")

    ax.text(8.35, 9.35, "NOUN", ha="center", va="center", fontsize=8, fontweight="bold", color="#86efac")
    nn_box = Rectangle((7.65, 8.25), 1.4, 0.90, facecolor="#03110a", edgecolor=vn_edge, lw=1.2)
    ax.add_patch(nn_box)
    ax.text(8.35, 8.70, dsky.noun, ha="center", va="center",
            fontsize=17, fontweight="bold", family="monospace", color="#4ade80")

    # R1, R2, R3 5-digit signed registers
    for idx, (reg_val, note) in enumerate(zip([dsky.r1, dsky.r2, dsky.r3], r_notes)):
        y_reg = 6.95 - idx * 1.18
        ax.plot([5.15, 9.25], [y_reg + 0.96, y_reg + 0.96], color="#15803d", lw=0.8)
        r_box = Rectangle((5.20, y_reg + 0.12), 3.95, 0.76, facecolor="#03110a", edgecolor="#14532d", lw=1.0)
        ax.add_patch(r_box)
        ax.text(7.18, y_reg + 0.50, reg_val, ha="center", va="center",
                fontsize=16.5, fontweight="bold", family="monospace", color="#4ade80")
        ax.text(7.18, y_reg - 0.04, note, ha="center", va="center",
                fontsize=7.2, color="#a7f3d0", family="monospace")

    # Bottom 19-button Keypad (7 columns)
    keypad_cols = [
        ["VERB", "NOUN"],
        ["+", "-", "0"],
        ["7", "4", "1"],
        ["8", "5", "2"],
        ["9", "6", "3"],
        ["CLR", "PRO", "KEY REL"],
        ["ENTR", "RSET"],
    ]
    pressed_set = set(dsky.key_history[-7:])
    for c_idx, col_keys in enumerate(keypad_cols):
        x = 0.58 + c_idx * 1.28
        y_offset = 0.55 if len(col_keys) == 2 else 0.0
        for r_idx, kname in enumerate(col_keys):
            y = 2.85 - r_idx * 1.12 - y_offset
            was_pressed = kname in pressed_set
            k_box = FancyBboxPatch(
                (x, y), 1.12, 0.95,
                boxstyle="round,pad=0.02,rounding_size=0.08",
                facecolor="#1e3a8a" if was_pressed else "#111827",
                edgecolor="#60a5fa" if was_pressed else "#6b7280",
                linewidth=1.8 if was_pressed else 1.0
            )
            ax.add_patch(k_box)
            ax.text(x + 0.56, y + 0.475, kname, ha="center", va="center",
                    fontsize=7.8, fontweight="bold", color="#ffffff")


def plot_dsky_panels(dsky_v16n68: DSKYModel, dsky_1202: DSKYModel) -> plt.Figure:
    """Render side-by-side DSKY panels for P63 V16N68 and the 1202 Alarm V05N09."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 7.4))

    _draw_single_dsky(
        ax1, dsky_v16n68,
        "1. P63 Braking: Crew Keys `V16 N68 ENTR`",
        (
            "R1: +00157 = 15.7 NM Slant Range",
            "R2:  04 12 = 4m 12s TGO in Braking",
            "R3: -02700 = -2,700 ft (LR - Calc Alt)",
        ),
    )
    _draw_single_dsky(
        ax2, dsky_1202,
        "2. 1202 Executive Alarm: Crew Keys `V05 N09 ENTR`",
        (
            "R1:  01202 = Exec Overflow (No Core Sets)",
            "R2:  00000 = 2nd Fail Reg (Empty)",
            "R3:  00000 = 3rd Fail Reg (Empty)",
        ),
    )

    fig.suptitle(
        "Apollo 11 Lunar Module DSKY (`PINBALL_GAME_BUTTONS_AND_LIGHTS.agc`): "
        "P63 Monitoring & 1202 Alarm",
        fontsize=12.5, fontweight="bold", y=0.98
    )
    save(fig, "agc_03_dsky_panels")
    return fig


def plot_reference_table() -> plt.Figure:
    """Render a clean visual reference sheet of key Apollo 11 Programs, Verbs, and Nouns."""
    fig, axes = plt.subplots(3, 1, figsize=(12.4, 8.0))
    sections = [
        ("Key Apollo 11 Programs (Major Modes — `V37 ENTR xx ENTR`)", APOLLO11_REFERENCE["programs"], "#1e3a8a"),
        ("Key PINBALL Verbs (`VERB xx` — Action to Take)", APOLLO11_REFERENCE["verbs"], "#047857"),
        ("Key PINBALL Nouns (`NOUN xx` — Registers & Scale Formatting)", APOLLO11_REFERENCE["nouns"], "#b45309"),
    ]

    for ax, (title, items, hdr_color) in zip(axes, sections):
        ax.axis("off")
        n = len(items)
        ax.set_xlim(0, 100)
        ax.set_ylim(-0.3, n + 1.1)
        ax.text(1.0, n + 0.45, title, fontsize=10, fontweight="bold", color=hdr_color, va="center")
        ax.plot([0.5, 99.5], [n + 0.05, n + 0.05], color=hdr_color, lw=1.3)

        for i, (code, name, desc) in enumerate(items):
            y = n - 1 - i
            bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
            ax.add_patch(Rectangle((0.5, y - 0.38), 99.0, 0.82, facecolor=bg, edgecolor="none"))
            ax.text(1.5, y, code, fontsize=8.5, fontweight="bold", family="monospace",
                    color=hdr_color, va="center")
            ax.text(11.5, y, name, fontsize=8.5, fontweight="bold", color="#111827", va="center")
            ax.text(40.0, y, desc, fontsize=8.2, color="#374151", va="center")

    fig.suptitle(
        "Apollo 11 DSKY Quick Reference (`ASSEMBLY_AND_OPERATION_INFORMATION.agc` & `PINBALL_NOUN_TABLES.agc`)",
        fontsize=12, fontweight="bold"
    )
    save(fig, "agc_03_verbs_nouns_programs")
    return fig


def main() -> None:
    """Narrate the PINBALL DSKY state machine, print ASCII DSKYs, and save figures."""
    step(
        1,
        "PINBALL Architecture: `KEYRUPT1` -> `CHARIN` and Verb/Noun Tables",
        f"Cited sources: {src('Luminary099/KEYRUPT_UPRUPT.agc', 'KEYRUPT1')}, "
        f"{src('Luminary099/PINBALL_GAME_BUTTONS_AND_LIGHTS.agc', 'CHARIN')}, "
        f"{src('Luminary099/PINBALL_NOUN_TABLES.agc', 'NNADTAB')}, "
        f"{src('Luminary099/PINBALL_NOUN_TABLES.agc', 'IDADDTAB')}\n"
        "• Pressing any DSKY button fires `KEYRUPT1`, which reads the 5-bit keycode from Channel 15\n"
        "  and schedules `CHARIN` as a `NOVAC` job with high priority (`CHRPRIO = OCT 30000`).\n"
        "• Normal Nouns (01–39) index `NNADTAB`; Mixed Nouns (40–99, like N68) index `IDADDTAB`\n"
        "  so R1, R2, and R3 can pull from 3 independent erasable addresses with 3 different scale routines!"
    )

    # 1. Simulate P63 start and crew keying V16 N68 ENTR
    dsky_p63 = DSKYModel(
        prog="63",
        erasable={"RANGEDSP_NM": 15.7, "TTFDISP_MS": (4, 12), "DELTAH_FT": -2700},
    )
    dsky_p63.set_background_display("06", "63", "+04216", "-00842", "+38400")
    dsky_p63.press_sequence(["VERB", "1", "6", "NOUN", "6", "8", "ENTR"])

    step(
        2,
        "Crew Sequence 1: Monitoring Landing Site & Radar Delta-H (`V16 N68 ENTR` in P63)",
        f"Cited sources: {src('Luminary099/THE_LUNAR_LANDING.agc', 'P63LM')}, "
        f"{src('Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc', 'P63DISPS')}\n"
        "Keys pressed: VERB -> 1 -> 6 -> NOUN -> 6 -> 8 -> ENTR\n\n"
        + dsky_p63.format_ascii("P63 Braking: V16 N68 Monitor")
    )

    # 2. Simulate 1202 Executive Alarm and crew keying V05 N09 ENTR
    import copy
    dsky_1202 = copy.deepcopy(dsky_p63)
    dsky_1202.trigger_alarm(0o01202, restart=True)
    dsky_1202.press_sequence(["VERB", "0", "5", "NOUN", "0", "9", "ENTR"])

    step(
        3,
        "Crew Sequence 2: Inspecting the 1202 Alarm (`V05 N09 ENTR` -> `RSET` / `KEY REL`)",
        f"Cited sources: {src('Luminary099/ALARM_AND_ABORT.agc', 'BAILOUT1')}, "
        f"{src('Luminary099/ALARM_AND_ABORT.agc', 'PROGLARM')}, "
        f"{src('Luminary099/PINBALL_GAME_BUTTONS_AND_LIGHTS.agc', 'VBRELDSP')}\n"
        "• `BAILOUT1` writes `OCT 01202` into `FAILREG`, lights `PROG` & `RESTART`.\n"
        "• Crew keys `VERB 0 5 NOUN 0 9 ENTR` to read `FAILREG` (`01202` in R1).\n"
        "• Because `V16 N68` was interrupted in `CADRSTOR`, the `KEY REL` lamp illuminates to remind\n"
        "  the crew to press `KEY REL` (and `RSET`) to extinguish the alarm and resume `V16 N68`!\n\n"
        + dsky_1202.format_ascii("1202 Alarm Inspection: V05 N09")
    )

    # Print summary table of important Apollo 11 Programs, Verbs, and Nouns
    table_lines = ["PROGRAMS (Major Modes):"]
    for code, name, desc in APOLLO11_REFERENCE["programs"]:
        table_lines.append(f"  {code:<6s} {name:<28s} — {desc}")
    table_lines.append("\nVERBS:")
    for code, name, desc in APOLLO11_REFERENCE["verbs"]:
        table_lines.append(f"  {code:<6s} {name:<28s} — {desc}")
    table_lines.append("\nNOUNS:")
    for code, name, desc in APOLLO11_REFERENCE["nouns"]:
        table_lines.append(f"  {code:<6s} {name:<28s} — {desc}")

    step(
        4,
        "Reference Table of Apollo 11 Programs, Verbs, and Nouns & Saving Figures",
        f"Cited source: {src('Luminary099/ASSEMBLY_AND_OPERATION_INFORMATION.agc', '')}\n"
        + "\n".join(table_lines)
    )
    plot_dsky_panels(dsky_p63, dsky_1202)
    plot_reference_table()


if __name__ == "__main__":
    main()
