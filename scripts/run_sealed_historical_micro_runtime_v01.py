"""Validate or execute the provider-free sealed historical Micro-v0.1 runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io
from momentumbot.research.sealed_historical_micro_runtime_v01 import (
    CONTRACT_ID,
    execute_runtime,
    validate_runtime_inputs,
    validate_runtime_output,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--micro-input-root", type=Path, required=True)
    parser.add_argument("--micro-input-zip", type=Path, required=True)
    parser.add_argument("--session-input-root", type=Path, required=True)
    parser.add_argument("--session-input-zip", type=Path, required=True)
    parser.add_argument("--plan-root", type=Path, required=True)
    parser.add_argument(
        "--contract-path", type=Path,
        default=ROOT / "research/strategy/sealed-historical-micro-runtime-v0.1.json",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only == (args.output_root is not None):
        parser.error("choose exactly one of --validate-only or --output-root")
    sys.addaudithook(deny_external_io)
    values = {
        "snapshot_root": args.snapshot_root,
        "micro_input_root": args.micro_input_root,
        "micro_input_zip": args.micro_input_zip,
        "session_input_root": args.session_input_root,
        "session_input_zip": args.session_input_zip,
        "plan_root": args.plan_root,
        "contract_path": args.contract_path,
    }
    if args.validate_only:
        validate_runtime_inputs(**values)
        print(json.dumps({"contract_id": CONTRACT_ID, "inputs_valid": True, "provider_calls": 0,
                          "runtime_started": False}, sort_keys=True))
    else:
        manifest = execute_runtime(**values, output_root=args.output_root)
        validate_runtime_output(output_root=args.output_root, plan_root=args.plan_root)
        print(json.dumps({"contract_id": CONTRACT_ID, "status": "complete",
                          "activations": manifest["activation_count"],
                          "decisions": manifest["decision_count"], "provider_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
