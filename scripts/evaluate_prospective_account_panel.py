from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from momentumbot.research.prospective_account_evaluation import (
    build_prospective_account_evaluation,
    load_evaluation_contract,
    validate_evaluation_report,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT / "research" / "strategy" / "prospective-account-evaluation-v0.1.json"
)


def _load_object(path: Path, field: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{field} root must be an object")
    return payload


def _write_once(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(rendered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the preregistered prospective account component and conditional "
            "portfolio evaluation from separately frozen runtime and labels."
        )
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    contract = load_evaluation_contract(args.contract)
    runtime = _load_object(args.runtime, "runtime")
    labels = _load_object(args.labels, "labels")
    report = build_prospective_account_evaluation(
        contract=contract,
        runtime_bundle=runtime,
        labels_bundle=labels,
    )
    validate_evaluation_report(report)
    rendered = json.dumps(
        report,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    _write_once(args.output, rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
