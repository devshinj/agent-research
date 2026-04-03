"""Layer dependency checker — ensures no upward imports across the 6-layer architecture."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LAYER_MAP: dict[str, int] = {
    "types": 0,
    "config": 1,
    "repository": 2,
    "service": 3,
    "runtime": 4,
    "ui": 5,
}


def get_layer(filepath: Path) -> int | None:
    parts = filepath.parts
    for i, part in enumerate(parts):
        if part == "src" and i + 1 < len(parts):
            layer_name = parts[i + 1]
            return LAYER_MAP.get(layer_name)
    return None


def get_imported_layer(module: str) -> int | None:
    parts = module.split(".")
    for i, part in enumerate(parts):
        if part == "src" and i + 1 < len(parts):
            return LAYER_MAP.get(parts[i + 1])
    return None


def check_file(filepath: Path) -> list[str]:
    current_layer = get_layer(filepath)
    if current_layer is None:
        return []

    violations: list[str] = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        module: str | None = None
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name

        if module:
            imported_layer = get_imported_layer(module)
            if imported_layer is not None and imported_layer > current_layer:
                layer_names = {v: k for k, v in LAYER_MAP.items()}
                violations.append(
                    f"{filepath}:{node.lineno} — "
                    f"{layer_names[current_layer]}(L{current_layer}) imports "
                    f"{layer_names[imported_layer]}(L{imported_layer}): {module}"
                )
    return violations


def main() -> int:
    src_dir = Path("src")
    all_violations: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        all_violations.extend(check_file(py_file))

    if all_violations:
        print("Layer dependency violations found:")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print("No layer violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
