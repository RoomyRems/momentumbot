"""Attribute fixed conditional losses from saved records; never replay markets."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io
from momentumbot.research import sealed_historical_loss_attribution_v01 as diagnostic

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--validate-registration", action="store_true")
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    if args.validate_registration:
        result = diagnostic.check_registration(ROOT, args.expected_contract_sha256)
    else:
        if args.output_directory is None or args.output_directory.exists():
            parser.error("a new output directory is required")
        result = diagnostic.analyze(ROOT, args.expected_contract_sha256)
        markdown = diagnostic.render_markdown(result)
        args.output_directory.mkdir(parents=True, exist_ok=False)
        diagnostic.baseline.evidence.write_new(args.output_directory / "report.json", result)
        with (args.output_directory / "report.md").open("x", encoding="utf-8") as stream:
            stream.write(markdown)
    print(json.dumps({k: result[k] for k in ("contract_id", "content_sha256", "all_account_results_unchanged") if k in result},
        indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
