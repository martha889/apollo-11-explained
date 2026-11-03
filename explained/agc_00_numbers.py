"""How the Apollo Guidance Computer (AGC) represents numbers.

The Block II AGC had no floating-point hardware. Every quantity in Luminary099
and Comanche055 is stored in 15-bit ones'-complement software words (Bit 15 = sign,
Bits 14..1 = magnitude; a separate 16th odd-parity bit exists only in memory and
is invisible to software) using fixed-point fractional scaling (`B-n` notation).

This module translates the AGC's number system into readable Python:
  1. 15-bit ones'-complement integers, including +0 (00000_8) and -0 (77777_8)
  2. Single-precision (SP, 14 magnitude bits) and Double-precision (DP, 28 magnitude bits)
  3. Fixed-point binary scaling (`B-n`), with real constants from Luminary099
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from common import save, src, step

MASK15 = 0o77777          # 15-bit word mask (32767)
SIGN_BIT = 0o40000        # Bit 15 (1-indexed, MSB) is the sign bit
MAG_MASK = 0o37777        # Bits 14..1 hold the 14-bit magnitude (max 16383)
POS_ZERO = 0o00000        # +0: all 15 bits 0
NEG_ZERO = 0o77777        # -0: all 15 bits 1 (used as "empty/available" sentinel!)
POSMAX = 0o37777          # +16383 integer, or +(1 - 2^-14) fractional
NEGMAX = 0o40000          # -16383 integer, or -(1 - 2^-14) fractional


def encode_ones_complement(n: int, allow_neg_zero: bool = False) -> int:
    """Encode a signed integer (-16383..+16383) into a 15-bit AGC word.

    Original AGC reference:
      * Constant definitions in `src("Luminary099/FIXED_FIXED_CONSTANT_POOL.agc", "POSMAX")`
      * Negative zero sentinel `NEG0` at `src("Luminary099/FIXED_FIXED_CONSTANT_POOL.agc", "NEG0")`

    In ones'-complement, negative numbers are formed by flipping all 15 bits
    of the positive magnitude: `~abs(n) & 0o77777`.
    """
    if n == 0 and allow_neg_zero:
        return NEG_ZERO
    if not (-MAG_MASK <= n <= MAG_MASK):
        raise ValueError(f"Integer {n} overflows 14-bit magnitude (±{MAG_MASK})")
    if n >= 0:
        return n & MAG_MASK
    return (~(-n)) & MASK15


def decode_ones_complement(word: int) -> tuple[int, bool]:
    """Decode a 15-bit AGC word into (signed_integer, is_negative_zero).

    Original AGC reference:
      * `CCS` (Count, Compare, and Skip) instruction branches 4 ways on
        `> +0`, `= +0`, `< -0`, `= -0`; see `src("Luminary099/EXECUTIVE.agc", "NOVAC3")`.
    """
    word &= MASK15
    if word == POS_ZERO:
        return 0, False
    if word == NEG_ZERO:
        return 0, True
    if word & SIGN_BIT:
        magnitude = (~word) & MAG_MASK
        return -magnitude, False
    return word & MAG_MASK, False


def encode_sp_fraction(value: float, scale_exp: int = 0) -> int:
    """Encode a physical value scaled at 2^scale_exp (`B-scale_exp`) as a 15-bit SP fraction.

    Original AGC reference:
      * Single-precision `DEC` constants in `src("Luminary099/CONTROLLED_CONSTANTS.agc", "FULLAPS")`
        (e.g., `FULLAPS DEC 5050 B-16` stores 5050 / 2^16 in a single word).

    The binary point sits immediately to the right of the sign bit (Bit 15),
    so the word holds `fraction = value / 2^scale_exp` in (-1, +1) with step 2^-14.
    """
    fraction = value / (2.0 ** scale_exp)
    if abs(fraction) >= 1.0:
        raise ValueError(f"Scaled fraction {fraction:.6f} outside (-1, +1) for B-{scale_exp}")
    scaled_int = int(np.round(fraction * (1 << 14)))
    scaled_int = int(np.clip(scaled_int, -MAG_MASK, MAG_MASK))
    return encode_ones_complement(scaled_int)


def decode_sp_fraction(word: int, scale_exp: int = 0) -> float:
    """Decode a 15-bit SP fractional word scaled at 2^scale_exp back to physical units."""
    signed_int, _ = decode_ones_complement(word)
    fraction = signed_int / float(1 << 14)
    return fraction * (2.0 ** scale_exp)


def encode_dp_fraction(value: float, scale_exp: int = 0) -> tuple[int, int]:
    """Encode a physical value into an AGC Double Precision (DP) word pair (major, minor).

    Original AGC reference:
      * Sign agreement between major & minor words: `src("Luminary099/INTERPRETER.agc", "ALSIGNAG")`
      * DP constants (`2DEC`): `src("Luminary099/THE_LUNAR_LANDING.agc", "99999CON")`
        and `src("Luminary099/CONTROLLED_CONSTANTS.agc", "FDPS")`.

    A DP number uses two 15-bit words:
      * Major word holds bits 1..14 after the binary point (weight 2^-1 to 2^-14)
      * Minor word holds bits 15..28 after the binary point (weight 2^-15 to 2^-28)
      * Both words carry the same sign bit (sign agreement).
    """
    fraction = value / (2.0 ** scale_exp)
    if abs(fraction) >= 1.0:
        raise ValueError(f"Scaled fraction {fraction:.6f} outside (-1, +1) for B-{scale_exp}")
    sign = -1 if fraction < 0 else 1
    total_mag = int(np.round(abs(fraction) * (1 << 28)))
    total_mag = min(total_mag, (1 << 28) - 1)
    major_mag = (total_mag >> 14) & MAG_MASK
    minor_mag = total_mag & MAG_MASK
    return (
        encode_ones_complement(sign * major_mag),
        encode_ones_complement(sign * minor_mag),
    )


def decode_dp_fraction(major_word: int, minor_word: int, scale_exp: int = 0) -> float:
    """Decode an AGC Double Precision (major, minor) word pair into physical units.

    Original AGC reference:
      * `DPAGREE` / `TPAGREE` in `src("Luminary099/INTERPRETER.agc", "DPAGREE")`.
    """
    maj_int, _ = decode_ones_complement(major_word)
    min_int, _ = decode_ones_complement(minor_word)
    fraction = (maj_int / float(1 << 14)) + (min_int / float(1 << 28))
    return fraction * (2.0 ** scale_exp)


def odd_parity_bit(word: int) -> int:
    """Compute the 16th hardware odd-parity bit (exists only in memory, not seen by software)."""
    ones = bin(word & MASK15).count("1")
    return 0 if (ones % 2 == 1) else 1


def word_to_bits(word: int) -> list[int]:
    """Return the 15 software bits [Bit15 (MSB/sign), Bit14, ..., Bit1 (LSB)]."""
    return [(word >> shift) & 1 for shift in range(14, -1, -1)]


def plot_bit_layout() -> plt.Figure:
    """Create a visual bit-layout diagram of representative AGC words from Luminary099."""
    # Real examples from Luminary099
    fullaps_w = encode_sp_fraction(5050.0, scale_exp=16)
    neg_half_w = encode_ones_complement(-0o20000)
    dp_maj, dp_min = encode_dp_fraction(30479.7, scale_exp=24)

    examples = [
        ("ZERO (+0)", POS_ZERO, "OCT 00000  |  +0 (positive zero)", "FIXED_FIXED_CONSTANT_POOL.agc @ ZERO"),
        ("NEG0 (-0)", NEG_ZERO, "OCT 77777  |  -0 (empty core-set sentinel!)", "FIXED_FIXED_CONSTANT_POOL.agc @ NEG0"),
        ("POSMAX", POSMAX, "OCT 37777  |  +16383 int  or  +(1 - 2^-14) ≈ +0.999939", "FIXED_FIXED_CONSTANT_POOL.agc @ POSMAX"),
        ("NEG1/2", neg_half_w, "OCT 57777 (-20000)  |  -0.5 fractional", "FIXED_FIXED_CONSTANT_POOL.agc @ NEG1/2"),
        ("FULLAPS (SP)", fullaps_w, f"OCT {fullaps_w:05o}  |  DEC 5050 B-16 kg -> {decode_sp_fraction(fullaps_w, 16):.1f} kg", "CONTROLLED_CONSTANTS.agc @ FULLAPS"),
        ("99999CON (DP hi)", dp_maj, f"OCT {dp_maj:05o}  |  2DEC 30479.7 B-24 m (Major word)", "THE_LUNAR_LANDING.agc @ 99999CON"),
        ("99999CON (DP lo)", dp_min, f"OCT {dp_min:05o}  |  2DEC 30479.7 B-24 m (Minor word -> {decode_dp_fraction(dp_maj, dp_min, 24):.4f} m)", "THE_LUNAR_LANDING.agc @ 99999CON"),
    ]

    fig, ax = plt.subplots(figsize=(13.2, 7.0))
    ax.set_xlim(-3.5, 17.2)
    ax.set_ylim(-0.8, len(examples) + 1.45)
    ax.axis("off")

    # Column X positions:
    # Far left (x=-0.30): hardware parity bit (memory only, visually separated from software word)
    # Then a visual gap + dashed divider at x=1.00
    # Then the 15-bit software word: Bit 15 (Sign) at x=1.65, Bits 14..1 (Magnitude) at x=2.70..15.05
    col_x = [-0.30, 1.65] + [2.70 + i * 0.95 for i in range(14)]
    headers = ["P\nMem", "B15\nSign"] + [f"B{14 - i}\n2^-{i + 1}" for i in range(14)]
    for cx, hdr in zip(col_x, headers):
        color = "#6b7280" if "Mem" in hdr else ("#b91c1c" if "Sign" in hdr else "#1e3a8a")
        ax.text(cx + 0.4, len(examples) + 0.42, hdr, ha="center", va="center",
                fontsize=8, fontweight="bold", color=color)

    # Vertical dashed line visually separating memory-only parity from the 15-bit software word
    ax.plot([1.05, 1.05], [-0.3, len(examples) + 1.25], color="#9ca3af", ls="--", lw=1.2)

    # Group labels at top
    ax.text(-0.05, len(examples) + 1.05, "parity (memory only,\nnot seen by software)",
            ha="center", va="center", fontsize=7.8, color="#4b5563", fontweight="bold")
    ax.text(2.05, len(examples) + 1.05, "Sign\n(0=+, 1=-)", ha="center", va="center",
            fontsize=8.2, color="#b91c1c", fontweight="bold")
    ax.text(9.35, len(examples) + 1.05,
            "14 Magnitude Bits — Bits 14..1 (ones'-complement: inverted when Sign = 1)",
            ha="center", va="center", fontsize=9, color="#1e3a8a", fontweight="bold")

    for row_idx, (name, word, desc, citation) in enumerate(examples):
        y = len(examples) - 1 - row_idx
        bits = word_to_bits(word)
        pbit = odd_parity_bit(word)
        # Parity on far left (col 0), then 15-bit software word: Bit 15 Sign (col 1) + Bits 14..1 (cols 2..15)
        all_bits = [pbit, bits[0]] + bits[1:]

        # Label on the left
        ax.text(-0.55, y + 0.42, name, ha="right", va="center",
                fontsize=9.5, fontweight="bold", color="#111827")
        ax.text(-0.55, y + 0.12, citation, ha="right", va="center",
                fontsize=7.2, color="#4b5563", family="monospace")

        for col_i, (cx, b) in enumerate(zip(col_x, all_bits)):
            if col_i == 0:  # Parity bit (memory only, far left)
                face = "#f3f4f6"
                edge = "#9ca3af"
            elif col_i == 1:  # Bit 15: Sign bit
                face = "#fecaca" if b == 1 else "#dcfce7"
                edge = "#dc2626" if b == 1 else "#16a34a"
            else:  # Bits 14..1: 14 Magnitude bits
                face = "#dbeafe" if b == 1 else "#ffffff"
                edge = "#2563eb" if b == 1 else "#cbd5e1"

            box = FancyBboxPatch(
                (cx, y + 0.08), 0.80, 0.52,
                boxstyle="round,pad=0.03,rounding_size=0.06",
                facecolor=face, edgecolor=edge, linewidth=1.2
            )
            ax.add_patch(box)
            ax.text(cx + 0.40, y + 0.34, str(b), ha="center", va="center",
                    fontsize=9.5, fontweight="bold", family="monospace",
                    color="#6b7280" if col_i == 0 else "#111827")

        # Description below the 15-bit software word boxes
        ax.text(1.60, y - 0.14, desc, ha="left", va="center",
                fontsize=8.2, color="#374151", family="monospace")

    ax.set_title(
        "AGC 15-Bit Software Word (Bit 15 Sign + Bits 14..1 Magnitude) & Memory-Only Parity Bit",
        fontsize=12.2, fontweight="bold", pad=12
    )
    save(fig, "agc_00_bit_layout")
    return fig


def plot_scaling_precision() -> plt.Figure:
    """Plot fixed-point range vs. resolution across real Apollo 11 scaled variables."""
    # Real scaled variables from Luminary099
    variables = [
        ("Attitude Deadband\nMAXDB (SP B+5 deg)", 5.625, False, "deg", "FRESH_START_AND_RESTART.agc @ MAXDB"),
        ("Velocity VGU\n(DP 2^10 m/cs = 10.24 km/s)", 10240.0, True, "m/s", "LUNAR_LANDING_GUIDANCE_EQUATIONS.agc @ RGVGCALC"),
        ("Ascent Mass FULLAPS\n(SP 2^16 kg = 65,536 kg)", 2.0**16, False, "kg", "CONTROLLED_CONSTANTS.agc @ FULLAPS"),
        ("Landing Alt 99999CON\n(DP 2^24 m = 16,777 km)", 2.0**24, True, "m", "THE_LUNAR_LANDING.agc @ 99999CON"),
        ("Moon Position RP-TO-R\n(DP 2^27 m = 134,218 km)", 2.0**27, True, "m", "PLANETARY_INERTIAL_ORIENTATION.agc @ RP-TO-R"),
        ("DDUMCALC Numerator\n(DP 2^28 m = 268,435 km)", 2.0**28, True, "m", "THE_LUNAR_LANDING.agc @ DDUMCALC"),
        ("Earth Position RP-TO-R\n(DP 2^29 m = 536,871 km)", 2.0**29, True, "m", "PLANETARY_INERTIAL_ORIENTATION.agc @ RP-TO-R"),
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.2))

    names = [v[0] for v in variables]
    full_scales = [v[1] for v in variables]
    is_dp = [v[2] for v in variables]
    units = [v[3] for v in variables]

    sp_res = [fs / (1 << 14) for fs in full_scales]
    dp_res = [fs / (1 << 28) for fs in full_scales]

    y_pos = np.arange(len(variables))
    height = 0.36

    ax1.barh(y_pos + height / 2, sp_res, height, label="Single Precision (14 mag bits: 2^-14)",
             color="#f59e0b", alpha=0.88)
    ax1.barh(y_pos - height / 2, dp_res, height, label="Double Precision (28 mag bits: 2^-28)",
             color="#2563eb", alpha=0.88)
    ax1.set_xscale("log")
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(names, fontsize=8.5)
    ax1.invert_yaxis()
    ax1.set_xlabel("Smallest Representable Step (1 LSB, log scale)")
    ax1.set_title("Why Navigation Needed Double Precision (28 bits)")
    ax1.legend(loc="lower right", fontsize=8.5)

    for i, (sr, dr, u, dp_flag) in enumerate(zip(sp_res, dp_res, units, is_dp)):
        active_val = dr if dp_flag else sr
        tag = f"DP: {dr:.3g} {u}" if dp_flag else f"SP: {sr:.3g} {u}"
        ax1.annotate(tag, xy=(active_val, i - (height / 2 if dp_flag else -height / 2)),
                     xytext=(6, 0), textcoords="offset points", va="center",
                     fontsize=8, fontweight="bold",
                     color="#1d4ed8" if dp_flag else "#b45309")

    # Right panel: quantization error curve across (-1, 1) for a B-24 altitude variable
    alt_true = np.linspace(0.0, 15000.0, 300)  # 0 to 15 km altitude in meters
    alt_sp = np.array([decode_sp_fraction(encode_sp_fraction(h, 24), 24) for h in alt_true])
    alt_dp = np.array([decode_dp_fraction(*encode_dp_fraction(h, 24), 24) for h in alt_true])

    ax2.plot(alt_true / 1000.0, alt_sp - alt_true, color="#f59e0b", lw=1.4,
             label=f"SP B-24 error (±{2**24 / 2**15:.0f} m step = {2**10:.0f} m!)")
    ax2.plot(alt_true / 1000.0, (alt_dp - alt_true) * 1000.0, color="#2563eb", lw=1.2,
             label="DP B-24 error × 1000 (±0.031 m = 3.1 cm!)")
    ax2.axhline(0, color="#6b7280", ls="--", lw=0.8)
    ax2.set_xlabel("True Lunar Altitude (km)")
    ax2.set_ylabel("Quantization Error: SP (m) / DP (mm)")
    ax2.set_title("Quantization Error at B-24 m (1024 m vs 6.25 cm)")
    ax2.legend(loc="upper right", fontsize=8.5)

    fig.suptitle("Fixed-Point Scaling (`B-n`) Range vs. Precision in Luminary099",
                 fontsize=12, fontweight="bold")
    save(fig, "agc_00_scaling_precision")
    return fig


def main() -> None:
    """Narrate AGC number representation with real constants and save figures."""
    step(
        1,
        "15-bit Ones'-Complement Words and Negative Zero",
        f"Cited source: {src('Luminary099/FIXED_FIXED_CONSTANT_POOL.agc', 'NEG0')} & "
        f"{src('Luminary099/EXECUTIVE.agc', 'NOVAC3')}\n"
        f"+0 encodes as OCT {POS_ZERO:05o}; -0 encodes as OCT {NEG_ZERO:05o} (all 1s).\n"
        f"POSMAX = OCT {POSMAX:05o} (+{decode_ones_complement(POSMAX)[0]}), "
        f"NEGMAX = OCT {NEGMAX:05o} ({decode_ones_complement(NEGMAX)[0]}).\n"
        f"The Executive uses -0 in PRIORITY registers to mark unused core sets!"
    )

    fullaps_w = encode_sp_fraction(5050.0, scale_exp=16)
    fullaps_dec = decode_sp_fraction(fullaps_w, scale_exp=16)
    step(
        2,
        "Single-Precision Fractional Scaling (`DEC ... B-n`)",
        f"Cited source: {src('Luminary099/CONTROLLED_CONSTANTS.agc', 'FULLAPS')}\n"
        f"`FULLAPS DEC 5050 B-16` stores 5050 / 2^16 = {5050 / 65536:.6f} in 14 magnitude bits.\n"
        f"Encoded word: OCT {fullaps_w:05o} -> Decoded: {fullaps_dec:.2f} kg "
        f"(step size = 2^(16-14) = 4.0 kg)."
    )

    maj_fdps, min_fdps = encode_dp_fraction(43670.0 * 1e-4, scale_exp=7)
    maj_999, min_999 = encode_dp_fraction(30479.7, scale_exp=24)
    val_999 = decode_dp_fraction(maj_999, min_999, scale_exp=24)
    maj_ddum, min_ddum = encode_dp_fraction(8.0, scale_exp=28)
    val_ddum = decode_dp_fraction(maj_ddum, min_ddum, scale_exp=28)
    step(
        3,
        "Double-Precision (`2DEC`) and `B-24` / `B-28` Meter Scaling",
        f"Cited sources: {src('Luminary099/CONTROLLED_CONSTANTS.agc', 'FDPS')}, "
        f"{src('Luminary099/THE_LUNAR_LANDING.agc', '99999CON')}, "
        f"{src('Luminary099/THE_LUNAR_LANDING.agc', 'DDUMCRIT')}\n"
        f"• FDPS (`2DEC 4.3670 B-7`): OCT ({maj_fdps:05o}, {min_fdps:05o})\n"
        f"• 99999CON (`2DEC 30479.7 B-24` m = 99,999 ft): OCT ({maj_999:05o}, {min_999:05o}) "
        f"-> {val_999:.4f} m (LSB = 2^-4 m = 6.25 cm)\n"
        f"• DDUMCRIT (`2DEC +8 B-28` cs): OCT ({maj_ddum:05o}, {min_ddum:05o}) "
        f"-> {val_ddum:.1f} cs (scaled at 2^-28)"
    )

    step(4, "Generating Bit-Layout and Scaling Precision Figures")
    plot_bit_layout()
    plot_scaling_precision()


if __name__ == "__main__":
    main()
