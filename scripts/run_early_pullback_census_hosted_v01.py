"""Unarmed census launcher; execution requires a separate sole-file approval."""
import argparse
from datetime import datetime, timezone
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
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("register", "validate-only", "prepare", "capture"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--check-execution", action="store_true")
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live-ref", type=Path)
    parser.add_argument("--artifact-metadata", type=Path)
    args = parser.parse_args()
    facts = checkout_facts() if args.check_execution or args.prepare or args.capture else None
    if not args.capture:
        sys.addaudithook(deny_external_io)
    from momentumbot.research import early_pullback_census_hosted_v01 as m
    # No all-environment copy: the provider key is read only by the gated loader.
    env = {key: os.environ.get(key, "") for key in m.ENV_KEYS}
    now = datetime.now(timezone.utc)
    if args.register:
        m.base.write_once(ROOT / m.CONTRACT_PATH, m.registration(ROOT))
    contract = m.validate_registration(ROOT)
    execution = None
    if facts:
        execution = m.validate_execution(m.base.frozen(ROOT / m.EXECUTION_PATH), contract, env, facts, now)
    if args.register or args.validate_only:
        print(json.dumps({"registration_sha256": contract["content_sha256"], "actual_provider_requests": 0, **m.adapter.BOUNDARY}))
        return 0
    if args.preflight is None:
        parser.error("preflight required")
    if args.prepare:
        pin = m.prepare(args.preflight, contract, m.adapter.validate_registration(ROOT), execution, env, m.runtime_facts())
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as handle:
            handle.write("inventory_sha256=" + pin + "\n")
        return 0
    if args.output is None or args.live_ref is None or args.artifact_metadata is None:
        parser.error("new output, live ref and artifact metadata required")
    from momentumbot.research.early_pullback_census_http_v01 import DirectHTTPS
    result = m.capture(root=ROOT, output=args.output, preflight=m.read_preflight(args.preflight, complete=True),
        env=env, facts=facts, now=now, runtime=m.runtime_facts(),
        live_ref=m.base.json_object(args.live_ref.read_bytes()), artifact=m.base.json_object(args.artifact_metadata.read_bytes()),
        credential_loader=lambda: os.environ.get("MASSIVE_API_KEY", ""), transport_factory=DirectHTTPS)
    print(json.dumps({"protocol_complete": result["protocol_complete"], "attempt_count": result["attempt_count"],
                      "report_sha256": result["content_sha256"], "historical_replay_enabled": False}))
    return 0 if result["protocol_complete"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "failed", "exception_class": type(exc).__name__,
                          "detail": "census stopped; preserve evidence; do not retry"}), file=sys.stderr)
        raise SystemExit(1) from None
