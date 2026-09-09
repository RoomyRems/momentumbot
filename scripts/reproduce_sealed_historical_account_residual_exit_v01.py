"""Separately recorded reproduction of the unchanged residual account replay.

Calls the frozen producer CLI and frozen corrected verifier without patching
either. Success requires the original runtime and verifier output bytes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import verify_sealed_historical_account_residual_exit_status_v01 as verifier

ID = "sealed-historical-account-residual-exit-reproduction-v0.1"
PARENT_COMMIT = "94fb0d37749ce8fe9c96df5d8d091b0b9d30b69c"
PARENT_TREE = "89fba9cf670db8b69274eb6ed00c4b238ac38e87"
VERIFIER_REGISTRATION = "ed0f19906970ed71af17bf32cbd72ebe2284daa8ad59f80557257035a5f85f85"
OWN_FILES = (
    "scripts/reproduce_sealed_historical_account_residual_exit_v01.py",
    "tests/test_sealed_historical_account_residual_exit_reproduction_v01.py",
    ".github/workflows/sealed-historical-account-residual-exit-reproduction-v01.yml",
)
ADDITIONAL_PARENTS = (
    f"research/strategy/{verifier.CHILD_ID}.json",
    f"research/runtime/{verifier.CHILD_ID}/freeze-manifest.json",
    f"research/data-audits/{verifier.CHILD_ID}/attempt.json",
    f"research/data-audits/{verifier.CHILD_ID}/verification.json",
    f"research/data-audits/{verifier.CHILD_ID}/freeze-manifest.json",
    f"research/data-audits/{verifier.CHILD_ID}-comparison.json",
    f"research/data-audits/{verifier.CHILD_ID}-success.json",
    "docs/research/sealed_historical_account_residual_exit_status_verification_v01.md",
)
ORIGINAL_FILES = {
    "account-replay-attempt.json": {"bytes": 1725,
        "sha256": "c51b218c2a083afde806064bf54535a959c7fb4eaa7ae166847f07990d058d68",
        "content_sha256": "daf28808c8537da83ed3fc9fb5a40de998bea57710372ba34e0b7eea1713ec67"},
    "account-replay/account-replay.json": {"bytes": 10602145,
        "sha256": verifier.RUNTIME_FILE, "content_sha256": verifier.RUNTIME},
    "account-replay/freeze-manifest.json": {"bytes": 1021,
        "sha256": verifier.RUNTIME_FREEZE_FILE,
        "content_sha256": "dfe7ca65907bb7dafeebb9fc464c69557b91ecbce286f3120ca162cefca3e351"},
}
BOUNDARIES = {
    "runtime_mechanics_changed": False, "verification_mechanics_changed": False,
    "original_attempts_overwritten": False, "provider_requests_authorized": False,
    "broker_orders_authorized": False, "financial_metrics_eligible": False,
    "account_backtest_complete": False, "retrospective_labels_opened": False,
    "policy_promotion_eligible": False, "overnight_execution_authorized": False,
}
seal, read, require = verifier.parent.seal, verifier.read, verifier.require
encoded, file_spec = verifier.encoded_document, verifier.file_spec


def contract_path(root):
    return root / f"research/strategy/{ID}.json"


def freeze_path(root):
    return root / f"research/runtime/{ID}/freeze-manifest.json"


def registration_documents(root):
    correction, _ = verifier.check_registration(root, VERIFIER_REGISTRATION)
    pins = {**correction["frozen_parent_file_sha256"], **correction["implementation_file_sha256"]}
    require(len(pins) == 281, "corrected verifier pin inventory differs")
    for path in ADDITIONAL_PARENTS:
        sha = file_spec(root / path)["sha256"]
        require(path not in pins or pins[path] == sha, "conflicting parent pin")
        pins[path] = sha
    original = read(root / f"research/strategy/{verifier.ID}.json")
    archives = {**original["source_archives"],
        **{key: verifier.ARCHIVES[key] for key in ("binding", "parent")}}
    expected = dict(ORIGINAL_FILES)
    for name in ("attempt.json", "verification.json", "freeze-manifest.json"):
        path = root / f"research/data-audits/{verifier.CHILD_ID}" / name
        expected["verification/" + name] = {**file_spec(path), "content_sha256": read(path)["content_sha256"]}
    contract = seal({
        "schema_version": 1, "contract_id": ID,
        "artifact_type": "separate_reproduction_of_unchanged_frozen_runtime",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "original_implementation_commit_sha": "49e35b57f06b97a73590517b993de0e333d692dd",
        "original_registration_freeze_content_sha256": verifier.ORIGINAL_REGISTRATION,
        "verifier_registration_freeze_content_sha256": VERIFIER_REGISTRATION,
        "expected_runtime_content_sha256": verifier.RUNTIME,
        "expected_runtime_file_sha256": verifier.RUNTIME_FILE,
        "original_hosted_run_id": 34295994393, "original_hosted_artifact_id": 10085178783,
        "original_local_runtime_missing": True, "original_failed_checker_preserved": True,
        "hypothesis": "unchanged_producer_reproduces_the_accepted_original_runtime_exactly",
        "allowed_environments": ["local", "github"], "attempts_per_environment": 1,
        "timeout_minutes": 120, "automatic_retries_authorized": False,
        "source_archives": archives, "expected_documents": expected,
        "required_population": {"paths": 12, "sessions": 360,
            "opportunity_references": 744, "unavailable_references": 162},
        "required_incomplete_states": {"flat_complete": 36,
            "flat_complete_with_unavailable_inputs": 30,
            "original_window_exhausted_with_unresolved_state": 12, "blocked_prior_state": 282},
        "frozen_parent_file_sha256": pins,
        "implementation_file_sha256": {path: file_spec(root / path)["sha256"] for path in OWN_FILES},
        "publication_required_before_replay": True,
        "next_gate": "compare_local_hosted_and_original_bytes_then_register_unresolved_continuation_scope",
        **BOUNDARIES,
    })
    raw = encoded(contract)
    freeze = seal({"contract_id": ID, "artifact_type": "reproduction_registration_freeze",
        "contract_content_sha256": contract["content_sha256"],
        "file_inventory": {f"research/strategy/{ID}.json":
            {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}, **BOUNDARIES})
    return contract, freeze


def write_new(path, value):
    with path.open("xb") as handle:
        handle.write(encoded(value))
        handle.flush()
        os.fsync(handle.fileno())


def build_registration(root):
    contract, freeze = registration_documents(root)
    contract_path(root).parent.mkdir(parents=True, exist_ok=True)
    freeze_path(root).parent.mkdir(parents=True, exist_ok=True)
    write_new(contract_path(root), contract)
    write_new(freeze_path(root), freeze)
    return freeze


def check_registration(root, expected_sha):
    contract, freeze = registration_documents(root)
    require(freeze["content_sha256"] == expected_sha, "external reproduction registration differs")
    require(contract_path(root).read_bytes() == encoded(contract)
        and freeze_path(root).read_bytes() == encoded(freeze), "reproduction metadata or frozen files differ")
    return contract, freeze


def begin_attempt(root, output, contract, expected_sha):
    require(not output.resolve().is_relative_to(root.resolve()) and not output.is_symlink()
        and not any(p.is_symlink() for p in output.parents), "new external nonsymlink output required")
    output.mkdir(parents=True, exist_ok=False)
    receipt = seal({"contract_id": ID, "artifact_type": "separate_runtime_reproduction_attempt",
        "registration_freeze_content_sha256": expected_sha,
        "contract_content_sha256": contract["content_sha256"],
        "original_runtime_content_sha256": contract["expected_runtime_content_sha256"],
        "source_archives": contract["source_archives"], "attempt": 1,
        "original_local_attempt_preserved_separately": True, **BOUNDARIES})
    write_new(output / "reproduction-attempt.json", receipt)
    return receipt


def validate_archives(paths, specs):
    require(set(paths) == set(specs), "all seven registered archives required")
    for key, spec in specs.items():
        require(file_spec(paths[key]) == {k: spec[k] for k in ("bytes", "sha256")},
            "original archive bytes differ: " + key)


def replay_original(output, paths):
    """Invoke the exact original CLI in this process; no code or policy patch."""
    import build_sealed_historical_account_residual_exit_v01 as original_cli
    previous = sys.argv
    arguments = [original_cli.__file__, "--replay", "--expected-registration-sha256",
        verifier.ORIGINAL_REGISTRATION, "--output-root", str(output / "account-replay")]
    for key in ("scanner", "management", "exit", "entry_result", "entry_consumption"):
        arguments.extend(["--" + key.replace("_", "-") + "-zip", str(paths[key])])
    try:
        sys.argv = arguments
        require(original_cli.main() == 0, "original replay CLI did not succeed")
    finally:
        sys.argv = previous


def verify_reproduced(root, output, paths, specs):
    from momentumbot.research.sealed_historical_source_binding_v01 import extract_archive
    with tempfile.TemporaryDirectory(prefix="residual-reproduction-inputs-") as temporary:
        inputs = Path(temporary)
        for key in ("binding", "parent"):
            extract_archive(paths[key], specs[key], inputs / key)
        return verifier.run_attempt(root, output / "account-replay", inputs / "binding",
            inputs / "parent/account-replay", {key: paths[key] for key in ("management", "exit")},
            VERIFIER_REGISTRATION, output / "verification")


def compare_documents(output, expected):
    inventory = {}
    for name, spec in expected.items():
        path = output / name
        require(file_spec(path) == {k: spec[k] for k in ("bytes", "sha256")},
            "reproduced bytes differ: " + name)
        require(read(path)["content_sha256"] == spec["content_sha256"], "reproduced seal differs: " + name)
        inventory[name] = dict(spec)
    return inventory


def finish_attempt(output, contract, receipt, expected_sha):
    expected = contract["expected_documents"]
    require({p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
        == set(expected) | {"reproduction-attempt.json"}, "unexpected reproduction output inventory")
    require(read(output / "reproduction-attempt.json") == receipt, "reproduction receipt changed")
    inventory = compare_documents(output, expected)
    checked = read(output / "verification/verification.json")
    require(checked["verification_passed"] is True
        and checked["runtime_content_sha256"] == contract["expected_runtime_content_sha256"],
        "frozen independent verification did not accept the original runtime")
    report = seal({"contract_id": ID, "artifact_type": "registered_runtime_reproduction_verification",
        "registration_freeze_content_sha256": expected_sha,
        "attempt_content_sha256": receipt["content_sha256"],
        "original_runtime_content_sha256": contract["expected_runtime_content_sha256"],
        "runtime_reproduction_verified": True, "all_six_original_component_files_byte_identical": True,
        "original_producer_and_corrected_verifier_unchanged": True,
        "verifier_report_content_sha256": checked["content_sha256"],
        "totals": checked["totals"], "expected_incomplete_states_preserved": contract["required_incomplete_states"],
        "file_inventory": inventory,
        "execution_provenance": "registered_original_CLI_call_and_retained_execution_log",
        "frozen_verifier_replay_false_flag_describes_its_verification_only_operation": True,
        **BOUNDARIES})
    write_new(output / "reproduction-verification.json", report)
    names = sorted(set(expected) | {"reproduction-attempt.json", "reproduction-verification.json"})
    freeze = seal({"contract_id": ID, "artifact_type": "runtime_reproduction_freeze",
        "registration_freeze_content_sha256": expected_sha, "runtime_reproduction_verified": True,
        "file_inventory": {name: file_spec(output / name) for name in names},
        "document_content_sha256": {name: read(output / name)["content_sha256"] for name in names}, **BOUNDARIES})
    write_new(output / "reproduction-freeze.json", freeze)
    return report


def run_reproduction(root, output, paths, expected_sha):
    contract, _ = check_registration(root, expected_sha)
    receipt = begin_attempt(root, output, contract, expected_sha)
    stage = "source_archive_validation"
    try:
        print("Reproduction receipt preserved; validating exact original archives", flush=True)
        validate_archives(paths, contract["source_archives"])
        stage = "original_account_replay"
        print("Starting unchanged original account replay; no policy or source changes", flush=True)
        replay_original(output, paths)
        stage = "frozen_corrected_verification"
        print("Original replay completed; applying frozen corrected verifier", flush=True)
        verify_reproduced(root, output, paths, contract["source_archives"])
        stage = "exact_byte_comparison"
        report = finish_attempt(output, contract, receipt, expected_sha)
        print(json.dumps({"runtime_reproduction_verified": True,
            "content_sha256": report["content_sha256"], **BOUNDARIES}, sort_keys=True), flush=True)
        return report
    except BaseException as exc:
        write_new(output / "reproduction-failure.json", seal({"contract_id": ID,
            "artifact_type": "preserved_runtime_reproduction_failure",
            "registration_freeze_content_sha256": expected_sha,
            "attempt_content_sha256": receipt["content_sha256"], "stage": stage,
            "error_type": type(exc).__name__, "error": str(exc)[:300],
            "runtime_reproduction_verified": False, **BOUNDARIES}))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for key in ("build-registration", "check-registration", "reproduce"):
        modes.add_argument("--" + key, action="store_true")
    parser.add_argument("--expected-registration-sha256")
    parser.add_argument("--output-root", type=Path)
    keys = ("scanner", "management", "exit", "entry_result", "entry_consumption", "binding", "parent")
    for key in keys:
        parser.add_argument("--" + key.replace("_", "-") + "-zip", type=Path)
    args = parser.parse_args()
    from run_offline_python_v13 import deny_external_io
    sys.addaudithook(deny_external_io)
    root = Path(__file__).resolve().parents[1]
    if args.build_registration:
        print(json.dumps(build_registration(root), indent=2, sort_keys=True))
        return
    expected = args.expected_registration_sha256
    if args.check_registration:
        expected = expected or read(freeze_path(root))["content_sha256"]
        _, freeze = check_registration(root, expected)
        print(json.dumps({"registration_verified": True, "registration_freeze_content_sha256": freeze["content_sha256"]}))
        return
    paths = {key: getattr(args, key + "_zip") for key in keys}
    require(expected is not None and args.output_root is not None
        and all(paths.values()), "external reproduction commitment, seven archives and new output root required")
    run_reproduction(root, args.output_root, paths, expected)


if __name__ == "__main__":
    main()
