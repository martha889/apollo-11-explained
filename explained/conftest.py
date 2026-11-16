from __future__ import annotations

import sys
from pathlib import Path
import pytest

EXPLAINED_DIR = Path(__file__).resolve().parent
if str(EXPLAINED_DIR) not in sys.path:
    sys.path.insert(0, str(EXPLAINED_DIR))

import common  # noqa: E402


@pytest.fixture(autouse=True)
def redirect_figures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Prevent any test from writing into explained/figures/."""
    monkeypatch.setattr(common, "FIGURES", tmp_path)
    return tmp_path
