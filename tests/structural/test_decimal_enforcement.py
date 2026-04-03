import ast
from pathlib import Path

FINANCIAL_MODULES = [
    Path("src/service/paper_engine.py"),
    Path("src/service/risk_manager.py"),
    Path("src/service/portfolio.py"),
]


def test_no_float_literals_in_financial_modules() -> None:
    """Financial modules must use Decimal, not float literals for monetary values."""
    violations: list[str] = []
    for filepath in FINANCIAL_MODULES:
        if not filepath.exists():
            continue
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                violations.append(f"{filepath}:{node.lineno} — float literal: {node.value}")

    assert violations == [], (
        "Float literals found in financial modules (use Decimal instead):\n"
        + "\n".join(violations)
    )
