"""Validate or execute the single-use, fixed four-call availability check."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from run_offline_python_v13 import deny_external_io

ROOT = Path(__file__).resolve().parents[1]


def checkout_facts():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    return {"head": git("rev-parse", "HEAD"), "parent_commit": git("rev-parse", "HEAD^"),
        "parent_tree": git("show", "-s", "--format=%T", "HEAD^"),
        "parents": git("show", "-s", "--format=%P", "HEAD").split(),
        "changed_files": git("diff", "--name-status", "HEAD^", "HEAD").splitlines(),
        "clean": not git("status", "--porcelain", "--untracked-files=no")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--register", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--probe", action="store_true")
    parser.add_argument("--check-execution", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight", type=Path)
    args = parser.parse_args()
    facts = checkout_facts() if args.check_execution or args.prepare or args.probe else None
    if not args.probe:
        sys.addaudithook(deny_external_io)
    from momentumbot.research import early_pullback_provider_check_v01 as m
    if args.register:
        m.write_once(ROOT / m.CONTRACT_PATH, m.registration(ROOT))
        print(json.dumps({"registration_created": True, "provider_attempts": 0}))
        return 0
    contract = m.validate_registration(ROOT)
    env = dict(os.environ)
    if facts:
        execution = m.validate_execution(m.frozen(ROOT / m.EXECUTION_PATH), contract, env, facts)
    if args.validate_only:
        print(json.dumps({"contract_sha256": contract["content_sha256"], "validated": True, "provider_attempts": 0}))
        return 0
    if args.preflight is None:
        parser.error("preflight directory required")
    marker = m.consumption(execution, env)
    m.validate_ci(m.json_object((args.preflight / "parent-ci.json").read_bytes()), execution)
    ref = m.json_object((args.preflight / "consumption-ref.json").read_bytes())
    m.require(ref.get("ref") == m.CONSUMPTION_REF and ref.get("object", {}).get("type") == "commit"
              and ref.get("object", {}).get("sha") == env["GITHUB_SHA"], "permanent GitHub consumption ref required")
    if args.prepare:
        for name, value in (("contract.json", contract), ("execution.json", execution),
                            ("consumption.json", marker), ("requests.json", m.request_document(contract))):
            m.write_once(args.preflight / name, value)
        return 0
    for name, value in (("contract.json", contract), ("execution.json", execution),
                        ("consumption.json", marker), ("requests.json", m.request_document(contract))):
        m.exact(m.frozen(args.preflight / name), value, "durable preflight evidence differs")
    if args.output is None:
        parser.error("new probe output directory required")
    from momentumbot.research.early_pullback_provider_transport_v01 import BoundedProbe
    credentials = {k: env.get(k, "") for k in ("ALPACA_API_KEY", "ALPACA_API_SECRET", "MASSIVE_API_KEY", "POLYGON_API_KEY", "DATABENTO_API_KEY")}
    runner = BoundedProbe(contract, execution, marker, env, output=args.output, credentials=credentials)
    result = runner.run()
    documents = {p.name: p.read_bytes() for p in args.output.iterdir()}
    m.verify_documents(documents, contract, execution_commit=env["GITHUB_SHA"], run_id=env["GITHUB_RUN_ID"],
        code_commit=execution["code_commit_sha"], code_tree=execution["code_tree_sha"], ci_run_id=execution["successful_code_ci_run_id"])
    print(json.dumps({"limited_availability_passed": result["limited_availability_passed"], "provider_attempts": 4,
                      "report_sha256": result["content_sha256"]}))
    return 0 if result["limited_availability_passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "failed", "exception_class": type(exc).__name__,
                          "detail": "provider check stopped; preserve evidence; no retry"}), file=sys.stderr)
        raise SystemExit(1) from None
