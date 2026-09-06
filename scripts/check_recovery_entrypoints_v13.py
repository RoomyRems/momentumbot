"""Stdlib undefined-global check for the registered, non-dynamic entrypoints.

Uses Python's symbol table (including nested scopes), not a name regex. This
small gate specifically catches missing imports such as the v0.12 NameError;
it does not claim to replace the full command-line or real-data replay tests.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path
import symtable


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_FILES = (
    "scripts/run_sealed_historical_source_acquisition_v13.py",
    "scripts/run_offline_python_v13.py",
    "scripts/check_recovery_entrypoints_v13.py",
    "src/momentumbot/research/sealed_historical_source_acquisition_v13.py",
    "src/momentumbot/research/sealed_historical_source_authorization_v13.py",
)
IMPLICIT_GLOBALS = {"__name__", "__file__", "__package__", "__spec__", "__doc__", "__builtins__", "__annotations__", "__loader__", "__cached__"}


def undefined_globals(source: str, filename: str = "<source>") -> set[str]:
    parsed = ast.parse(source, filename=filename)
    if any(isinstance(node, ast.ImportFrom) and any(item.name == "*" for item in node.names) for node in ast.walk(parsed)):
        raise ValueError("wildcard imports are not permitted in recovery entrypoints")
    table = symtable.symtable(source, filename, "exec")
    defined = set(dir(builtins)) | IMPLICIT_GLOBALS
    defined.update(
        symbol.get_name() for symbol in table.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    )
    missing: set[str] = set()

    def visit(scope: symtable.SymbolTable) -> None:
        for symbol in scope.get_symbols():
            if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in defined:
                missing.add(symbol.get_name())
        for child in scope.get_children():
            visit(child)

    visit(table)
    return missing


def main() -> int:
    failures = []
    for relative in ACTIVE_FILES:
        missing = undefined_globals((ROOT / relative).read_text(encoding="utf-8"), relative)
        if missing:
            failures.append(f"{relative}: {', '.join(sorted(missing))}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"undefined-name gate passed for {len(ACTIVE_FILES)} active recovery files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
