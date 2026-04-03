from pathlib import Path

from scripts.check_layers import check_file


def test_no_upward_layer_dependency() -> None:
    src_dir = Path("src")
    violations: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        violations.extend(check_file(py_file))
    assert violations == [], "Layer dependency violations:\n" + "\n".join(violations)
