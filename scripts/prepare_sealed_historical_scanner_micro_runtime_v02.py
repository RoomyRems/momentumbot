from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from run_offline_python_v13 import deny_external_io

from momentumbot.research.sealed_historical_scanner_micro_runtime_v02 import (
    materialize_scanner_activation_plan,
    validate_contract,
    validate_final_snapshot,
    validate_registration,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    load_json_object,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research/strategy/sealed-historical-scanner-micro-runtime-v0.2.json"
REGISTRATION = (
    ROOT
    / "research/data-audits"
    / "sealed-historical-scanner-micro-runtime-v0.2-registration-2026-09-06.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the unarmed v0.13-bound historical runtime stage."
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        help="Optional extracted final v0.13 artifact for full source validation.",
    )
    parser.add_argument(
        "--materialize-scanner-activations",
        type=Path,
        metavar="OUTPUT_ROOT",
        help="Write the scanner activation and Micro-input plan; requires --snapshot-root.",
    )
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    contract = load_json_object(CONTRACT)
    validate_contract(contract)
    validate_registration(load_json_object(REGISTRATION), contract_path=CONTRACT)
    result: dict[str, object] = {
        "contract_id": contract["contract_id"],
        "registration_valid": True,
        "runtime_execution_authorized": False,
        "runtime_started": False,
        "scanner_activation_materialization_started": False,
        "micro_runtime_started": False,
    }
    if args.snapshot_root is not None:
        result["source_validation"] = validate_final_snapshot(args.snapshot_root)
    if args.materialize_scanner_activations is not None:
        if args.snapshot_root is None:
            parser.error("--materialize-scanner-activations requires --snapshot-root")
        result["scanner_activation_plan"] = materialize_scanner_activation_plan(
            snapshot_root=args.snapshot_root,
            output_root=args.materialize_scanner_activations,
        )
        result["runtime_started"] = True
        result["scanner_activation_materialization_started"] = True
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
