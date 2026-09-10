"""Inspect exact original entry tapes; never replay accounts or request data."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io
from momentumbot.research import sealed_historical_entry_reference_evidence_v01 as evidence

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--validate-registration", action="store_true")
    parser.add_argument("--result-zip", type=Path)
    parser.add_argument("--consumption-zip", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    if args.validate_registration:
        result = evidence.check_registration(ROOT, args.expected_contract_sha256)
    else:
        if not all((args.result_zip, args.consumption_zip, args.output)):
            parser.error("both original archives and a new output path are required")
        if args.output.exists():
            parser.error("output must be new")
        result = evidence.audit(ROOT, result_zip=args.result_zip, consumption_zip=args.consumption_zip,
            expected_contract=args.expected_contract_sha256)
        evidence.write_new(args.output, result)
    print(json.dumps({k: result[k] for k in ("contract_id", "content_sha256", "entry_gate_counts")
        if k in result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
