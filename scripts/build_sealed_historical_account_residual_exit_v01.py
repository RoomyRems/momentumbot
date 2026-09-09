"""Freeze or execute the registered historical account panel without external IO."""
import argparse
import json
from pathlib import Path
import sys

from run_offline_python_v13 import deny_external_io


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--build", action="store_true")
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--replay", action="store_true")
    parser.add_argument("--expected-registration-sha256")
    parser.add_argument("--output-root", type=Path)
    for key in ("scanner", "management", "exit", "entry-result", "entry-consumption"):
        parser.add_argument("--" + key + "-zip", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_external_io)
    from momentumbot.research import sealed_historical_account_residual_exit_v01 as m
    root = Path(__file__).resolve().parents[1]
    paths = {key: getattr(args, key + "_zip") for key in m.binding.SOURCES}
    if args.replay:
        output = args.output_root
        if output is None or output.exists() or output.resolve().is_relative_to(root):
            raise ValueError("new external historical runtime output required")
        if any(value is None for value in paths.values()):
            raise ValueError("all five original archives required")
        verified = m.verify_bundle(root, root / m.OUTPUT_PATH)
        if verified["freeze_content_sha256"] != args.expected_registration_sha256:
            raise ValueError("independent replay registration commitment differs")
        # An exclusive attempt receipt precedes all original source access.
        receipt = output.with_name(output.name + "-attempt.json")
        with receipt.open("xb") as handle:
            handle.write(m.fees.encoded(m.seal({"contract_id": m.CONTRACT_ID,
                "registration_freeze_content_sha256": args.expected_registration_sha256,
                "source_bindings_content_sha256": m.BOUND_MANIFEST,
                "source_archives": m.binding.SOURCES, "attempt": 1, **m.BOUNDARY})))
            handle.flush()
            m.os.fsync(handle.fileno())
        try:
            with m.binding.OriginalSources(root, paths, expected_registration_sha256=m.PARENT_FREEZE) as sources:
                result = m.replay_panel(root, sources, expected_registration_sha256=args.expected_registration_sha256)
            files = m.documents({"account-replay.json": result}, m.expected_contract(root)["content_sha256"], runtime=True)
            m.write_files(root, output, files)
        except BaseException as exc:
            with output.with_name(output.name + "-failure.json").open("xb") as handle:
                handle.write(m.fees.encoded(m.seal({"contract_id": m.CONTRACT_ID,
                    "registration_freeze_content_sha256": args.expected_registration_sha256,
                    "status": "failed_attempt_preserved", "error_type": type(exc).__name__,
                    "error": str(exc)[:300], **m.BOUNDARY})))
            raise
        print(json.dumps({"runtime_content_sha256": result["content_sha256"],
            "paths": len(result["paths"]), "sessions": sum(p["session_count"] for p in result["paths"]),
            "financial_metrics_eligible": False}, sort_keys=True))
    else:
        if args.expected_registration_sha256 or any(paths.values()):
            raise ValueError("source arguments require --replay")
        output = args.output_root or root / m.OUTPUT_PATH
        result = m.write_files(root, output, m.build_bundle(root), registration=True) if args.build else m.verify_bundle(root, output)
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
