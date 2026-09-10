"""Audit original causal setup evidence offline; never run an account replay."""
import argparse
import gzip
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io
from momentumbot.research import sealed_historical_setup_stop_audit_v01 as audit

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--validate-registration", action="store_true")
    parser.add_argument("--verify-saved", action="store_true")
    parser.add_argument("--micro-zip", type=Path)
    parser.add_argument("--minutes-zip", type=Path)
    parser.add_argument("--scanner-zip", type=Path)
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    if args.validate_registration:
        result = audit.check_registration(ROOT, args.expected_contract_sha256)
    elif args.verify_saved:
        result = audit.verify_saved(ROOT, args.expected_contract_sha256)
    else:
        if args.output_directory is None or args.output_directory.exists() or not all((args.micro_zip, args.minutes_zip, args.scanner_zip)):
            parser.error("all three original ZIPs and a new output directory are required")
        args.output_directory.mkdir(parents=True, exist_ok=False)
        try:
            result, witness = audit.build(ROOT, args.expected_contract_sha256,
                {"micro": args.micro_zip, "minutes": args.minutes_zip, "scanner": args.scanner_zip},
                progress=lambda line: print(line, flush=True))
            (args.output_directory / "report.json").write_bytes(audit.encoded(result))
            (args.output_directory / "geometry-witnesses.json.gz").write_bytes(gzip.compress(audit.encoded(witness), mtime=0))
            (args.output_directory / "report.md").write_text(audit.render_markdown(result), encoding="utf-8")
        except Exception as exc:
            (args.output_directory / "failure.json").write_bytes(audit.encoded(audit.seal({"contract_id": audit.ID,
                "contract_content_sha256": args.expected_contract_sha256, "error_type": type(exc).__name__,
                "error": str(exc), "completed": False, "baseline_changed": False})))
            raise
    print(json.dumps({k: result[k] for k in ("contract_id", "content_sha256", "all_109_original_prefixes_match", "all_account_results_unchanged") if k in result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
