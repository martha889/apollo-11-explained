from __future__ import annotations

import importlib

import common
import mission


def test_mission_list_exits_zero(capsys) -> None:
    rc = mission.main(["--list"])
    assert rc == 0
    captured = capsys.readouterr()
    for phase in mission.PHASES:
        assert phase.module_name in captured.out
        assert phase.short_id in captured.out


def test_resolve_only_target() -> None:
    assert len(mission.resolve_only_target("lm_02")) == 1
    assert mission.resolve_only_target("lm_02")[0].module_name == "lm_02_ascent_p12"
    assert len(mission.resolve_only_target("10")) == 1
    assert mission.resolve_only_target("10")[0].short_id == "lm_02"
    assert mission.resolve_only_target("nonexistent_phase") == []


def test_all_modules_import_and_src_citations_resolve() -> None:
    # Importing each module executes module-level src(...) docstring/constant checks;
    # we also scan AST for all src("path", ...) literals across every module to verify
    # that every single cited AGC file exists in the repository.
    import ast
    from pathlib import Path

    explained_dir = Path(common.HERE)
    for phase in mission.PHASES:
        mod = importlib.import_module(phase.module_name)
        assert hasattr(mod, "main")

        mod_path = explained_dir / f"{phase.module_name}.py"
        tree = ast.parse(mod_path.read_text(encoding="utf-8"), filename=str(mod_path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "src"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                rel_path = node.args[0].value
                label = (
                    node.args[1].value
                    if len(node.args) > 1
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                    else ""
                )
                cited = common.src(rel_path, label)
                assert rel_path in cited
