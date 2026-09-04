"""Fixed offline quality checks for the deterministic fixture."""

from __future__ import annotations

import ast
from pathlib import Path


def main() -> int:
    failures: list[str] = []
    for name in ("app.py", "test_app.py", "quality_check.py"):
        path = Path(name)
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            failures.append(f"{name}: missing final newline")
        if any(line.rstrip() != line for line in text.splitlines()):
            failures.append(f"{name}: trailing whitespace")
        ast.parse(text, filename=name)
    app_tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    functions = [node for node in app_tree.body if isinstance(node, ast.FunctionDef)]
    for function in functions:
        if function.returns is None or any(arg.annotation is None for arg in function.args.args):
            failures.append(f"app.py:{function.name}: public function is not fully annotated")
    if failures:
        print("\n".join(failures))
        return 1
    print("format=PASS lint-contract=PASS annotations=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
