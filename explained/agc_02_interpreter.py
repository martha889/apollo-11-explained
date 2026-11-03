"""The AGC Interpreter (`Luminary099/INTERPRETER.agc`): Hal Laning's Vector Virtual Machine.

Why did the Apollo Guidance Computer have a bytecode virtual machine?
  1. Hardware limits: Basic AGC instructions only operate on 15-bit scalars (`CA`, `AD`,
     `MP`, `DV`). Guidance laws are written in 3D double-precision vectors and 3x3 matrices.
  2. Rope-core density: `INTERPRETER.agc` packs TWO 7-bit interpretive opcodes into a
     single 15-bit word (`NEWOPS` / `EDOP` at `src("Luminary099/INTERPRETER.agc", "NEWOPS")`),
     shrinking guidance programs by ~3–4x so they fit inside the 36,864-word rope memory.
  3. Stack machine (`PUSHLOC`): Each job allocated via `FINDVAC` gets a 44-word Vector
     Accumulator (VAC) work area containing a 38-word Push-Down List (`0D..37D`). Omitting
     an operand address automatically pops the Push-Down List (`PUSHUP` at
     `src("Luminary099/INTERPRETER.agc", "PUSHUP")`).

This module implements a readable Python AGC Interpreter and runs the real Lunar Module
guidance routine `RGVGCALC` (`src("Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc", "RGVGCALC")`),
recording `MPAC`, `MODE`, `PUSHLOC`, and the Push-Down List at every instruction.
"""
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from common import save, src, step

# Authentic AGC quotes from Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc (lines 442-480)
RGVGCALC_AGC_SOURCE = """\
RGVGCALC\tTC\tINTPRET\t\t# ENTER HERE TO RECOMPUTE RG AND VG
\t\tVLOAD\tVXV
\t\t\tR
\t\t\tWM
\t\tVAD\tVSR2\t\t# RESCALE TO UNITS OF 2(9) M/CS
\t\t\tV
\t\tSTORE\tANGTERM
\t\tMXV
\t\t\tCG\t\t# NO SHIFT SINCE ANGTERM IS DOUBLE SIZED
\t\tSTORE\tVGU
\t\tPDDL\tVDEF\t\t# FORM (0,VG ,VG ) IN UNITS OF 2(10) M/CS
\t\t\tZEROVECS\t#           2   1
\t\tABVAL\tSL3
\t\tSTOVL\tVHORIZ\t\t# VHORIZ FOR DISPLAY DURING P65.
\t\t\tR\t\t#           _   ____
\t\tVSU\tPUSH\t\t# PUSH DOWN R - LAND
\t\t\tLAND
\t\tMXV\tVSL1
\t\t\tCG
\t\tSTORE\tRGU
\t\tABVAL
\t\tSTOVL\tRANGEDSP
\t\tRTB\tDOT\t\t# NOW IN MPAC IS SINE(LOOKANGL)/4
\t\t\tNORMUNIT
\t\t\tXNBPIP
\t\tEXIT

\t\tCA\tFIXLOC\t\t# RESET PUSH DOWN POINTER
\t\tTS\tPUSHLOC

# Page 807
\t\tCA\tMPAC\t\t# COMPUTE LOOKANGLE ITSELF
\t\tDOUBLE
\t\tTC\tBANKCALL
\t\tCADR\tSPARCSIN -1
\t\tAD\t1/2DEG
\t\tEXTEND
\t\tMP\t180DEGS
\t\tTS\tLOOKANGL\t# LOOKANGL FOR DISPLAY DURING P64"""


@dataclass
class TraceRow:
    """Snapshot of the Interpreter's registers after executing one opcode."""
    step_idx: int
    opcode: str
    operand: str
    mode: str               # "DP" (0) or "VEC" (-1)
    mpac_str: str
    pushloc: int            # Word offset in VAC work area (0D, 2D, 4D, 6D...)
    pd_stack_str: str
    comment: str


class TinyAGCInterpreter:
    """A readable Python model of Hal Laning's AGC Interpreter (`INTERPRETER.agc`).

    Original AGC references:
      * Entry & Dispatcher: `src("Luminary099/INTERPRETER.agc", "INTPRET")`,
        `src("Luminary099/INTERPRETER.agc", "DANZIG")`
      * Push-down / Push-up: `src("Luminary099/INTERPRETER.agc", "PUSH")`,
        `src("Luminary099/INTERPRETER.agc", "PDDL")`,
        `src("Luminary099/INTERPRETER.agc", "PUSHUP")`
      * Vector ops & RTB: `src("Luminary099/INTERPRETER.agc", "VLOAD")`,
        `src("Luminary099/INTERPRETER.agc", "VXV")`,
        `src("Luminary099/INTERPRETER.agc", "DOT")`,
        `src("Luminary099/INTERPRETER.agc", "RTB")`,
        `src("Luminary099/RTB_OP_CODES.agc", "NORMUNIT")`,
        `src("Luminary099/INTERPRETER.agc", "STORE")`
    """

    def __init__(self, erasable: dict[str, Any]) -> None:
        self.erasable = dict(erasable)
        self.mpac: Any = 0.0        # Multi-Purpose Accumulator (DP float or 3-vector)
        self.mode: int = 0          # 0 = DP scalar, -1 = 3D Vector (matches AGC MODE!)
        self.pushloc: int = 0       # Word pointer into 38-word VAC push-down list (0D..37D)
        # Model the VAC work area as word-indexed slots (DP scalar = 2 words, Vector = 6 words)
        self.vac_words: list[float] = [0.0] * 44
        self.trace: list[TraceRow] = []

    def _push_mpac(self) -> None:
        """Push `MPAC` onto the VAC Push-Down List at `PUSHLOC` (`PUSH` / `PDDL` / `PDVL`).

        In the AGC (`src("Luminary099/INTERPRETER.agc", "PUSH")`), a DP scalar occupies
        2 words (`NO.WDS = 2`) and a 3D vector occupies 6 words (`NO.WDS = 6`).
        """
        if self.mode == -1:  # Vector (6 words: X at +0, Y at +2, Z at +4)
            vec = np.asarray(self.mpac, dtype=float)
            self.vac_words[self.pushloc] = float(vec[0])
            self.vac_words[self.pushloc + 2] = float(vec[1])
            self.vac_words[self.pushloc + 4] = float(vec[2])
            self.pushloc += 6
        else:  # DP Scalar (2 words)
            self.vac_words[self.pushloc] = float(self.mpac)
            self.pushloc += 2

    def _pop_vector(self) -> np.ndarray:
        """Pop a 6-word DP vector from the Push-Down List (`PUSHUP`, `NO.WDS = 6`)."""
        assert self.pushloc >= 6, f"Push-down list underflow at PUSHLOC={self.pushloc}D"
        self.pushloc -= 6
        return np.array([
            self.vac_words[self.pushloc],
            self.vac_words[self.pushloc + 2],
            self.vac_words[self.pushloc + 4],
        ], dtype=float)

    def _pop_scalar(self) -> float:
        """Pop a 2-word DP scalar from the Push-Down List (`PUSHUP`, `NO.WDS = 2`)."""
        assert self.pushloc >= 2, f"Push-down list underflow at PUSHLOC={self.pushloc}D"
        self.pushloc -= 2
        return float(self.vac_words[self.pushloc])

    def _resolve_operand(self, operand: Optional[str], expect_vec: bool) -> Any:
        """Fetch operand from `erasable[operand]`, or `PUSHUP` from stack if `operand` is None."""
        if operand is None or operand == "":
            return self._pop_vector() if expect_vec else self._pop_scalar()
        return self.erasable[operand]

    def execute(
        self, program: list[tuple[str, Optional[str], str]]
    ) -> list[TraceRow]:
        """Execute a sequence of `(opcode, operand, comment)` instructions and log state."""
        for idx, (op, arg, comment) in enumerate(program, start=1):
            if op == "VLOAD":
                self.mpac = np.array(self._resolve_operand(arg, expect_vec=True), dtype=float)
                self.mode = -1
            elif op == "DLOAD":
                self.mpac = float(self._resolve_operand(arg, expect_vec=False))
                self.mode = 0
            elif op == "PDDL":
                # Push down MPAC, then DP-load from operand
                self._push_mpac()
                self.mpac = float(self._resolve_operand(arg, expect_vec=False))
                self.mode = 0
            elif op == "PDVL":
                self._push_mpac()
                self.mpac = np.array(self._resolve_operand(arg, expect_vec=True), dtype=float)
                self.mode = -1
            elif op == "PUSH":
                self._push_mpac()
            elif op == "VDEF":
                # `src("Luminary099/INTERPRETER.agc", "VDEF")`:
                # Treats scalar in MPAC as X, pops 2 words for Y, pops 2 words for Z!
                x_comp = float(self.mpac)
                self.pushloc -= 4
                y_comp = self.vac_words[self.pushloc + 2]
                z_comp = self.vac_words[self.pushloc]
                self.mpac = np.array([x_comp, y_comp, z_comp], dtype=float)
                self.mode = -1
            elif op == "VXV":
                # `src("Luminary099/INTERPRETER.agc", "VXV")`:
                # Computes MPAC × operand: (M2*X3 - M3*X2, M3*X1 - M1*X3, M1*X2 - M2*X1)
                rhs = np.array(self._resolve_operand(arg, expect_vec=True), dtype=float)
                self.mpac = np.cross(self.mpac, rhs)
                self.mode = -1
            elif op == "VAD":
                rhs = np.array(self._resolve_operand(arg, expect_vec=True), dtype=float)
                self.mpac = self.mpac + rhs
                self.mode = -1
            elif op == "VSU":
                rhs = np.array(self._resolve_operand(arg, expect_vec=True), dtype=float)
                self.mpac = self.mpac - rhs
                self.mode = -1
            elif op == "VXSC":
                if self.mode == -1:
                    s = float(self._resolve_operand(arg, expect_vec=False))
                    self.mpac = self.mpac * s
                else:
                    v = np.array(self._resolve_operand(arg, expect_vec=True), dtype=float)
                    self.mpac = float(self.mpac) * v
                    self.mode = -1
            elif op == "MXV":
                # Matrix pre-multiplied: M @ MPAC (`src("Luminary099/INTERPRETER.agc", "MXV")`)
                mat = np.array(self.erasable[arg], dtype=float)
                self.mpac = mat @ self.mpac
                self.mode = -1
            elif op == "DOT":
                # Vector dot product (`src("Luminary099/INTERPRETER.agc", "DOT")`)
                rhs = np.array(self._resolve_operand(arg, expect_vec=True), dtype=float)
                self.mpac = float(np.dot(self.mpac, rhs))
                self.mode = 0
            elif op == "ABVAL":
                # Vector magnitude (`src("Luminary099/INTERPRETER.agc", "ABVAL")`)
                v = np.asarray(self.mpac, dtype=float)
                lv_sq = float(np.dot(v, v))
                self.vac_words[34] = lv_sq  # 34D = LVSQUARE in VAC area
                self.mpac = float(np.sqrt(lv_sq))
                self.mode = 0
            elif op in ("UNIT", "RTB"):
                # `RTB` ("Return To Basic", `src("Luminary099/INTERPRETER.agc", "RTB")`) calls a
                # Basic assembly routine from interpretive code.
                # `RTB NORMUNIT` (`src("Luminary099/RTB_OP_CODES.agc", "NORMUNIT")`) is like `UNIT`,
                # except it pre-shifts small vectors by 2^13 if all upper words are zero so it will
                # not blow up on small vectors, returning the HALF-UNIT vector v / (2 * |v|) in MPAC.
                if op == "RTB" and arg != "NORMUNIT":
                    raise ValueError(f"Unsupported RTB subroutine: {arg}")
                v = np.asarray(self.mpac, dtype=float)
                lv_sq = float(np.dot(v, v))
                lv = float(np.sqrt(lv_sq))
                self.vac_words[34] = lv_sq
                self.vac_words[36] = lv
                self.mpac = v / (2.0 * lv)
                self.mode = -1
            elif op in ("VSR2", "VSL1", "SL3"):
                # In SI-unit mode we keep physical values unshifted while noting AGC binary shifts
                pass
            elif op == "STORE":
                self.erasable[arg] = np.copy(self.mpac) if self.mode == -1 else float(self.mpac)
            elif op == "STOVL":
                # Store MPAC at first address, then VLOAD from second address (or PUSHUP!)
                parts = [p.strip() for p in arg.split(",")] if arg else [""]
                store_sym = parts[0]
                load_sym = parts[1] if len(parts) > 1 else None
                self.erasable[store_sym] = (
                    np.copy(self.mpac) if self.mode == -1 else float(self.mpac)
                )
                self.mpac = np.array(self._resolve_operand(load_sym, expect_vec=True), dtype=float)
                self.mode = -1
                if load_sym is None:
                    arg = f"{store_sym}, (PUSHUP)"
            elif op == "EXIT":
                pass
            else:
                raise ValueError(f"Unknown interpretive opcode: {op}")

            self.trace.append(TraceRow(
                step_idx=idx,
                opcode=op,
                operand=arg if arg else "—",
                mode="VEC (-1)" if self.mode == -1 else "DP (+0)",
                mpac_str=self._format_val(self.mpac),
                pushloc=self.pushloc,
                pd_stack_str=self._format_stack(),
                comment=comment,
            ))
        return self.trace

    @staticmethod
    def _format_val(val: Any) -> str:
        if isinstance(val, np.ndarray):
            if np.max(np.abs(val)) < 1.0:
                return f"[{val[0]:8.4f}, {val[1]:8.4f}, {val[2]:8.4f}]"
            return f"[{val[0]:8.1f}, {val[1]:8.1f}, {val[2]:8.1f}]"
        return f"{float(val):10.4f}"

    def _format_stack(self) -> str:
        if self.pushloc == 0:
            return "(empty: PUSHLOC=0D)"
        vals = [
            f"{i}D:{self.vac_words[i]:.1f}"
            for i in range(0, self.pushloc, 2)
        ]
        return " | ".join(vals)


def run_rgvgcalc_demo() -> tuple[TinyAGCInterpreter, dict[str, Any]]:
    """Run `RGVGCALC` on realistic Apollo 11 P64 Approach Phase state vectors (SI units)."""
    # Lunar landing site vector LAND and LM position R in moon-centered inertial frame (meters)
    # Near P64 approach: ~2,100 m altitude, ~4,800 m slant range uprange of landing site
    r_moon = 1_737_400.0
    land = np.array([r_moon, 0.0, 0.0])                         # Landing site along +X_guidance
    r_lm = np.array([r_moon + 2150.0, -450.0, -4250.0])         # 2.15 km high, 4.25 km uprange
    v_lm = np.array([-18.5, 1.2, 112.0])                        # Descending at 18.5 m/s, 112 m/s forward
    wm = np.array([0.0, 2.6617e-6, 0.0])                        # Lunar rotation vector (rad/s)
    cg = np.eye(3)                                              # Guidance-to-SM transformation matrix
    # LM body X-axis (XNBPIP) pitched back ~16 deg from local vertical.
    # In Luminary099, unit vectors like XNBPIP are stored as HALF-UNIT vectors (scaled by 1/2)
    # so that components of +-1.0 never overflow 15-bit POSMAX. Thus dotting two half-unit
    # vectors (RTB NORMUNIT and XNBPIP) yields SINE(LOOKANGL)/4 in MPAC!
    pitch_rad = np.deg2rad(16.0)
    xnbpip_half_unit = 0.5 * np.array([np.cos(pitch_rad), 0.0, -np.sin(pitch_rad)])

    erasable = {
        "R": r_lm,
        "V": v_lm,
        "LAND": land,
        "WM": wm,
        "CG": cg,
        "ZEROVECS": 0.0,
        "XNBPIP": xnbpip_half_unit,
    }

    # Exact interpretive instruction sequence of RGVGCALC
    # from Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc (lines 442-467)
    program = [
        ("VLOAD", "R", "Load LM position vector R into MPAC"),
        ("VXV", "WM", "Compute R × WM (MPAC × operand = -(WM × R))"),
        ("VAD", "V", "ANGTERM = V + (R × WM) = V - (WM × R), velocity rel. to rotating Moon"),
        ("VSR2", "", "Rescale to 2^9 m/cs in fixed-point AGC"),
        ("STORE", "ANGTERM", "Save relative velocity in ANGTERM"),
        ("MXV", "CG", "Transform into guidance frame: VGU = CG @ ANGTERM"),
        ("STORE", "VGU", "Store guidance velocity [vx_vert, vy_lat, vz_downrange]"),
        ("PDDL", "ZEROVECS", "Push VGU to 0D..5D (PUSHLOC=6D); load 0.0 into MPAC"),
        ("VDEF", "", "Pop 4D (VGU_z) & 2D (VGU_y) -> MPAC = [0, VGU_y, VGU_z] (PUSHLOC=2D)"),
        ("ABVAL", "", "Compute horizontal speed sqrt(VGU_y^2 + VGU_z^2)"),
        ("SL3", "", "Rescale for display"),
        ("STOVL", "VHORIZ, R", "Store VHORIZ; load R into MPAC"),
        ("VSU", "LAND", "Compute position relative to landing site: R - LAND"),
        ("PUSH", "", "Push (R - LAND) onto Push-Down List at 2D..7D"),
        ("MXV", "CG", "Transform into guidance frame: RGU = CG @ (R - LAND)"),
        ("VSL1", "", "Restore scale after B-1 matrix multiply"),
        ("STORE", "RGU", "Store guidance position RGU"),
        ("ABVAL", "", "Slant range to landing site |RGU| (for V16 N68 R1!)"),
        ("STOVL", "RANGEDSP", "Store RANGEDSP; no load addr -> PUSHUP pops (R - LAND)!"),
        ("RTB", "NORMUNIT", "RTB (Return To Basic) NORMUNIT -> half-unit (R - LAND)/(2|R - LAND|)"),
        ("DOT", "XNBPIP", "Dot half-unit LOS with half-unit XNBPIP -> SINE(LOOKANGL)/4 in MPAC"),
        ("EXIT", "", "Leave Interpreter; Basic code does CA FIXLOC/TS PUSHLOC & CA MPAC/DOUBLE"),
    ]

    interp = TinyAGCInterpreter(erasable)
    interp.execute(program)

    # After EXIT, non-interpretive Basic code in RGVGCALC (lines 469-480) executes:
    #   CA FIXLOC / TS PUSHLOC      (reset push-down pointer from 2D back to 0D)
    #   CA MPAC / DOUBLE            (double SINE(LOOKANGL)/4 -> SINE(LOOKANGL)/2 for SPARCSIN -1)
    sin_look_div4 = float(interp.mpac)
    sin_look_div2 = 2.0 * sin_look_div4
    sin_look = 2.0 * sin_look_div2
    interp.erasable["SIN_LOOK_DIV4"] = sin_look_div4
    interp.erasable["SIN_LOOK_DIV2"] = sin_look_div2
    interp.erasable["LOOKANGL"] = float(np.rad2deg(np.arcsin(sin_look)))
    return interp, interp.erasable


def plot_interpreter_trace(interp: TinyAGCInterpreter) -> plt.Figure:
    """Render a step-by-step visual table of MPAC and Push-Down List state, plus PUSHLOC depth."""
    fig = plt.figure(figsize=(13.5, 8.4))
    gs = fig.add_gridspec(2, 1, height_ratios=[3.35, 1.15], hspace=0.22)
    ax_tbl = fig.add_subplot(gs[0])
    ax_pd = fig.add_subplot(gs[1])

    ax_tbl.axis("off")
    rows = interp.trace

    # Render clean alternating-row table of all 22 interpretive steps
    n_rows = len(rows)
    ax_tbl.set_xlim(0, 100)
    ax_tbl.set_ylim(-1.35, n_rows + 1.2)

    cols = [
        (1.0, "#", "left"),
        (4.5, "Opcode", "left"),
        (12.5, "Operand", "left"),
        (25.0, "Mode", "left"),
        (33.0, "MPAC Accumulator (SI units)", "left"),
        (59.5, "PD Ptr", "center"),
        (64.0, "Push-Down List State / Effect", "left"),
    ]
    for cx, title, align in cols:
        ax_tbl.text(cx, n_rows + 0.45, title, fontsize=8.8, fontweight="bold",
                    ha=align, va="center", color="#1e3a8a")
    ax_tbl.plot([0.5, 99.5], [n_rows + 0.05, n_rows + 0.05], color="#1e3a8a", lw=1.2)

    for idx, r in enumerate(rows):
        y = n_rows - 1 - idx
        # Highlight stack push/pop and RTB operations
        is_stack_op = r.opcode in ("PDDL", "VDEF", "PUSH", "RTB") or "(PUSHUP)" in r.operand
        bg_color = "#fef3c7" if is_stack_op else ("#f8fafc" if idx % 2 == 0 else "#ffffff")
        rect = FancyBboxPatch(
            (0.5, y - 0.38), 99.0, 0.82,
            boxstyle="square,pad=0", facecolor=bg_color, edgecolor="none"
        )
        ax_tbl.add_patch(rect)

        ax_tbl.text(1.0, y, f"{r.step_idx:2d}", fontsize=8, family="monospace", va="center")
        ax_tbl.text(4.5, y, r.opcode, fontsize=8.2, fontweight="bold", family="monospace",
                    color="#b91c1c" if is_stack_op else "#111827", va="center")
        ax_tbl.text(12.5, y, r.operand, fontsize=7.8, family="monospace", color="#374151", va="center")
        ax_tbl.text(25.0, y, r.mode, fontsize=7.8, family="monospace",
                    color="#0284c7" if "VEC" in r.mode else "#059669", va="center")
        ax_tbl.text(33.0, y, r.mpac_str, fontsize=8, family="monospace", color="#111827", va="center")
        ax_tbl.text(59.5, y, f"{r.pushloc:2d}D", fontsize=8, fontweight="bold",
                    family="monospace", ha="center", va="center",
                    color="#d97706" if r.pushloc > 0 else "#6b7280")
        ax_tbl.text(64.0, y, r.comment, fontsize=7.6, color="#374151", va="center")

    # Show the post-EXIT Basic (non-interpretive) instructions clearly at bottom of table
    basic_box = FancyBboxPatch(
        (0.5, -1.20), 99.0, 0.78,
        boxstyle="square,pad=0", facecolor="#e0f2fe", edgecolor="#0284c7", linewidth=0.8
    )
    ax_tbl.add_patch(basic_box)
    ax_tbl.text(
        1.2, -0.81,
        "Post-EXIT Basic (non-interpretive):  CA FIXLOC / TS PUSHLOC (resets PUSHLOC 2D -> 0D)  |  "
        "CA MPAC / DOUBLE (SINE(LOOKANGL)/4 -> SINE(LOOKANGL)/2) -> SPARCSIN -1",
        fontsize=7.5, fontweight="bold", family="monospace", color="#0369a1", va="center"
    )

    ax_tbl.set_title(
        "Step-by-Step Execution of `RGVGCALC` (`Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc`) "
        "in the AGC Interpreter",
        fontsize=11.5, fontweight="bold", pad=8
    )

    # Bottom panel: Push-Down List pointer (`PUSHLOC`) & VAC scratch registers over instruction steps
    steps_x = [r.step_idx for r in rows]
    pushlocs = [r.pushloc for r in rows]
    op_labels = [f"{r.step_idx}:{r.opcode}" for r in rows]

    ax_pd.step(steps_x, pushlocs, where="mid", color="#d97706", lw=2.2,
               label="PUSHLOC Word Offset in 44-Word VAC Area")
    ax_pd.fill_between(steps_x, pushlocs, step="mid", color="#fde68a", alpha=0.45)
    ax_pd.scatter(steps_x, pushlocs, color="#b45309", s=35, zorder=4)

    # Annotate key Push-Down List events
    ax_pd.annotate("PDDL ZEROVECS\n(Push VGU -> +6 words)", xy=(8, 6), xytext=(5.0, 6.8),
                   arrowprops={"arrowstyle": "->", "color": "#b45309"}, fontsize=8, fontweight="bold")
    ax_pd.annotate("VDEF pops Y,Z\n(-4 words)", xy=(9, 2), xytext=(9.2, 4.6),
                   arrowprops={"arrowstyle": "->", "color": "#b45309"}, fontsize=8, fontweight="bold")
    ax_pd.annotate("PUSH (R - LAND)\n(+6 words -> 8D)", xy=(14, 8), xytext=(11.5, 8.5),
                   arrowprops={"arrowstyle": "->", "color": "#b45309"}, fontsize=8, fontweight="bold")
    ax_pd.annotate("STOVL RANGEDSP\n(Implicit PUSHUP -6 words!)", xy=(19, 2), xytext=(16.2, 6.0),
                   arrowprops={"arrowstyle": "->", "color": "#dc2626"}, fontsize=8,
                   fontweight="bold", color="#991b1b")

    ax_pd.set_xticks(steps_x)
    ax_pd.set_xticklabels(op_labels, rotation=32, ha="right", fontsize=7.8, family="monospace")
    ax_pd.set_ylabel("PUSHLOC (VAC Words)")
    ax_pd.set_ylim(-0.5, 10.5)
    ax_pd.set_xlabel("Interpretive Instruction Sequence in `RGVGCALC` (followed by Basic CA FIXLOC / TS PUSHLOC)")
    ax_pd.legend(loc="upper right", fontsize=8.5)

    save(fig, "agc_02_interpreter_trace")
    return fig


def main() -> None:
    """Narrate the AGC Interpreter architecture and trace `RGVGCALC` step by step."""
    step(
        1,
        "Why a Bytecode Interpreter on a 1960s Spacecraft Computer?",
        f"Cited sources: {src('Luminary099/INTERPRETER.agc', 'INTPRET')}, "
        f"{src('Luminary099/INTERPRETER.agc', 'DANZIG')}, "
        f"{src('Luminary099/INTERPRETER.agc', 'NEWOPS')}\n"
        "• Basic AGC instructions only handle 15-bit scalars. 3D navigation requires DP vectors & matrices.\n"
        "• `NEWOPS` unpacks TWO 7-bit opcodes per 15-bit word (saving the right-hand opcode in `EDOP`).\n"
        "• `DANZIG` checks `CCS NEWJOB; TCF CHANG2` between instructions so higher-priority jobs can preempt!"
    )

    step(
        2,
        "Quoting Real AGC Interpretive Code: `RGVGCALC` (Lunar Landing Guidance)",
        f"Cited source: {src('Luminary099/LUNAR_LANDING_GUIDANCE_EQUATIONS.agc', 'RGVGCALC')} (lines 442-480)\n"
        + RGVGCALC_AGC_SOURCE
        + "\n\nKey details in the source listing above:\n"
        "  • `VLOAD R / VXV WM / VAD V`: `VXV` computes `MPAC × operand = R × WM`, so `VAD V` forms\n"
        "    `ANGTERM = V + (R × WM) = V - (WM × R)`, the LM's velocity relative to the rotating Moon.\n"
        "  • `RTB NORMUNIT`: `RTB` ('Return To Basic') calls the Basic assembly routine `NORMUNIT`\n"
        "    (`RTB_OP_CODES.agc`), which safely normalizes `MPAC` into a half-unit vector `(R - LAND)/(2|R - LAND|)`.\n"
        "  • `DOT XNBPIP / EXIT`: Dots the half-unit LOS vector with the half-unit body X-axis `XNBPIP`, leaving\n"
        "    `SINE(LOOKANGL)/4` in `MPAC` at `EXIT`. Then Basic (non-interpretive) code runs `CA FIXLOC / TS PUSHLOC`\n"
        "    (resetting the push-down pointer) and `CA MPAC / DOUBLE` (doubling `SINE(LOOKANGL)/4` to `SINE(LOOKANGL)/2`)\n"
        "    before calling `SPARCSIN -1`."
    )

    interp, out_erasable = run_rgvgcalc_demo()
    vgu = out_erasable["VGU"]
    rgu = out_erasable["RGU"]
    vhoriz = out_erasable["VHORIZ"]
    rangedsp = out_erasable["RANGEDSP"]
    sin_look_div4 = out_erasable["SIN_LOOK_DIV4"]
    sin_look_div2 = out_erasable["SIN_LOOK_DIV2"]
    lookangl_deg = out_erasable["LOOKANGL"]

    trace_lines = [
        f"  {r.step_idx:2d}. {r.opcode:<6s} {r.operand:<16s} | {r.mode} | MPAC={r.mpac_str} | PD={r.pushloc:2d}D"
        for r in interp.trace
    ]
    step(
        3,
        "Running `RGVGCALC` Through the Python AGC Interpreter",
        f"Cited opcodes: {src('Luminary099/INTERPRETER.agc', 'VLOAD')}, "
        f"{src('Luminary099/INTERPRETER.agc', 'VXV')}, "
        f"{src('Luminary099/INTERPRETER.agc', 'RTB')}, "
        f"{src('Luminary099/RTB_OP_CODES.agc', 'NORMUNIT')}, "
        f"{src('Luminary099/INTERPRETER.agc', 'DOT')}, "
        f"{src('Luminary099/INTERPRETER.agc', 'PUSHUP')}\n"
        + "\n".join(trace_lines)
        + "\n\nPost-EXIT Basic (non-interpretive) instructions (lines 469-480):\n"
        f"  [Basic] CA FIXLOC / TS PUSHLOC -> resets PUSHLOC from 2D back to 0D\n"
        f"  [Basic] CA MPAC / DOUBLE       -> doubles MPAC from SINE(LOOKANGL)/4 ({sin_look_div4:.4f}) "
        f"to SINE(LOOKANGL)/2 ({sin_look_div2:.4f}) for SPARCSIN -1\n"
        + f"\nOutputs stored in Erasable Memory:\n"
        f"  • VGU      = [{vgu[0]:.2f}, {vgu[1]:.2f}, {vgu[2]:.2f}] m/s (from ANGTERM = V + R × WM)\n"
        f"  • VHORIZ   = {vhoriz:.2f} m/s (horizontal speed over lunar surface)\n"
        f"  • RGU      = [{rgu[0]:.1f}, {rgu[1]:.1f}, {rgu[2]:.1f}] m\n"
        f"  • RANGEDSP = {rangedsp:.1f} m ({rangedsp / 1852.0:.2f} NM slant range for V16 N68!)\n"
        f"  • LOOKANGL = {lookangl_deg:.2f} deg (LPD window look angle for P64!)"
    )

    step(4, "Saving Step-by-Step Interpreter & Push-Down List Figure")
    plot_interpreter_trace(interp)


if __name__ == "__main__":
    main()
