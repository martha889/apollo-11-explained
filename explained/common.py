"""Shared helpers for the readable Apollo 11 AGC translations.

Every module in this folder:
  * translates one part of the original AGC assembly into plain Python,
  * cites the original source with `src("Luminary099/FILE.agc", "LABEL")`,
  * has a `main()` that prints a step-by-step narration and saves figures
    via `save(fig, "name")` into explained/figures/.
"""
from pathlib import Path

from cycler import cycler
import matplotlib

matplotlib.use("Agg")  # render to files; no display needed
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FIGURES = HERE / "figures"

# Physical constants (SI) used across modules
MU_EARTH = 3.986004418e14  # m^3/s^2
MU_MOON = 4.9048695e12  # m^3/s^2
R_EARTH = 6_378_137.0  # m
R_MOON = 1_737_400.0  # m
G0 = 9.80665  # m/s^2

PALETTE: dict[str, str] = {
    "fig_bg": "#0d121b",
    "ax_bg": "#131a26",
    "panel_bg": "#1a2333",
    "grid": "#26324a",
    "spine": "#26324a",
    "text": "#dbe3ef",
    "muted": "#8593a8",
    "csm": "#6cc3ff",
    "lm": "#f2b13c",
    "alarm": "#ff5a4f",
    "dsky": "#9bf28a",
    "earth": "#3d7fd9",
    "moon": "#b9bcc4",
    "p63": "#6cc3ff",
    "p64": "#f2b13c",
    "p66": "#ff7a6b",
    "cyan": "#4de2d8",
    "purple": "#b58cff",
    "pink": "#ff7ab8",
}

COLOR_CYCLE: list[str] = [
    PALETTE["csm"],
    PALETTE["lm"],
    PALETTE["dsky"],
    PALETTE["alarm"],
    PALETTE["cyan"],
    PALETTE["purple"],
    PALETTE["earth"],
    PALETTE["moon"],
]

plt.rcParams.update({
    "figure.figsize": (10, 6),
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "figure.facecolor": PALETTE["fig_bg"],
    "figure.edgecolor": PALETTE["fig_bg"],
    "savefig.facecolor": PALETTE["fig_bg"],
    "savefig.edgecolor": PALETTE["fig_bg"],
    "axes.facecolor": PALETTE["ax_bg"],
    "axes.edgecolor": PALETTE["spine"],
    "axes.labelcolor": PALETTE["text"],
    "axes.titlecolor": PALETTE["text"],
    "axes.titleweight": "bold",
    "axes.titlesize": 11.5,
    "axes.labelsize": 10,
    "axes.grid": True,
    "axes.prop_cycle": cycler(color=COLOR_CYCLE),
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.color": PALETTE["grid"],
    "grid.alpha": 0.55,
    "grid.linewidth": 0.7,
    "xtick.color": PALETTE["muted"],
    "ytick.color": PALETTE["muted"],
    "xtick.labelcolor": PALETTE["text"],
    "ytick.labelcolor": PALETTE["text"],
    "text.color": PALETTE["text"],
    "font.size": 10,
    "figure.titlesize": 13,
    "figure.titleweight": "bold",
    "legend.facecolor": PALETTE["fig_bg"],
    "legend.edgecolor": PALETTE["spine"],
    "legend.framealpha": 0.88,
    "legend.labelcolor": PALETTE["text"],
    "legend.fontsize": 8.5,
    "patch.edgecolor": PALETTE["spine"],
})


def glow_line(ax, x, y, color: str | None = None, lw: float = 2.0, glow_alpha: float = 0.18, glow_mult: float = 3.2, **kwargs):
    """Draw a soft wider low-alpha glow underneath a main line."""
    c = color or kwargs.pop("c", PALETTE["csm"])
    zorder = kwargs.pop("zorder", 3)
    ax.plot(x, y, color=c, lw=lw * glow_mult, alpha=glow_alpha, solid_capstyle="round", zorder=zorder - 0.1)
    return ax.plot(x, y, color=c, lw=lw, zorder=zorder, **kwargs)


def annotate_event(
    ax,
    text: str,
    xy: tuple[float, float],
    xytext: tuple[float, float] = (10, 12),
    color: str | None = None,
    fontsize: float = 8.5,
    ha: str = "left",
    va: str = "center",
    box: bool = True,
    **kwargs,
):
    """Add a styled dark-box event annotation with an arrow."""
    c = color or PALETTE["text"]
    bbox_kw = (
        dict(boxstyle="round,pad=0.28", facecolor=PALETTE["fig_bg"], edgecolor=c, alpha=0.9, lw=0.9)
        if box
        else None
    )
    return ax.annotate(
        text,
        xy=xy,
        xytext=xytext,
        textcoords="offset points",
        fontsize=fontsize,
        color=c,
        fontweight="bold",
        ha=ha,
        va=va,
        bbox=bbox_kw,
        arrowprops=dict(arrowstyle="->", color=c, lw=1.0, shrinkA=0, shrinkB=3),
        **kwargs,
    )


def src(path: str, label: str = "") -> str:
    """Return a readable pointer to the original AGC source, e.g. for docstrings/printouts."""
    assert (REPO / path).exists(), f"missing source file {path}"
    return f"{path}" + (f" @ {label}" if label else "")


def step(n, title: str, detail: str = "") -> None:
    """Print one narrated step of a walkthrough."""
    print(f"\n[{n}] {title}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"     {line}")


def save(fig, name: str) -> Path:
    """Save a figure to explained/figures/<name>.png and close it."""
    FIGURES.mkdir(exist_ok=True)
    out = FIGURES / f"{name}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    print(f"     -> saved {out.relative_to(REPO)}")
    return out
