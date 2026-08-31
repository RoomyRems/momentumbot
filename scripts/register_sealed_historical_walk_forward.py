from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from momentumbot.research.sealed_historical_walk_forward import (
    CONTRACT_ID,
    PARENT_RESEARCH_COMMIT,
    PARENT_RESEARCH_TREE,
    REGISTRATION_DATE,
    REGISTRATION_ID,
    SCAN_ROOTS,
    SCAN_SUFFIXES,
    build_contract,
    build_corpus_manifest,
    build_prior_research_date_manifest,
    canonical_fingerprint,
    freeze,
    load_json_object,
    validate_contract,
    validate_registration_files,
    verify_corpus_files,
    write_json_once,
)


REGISTRATION_AUDIT_CONTENT_SHA256 = (
    "dedd891612cd0129f1ec354b6e81af0f2fd169bb466ea9b94b1ae2ee542e9add"
)


DEFAULT_CONTRACT = Path(
    "research/strategy/sealed-historical-walk-forward-v0.1.json"
)
DEFAULT_CORPUS = Path(
    "research/data-audits/sealed-transcript-corpus-v0.1.json"
)
DEFAULT_EXCLUSIONS = Path(
    "research/data-audits/sealed-historical-date-exclusions-v0.1.json"
)
DEFAULT_REGISTRATION = Path(
    "research/data-audits/sealed-historical-walk-forward-v0.1-registration-2026-08-31.json"
)


def _git_value(repo_root: Path, expression: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", expression],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _parent_research_manifest(repo_root: Path) -> dict[str, object]:
    files: list[tuple[str, bytes]] = []
    for relative_root in SCAN_ROOTS:
        listed = subprocess.run(
            [
                "git",
                "ls-tree",
                "-r",
                "--name-only",
                PARENT_RESEARCH_COMMIT,
                "--",
                relative_root,
            ],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for relative in sorted(listed):
            if Path(relative).suffix.lower() not in SCAN_SUFFIXES:
                continue
            data = subprocess.run(
                ["git", "show", f"{PARENT_RESEARCH_COMMIT}:{relative}"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            ).stdout
            files.append((relative, data))
    return build_prior_research_date_manifest(files)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registration_audit(
    *,
    contract: dict[str, object],
    corpus: dict[str, object],
    exclusions: dict[str, object],
    contract_path: Path,
    corpus_path: Path,
    exclusion_path: Path,
) -> dict[str, object]:
    return freeze(
        {
            "schema_version": 1,
            "artifact_type": "provider_free_historical_panel_registration_audit",
            "registration_id": REGISTRATION_ID,
            "contract_id": CONTRACT_ID,
            "registered_at_date": REGISTRATION_DATE,
            "parent_research_commit": PARENT_RESEARCH_COMMIT,
            "parent_research_tree": PARENT_RESEARCH_TREE,
            "artifacts": {
                "contract": {
                    "path": contract_path.as_posix(),
                    "file_sha256": _file_sha256(contract_path),
                    "content_sha256": contract["content_sha256"],
                },
                "corpus_manifest": {
                    "path": corpus_path.as_posix(),
                    "file_sha256": _file_sha256(corpus_path),
                    "content_sha256": corpus["content_sha256"],
                    "raw_corpus_committed": False,
                },
                "exclusion_manifest": {
                    "path": exclusion_path.as_posix(),
                    "file_sha256": _file_sha256(exclusion_path),
                    "content_sha256": exclusions["content_sha256"],
                },
            },
            "selection": {
                "selected_dates": contract["sampling_contract"]["selected_dates"],
                "selection_seed_sha256": contract["sampling_contract"][
                    "selection_seed_sha256"
                ],
                "selected_block_index_zero_based": contract["sampling_contract"][
                    "selected_block_index_zero_based"
                ],
                "session_count": 30,
                "session_cell_count": 360,
                "date_replacement_allowed": False,
            },
            "causal_attestation": {
                "transcript_record_values_decoded": False,
                "titles_or_captions_opened_for_selection": False,
                "ross_actions_or_outcomes_opened_for_selection": False,
                "runtime_started": False,
                "provider_calls": 0,
                "credential_access": False,
                "orders": 0,
            },
            "next_gate": (
                "provider-free session availability and cost audit; no acquisition until a separately frozen bounded authorization"
            ),
            "authority_boundary": {
                "provider_call_authorized": False,
                "paper_order_authorized": False,
                "live_order_authorized": False,
                "policy_promotion_eligible": False,
            },
        }
    )


def _validate_audit(
    audit_path: Path,
    contract_path: Path,
    corpus_path: Path,
    exclusion_path: Path,
) -> None:
    audit = load_json_object(audit_path)
    content_hash = audit.get("content_sha256")
    body = dict(audit)
    body.pop("content_sha256", None)
    if canonical_fingerprint(body) != content_hash:
        raise ValueError("registration audit content hash mismatch")
    if content_hash != REGISTRATION_AUDIT_CONTENT_SHA256:
        raise ValueError("registration audit differs from the sealed fingerprint")
    if audit.get("registration_id") != REGISTRATION_ID:
        raise ValueError("unexpected historical registration audit ID")
    artifacts = audit.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("registration audit artifacts must be an object")
    for key, path in (
        ("contract", contract_path),
        ("corpus_manifest", corpus_path),
        ("exclusion_manifest", exclusion_path),
    ):
        row = artifacts.get(key)
        if not isinstance(row, dict) or row.get("file_sha256") != _file_sha256(path):
            raise ValueError(f"registration audit file binding mismatch: {key}")
    causal = audit.get("causal_attestation")
    if not isinstance(causal, dict) or causal != {
        "credential_access": False,
        "orders": 0,
        "provider_calls": 0,
        "ross_actions_or_outcomes_opened_for_selection": False,
        "runtime_started": False,
        "titles_or_captions_opened_for_selection": False,
        "transcript_record_values_decoded": False,
    }:
        raise ValueError("registration causal attestation mismatch")


def register(args: argparse.Namespace) -> None:
    repo_root = args.repo_root.resolve()
    tree = _git_value(repo_root, f"{PARENT_RESEARCH_COMMIT}^{{tree}}")
    if tree != PARENT_RESEARCH_TREE:
        raise RuntimeError(
            "the exact frozen parent commit/tree is unavailable or inconsistent"
        )
    corpus = build_corpus_manifest(args.corpus_file)
    exclusions = _parent_research_manifest(repo_root)
    contract = build_contract(corpus, exclusions)
    contract_path = repo_root / args.contract
    corpus_path = repo_root / args.corpus_manifest
    exclusion_path = repo_root / args.exclusion_manifest
    registration_path = repo_root / args.registration_audit
    write_json_once(corpus_path, corpus)
    write_json_once(exclusion_path, exclusions)
    write_json_once(contract_path, contract)
    audit = _registration_audit(
        contract=contract,
        corpus=corpus,
        exclusions=exclusions,
        contract_path=args.contract,
        corpus_path=args.corpus_manifest,
        exclusion_path=args.exclusion_manifest,
    )
    write_json_once(registration_path, audit)


def validate(args: argparse.Namespace) -> None:
    repo_root = args.repo_root.resolve()
    contract_path = repo_root / args.contract
    corpus_path = repo_root / args.corpus_manifest
    exclusion_path = repo_root / args.exclusion_manifest
    registration_path = repo_root / args.registration_audit
    validate_registration_files(
        contract_path=contract_path,
        corpus_manifest_path=corpus_path,
        exclusion_manifest_path=exclusion_path,
    )
    _validate_audit(
        registration_path,
        contract_path,
        corpus_path,
        exclusion_path,
    )
    if args.corpus_file:
        verify_corpus_files(load_json_object(corpus_path), args.corpus_file)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Register or validate the provider-free sealed historical panel"
    )
    result.add_argument("--repo-root", type=Path, default=Path("."))
    result.add_argument("--corpus-file", type=Path, action="append", default=[])
    result.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    result.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS)
    result.add_argument("--exclusion-manifest", type=Path, default=DEFAULT_EXCLUSIONS)
    result.add_argument("--registration-audit", type=Path, default=DEFAULT_REGISTRATION)
    result.add_argument("--validate-only", action="store_true")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.validate_only:
        validate(args)
        return
    if not args.corpus_file:
        raise SystemExit("registration requires all eight --corpus-file paths")
    register(args)


if __name__ == "__main__":
    main()
