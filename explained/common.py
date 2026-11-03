"""Shared helpers for the readable Apollo 11 AGC translations.

Every module in this folder:
  * translates one part of the original AGC assembly into plain Python,
  * cites the original source with `src("Luminary099/FILE.agc", "LABEL")`,
  * has a `main()` that prints a step-by-step narration and saves figures
    via `save(fig, "name")` into explained/figures/.
"""
from pathlib import Path

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

plt.rcParams.update({
    "figure.figsize": (10, 6),
    "figure.dpi": 110,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
})


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
    fig.savefig(out)
    plt.close(fig)
    print(f"     -> saved {out.relative_to(REPO)}")
    return out
