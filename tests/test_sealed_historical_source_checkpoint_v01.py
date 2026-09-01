from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    ARTIFACT_ID,
    AUTHORIZATION_ID,
    EXPECTED_AUXILIARY_CENSUS_ROOTS,
    EXPECTED_DATES,
    EXPECTED_STAGE_ROOTS,
    build_post_scanner_checkpoint_binding,
    build_source_checkpoint,
    canonical_fingerprint,
    inventory_source_tree,
    load_authorization_envelope,
    output_is_outside_source_root,
    validate_source_checkpoint,
    write_checkpoint_once,
)


REPOSITORY = "RoomyRems/momentumbot"
WORKFLOW_REF = (
    "RoomyRems/momentumbot/.github/workflows/"
    "sealed-historical-source-acquisition-v04.yml@refs/heads/main"
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _authorization() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "authorization_id": AUTHORIZATION_ID,
        "frozen_parent": {"selected_dates": list(EXPECTED_DATES)},
        "authority_boundary": {
            "historical_source_acquisition_authorized": True,
            "live_order_authorized": False,
            "paper_order_authorized": False,
        },
        "causal_boundary": {
            "ross_actions_fills_skips_or_outcomes_may_be_read": False,
            "transcript_record_values_may_be_read": False,
        },
        "one_shot_contract": {
            "automatic_rerun_allowed": False,
            "workflow_run_attempt_required": 1,
        },
        "request_budget": {
            "allowed_hosts": [
                "api.massive.com",
                "data.alpaca.markets",
                "data.sec.gov",
            ],
            "maximum_total_http_attempts_including_retries": 40_000,
        },
        "retention_budget": {
            "maximum_retained_bytes": 1_500_000_000,
            "raw_provider_http_responses_persisted": False,
        },
    }
    payload["content_sha256"] = canonical_fingerprint(payload)
    return payload


def _budget() -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_attempts": 6,
        "by_host": {
            "api.massive.com": 1,
            "data.alpaca.markets": 2,
            "data.sec.gov": 3,
        },
    }


def _provenance_kwargs() -> dict[str, object]:
    return {
        "repository": REPOSITORY,
        "authorization_commit_sha": "a" * 40,
        "authorization_tree_sha": "b" * 40,
        "dispatcher_workflow_sha": "c" * 40,
        "dispatcher_workflow_ref": WORKFLOW_REF,
        "workflow_run_id": "33450000000",
        "workflow_run_attempt": 1,
    }


def _rehash(payload: dict[str, object]) -> None:
    payload.pop("content_sha256", None)
    payload["content_sha256"] = canonical_fingerprint(payload)


def _build_source_root(root: Path) -> None:
    ticker_type_rows = [
        {
            "asset_class": "stocks",
            "code": "CS",
            "description": "Common Stock",
            "locale": "us",
        },
        {
            "asset_class": "stocks",
            "code": "PFD",
            "description": "Preferred Stock",
            "locale": "us",
        },
    ]
    ticker_type_sha = canonical_fingerprint(ticker_type_rows)
    ticker_type_lineage = {
        "official_contract": (
            "https://massive.com/docs/rest/stocks/tickers/ticker-types"
        ),
        "row_count": len(ticker_type_rows),
        "sha256": ticker_type_sha,
    }
    date_manifests: list[dict[str, object]] = []
    for trading_date in EXPECTED_DATES:
        date_manifest = {
            "requested_asof_date": trading_date,
            "complete": True,
            "ticker_type_dictionary": ticker_type_lineage,
        }
        date_manifests.append(date_manifest)
        _write_json(
            root / trading_date / "manifest.json",
            date_manifest,
        )
    _write_json(
        root / "massive-ticker-types.json",
        {
            "schema_version": 1,
            "source": "massive_v3_reference_tickers_types",
            "official_contract": (
                "https://massive.com/docs/rest/stocks/tickers/ticker-types"
            ),
            "retrieved_at_utc": "2026-09-01T00:00:00+00:00",
            "row_count": len(ticker_type_rows),
            "sha256": ticker_type_sha,
            "rows": ticker_type_rows,
        },
    )
    _write_json(
        root / "manifest.json",
        {
            "schema_version": 1,
            "dates": list(EXPECTED_DATES),
            "massive_ticker_type_count": len(ticker_type_rows),
            "massive_ticker_types_sha256": ticker_type_sha,
            "date_manifests": date_manifests,
        },
    )
    for auxiliary in EXPECTED_AUXILIARY_CENSUS_ROOTS:
        _write_json(
            root / auxiliary / "manifest.json",
            {
                "artifact_id": auxiliary,
                "dates": list(EXPECTED_DATES),
                "label_blind": True,
            },
        )
    for name, relative, artifact_id in EXPECTED_STAGE_ROOTS:
        if relative == ".":
            continue
        body: dict[str, object] = {
            "artifact_id": artifact_id,
            "dates": list(EXPECTED_DATES),
            "stage": name,
        }
        body["content_sha256"] = canonical_fingerprint(body)
        _write_json(root / relative / "manifest.json", body)


def _environment_files(source_root: Path) -> tuple[Path, Path, Path]:
    artifact_root = source_root.parent / "provider-checkpoint"
    environment = artifact_root / "environment"
    environment.mkdir(parents=True, exist_ok=True)
    freeze = environment / "pip-freeze.txt"
    requirements = environment / "requirements-sealed-source-v04.txt"
    if not freeze.exists():
        freeze.write_text("pandas==2.2.3\n", encoding="utf-8")
    if not requirements.exists():
        requirements.write_text("pandas==2.2.3\n", encoding="utf-8")
    return freeze, requirements, artifact_root / "source-checkpoint.json"


def _build_scanner_snapshot_root(source_root: Path) -> Path:
    scanner = source_root / "causal-scanner-snapshot-v0.3"
    scanner_body: dict[str, object] = {
        "artifact_id": "causal-scanner-snapshot-v0.3",
        "dates": list(EXPECTED_DATES),
    }
    scanner_body["content_sha256"] = canonical_fingerprint(scanner_body)
    _write_json(scanner / "manifest.json", scanner_body)
    for trading_date in EXPECTED_DATES:
        _write_json(
            scanner / trading_date / "manifest.json",
            {"trading_date": trading_date},
        )
        _write_json(
            scanner / trading_date / "scanner-snapshot.json",
            {"trading_date": trading_date, "rows": []},
        )
    return scanner


class SealedHistoricalSourceCheckpointV01Tests(unittest.TestCase):
    def _build(
        self,
        root: Path,
    ) -> tuple[dict[str, object], dict[str, object], Path, Path]:
        authorization = _authorization()
        freeze, requirements, output = _environment_files(root)
        checkpoint = build_source_checkpoint(
            source_root=root,
            authorization=authorization,
            request_budget=_budget(),
            environment_freeze_path=freeze,
            requirements_path=requirements,
            checkpoint_output_path=output,
            **_provenance_kwargs(),
        )
        return checkpoint, authorization, freeze, requirements

    def test_round_trip_rehashes_complete_label_blind_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            checkpoint, authorization, freeze, requirements = self._build(root)
            self.assertEqual(checkpoint["artifact_id"], ARTIFACT_ID)
            self.assertEqual(
                [row["artifact_id"] for row in checkpoint["stage_roots"]],
                [row[2] for row in EXPECTED_STAGE_ROOTS],
            )
            self.assertFalse(checkpoint["causal_boundary"]["scanner_snapshot_present"])
            root_files = {
                row["path"]
                for row in checkpoint["inventory"]["files"]
                if "/" not in row["path"]
            }
            self.assertEqual(
                root_files,
                {"manifest.json", "massive-ticker-types.json"},
            )
            self.assertEqual(
                checkpoint["total_retained_bytes"],
                sum(path.stat().st_size for path in root.rglob("*") if path.is_file()),
            )
            loaded = json.loads(json.dumps(checkpoint))
            self.assertEqual(
                validate_source_checkpoint(
                    loaded,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    authorization=authorization,
                    expected_provenance=checkpoint["provenance"],
                ),
                loaded,
            )

    def test_massive_ticker_types_layout_hash_and_manifest_lineage_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            ticker_types_path = root / "massive-ticker-types.json"
            ticker_types_bytes = ticker_types_path.read_bytes()

            ticker_types_path.unlink()
            with self.assertRaisesRegex(ValueError, "census root files"):
                inventory_source_tree(root)
            ticker_types_path.write_bytes(ticker_types_bytes)

            extra = root / "extra-root.json"
            _write_json(extra, {})
            with self.assertRaisesRegex(ValueError, "census root files"):
                inventory_source_tree(root)
            extra.unlink()

            ticker_types = json.loads(ticker_types_bytes)
            ticker_types["rows"][0]["description"] = "Tampered description"
            _write_json(ticker_types_path, ticker_types)
            with self.assertRaisesRegex(ValueError, "canonical rows hash"):
                self._build(root)
            ticker_types_path.write_bytes(ticker_types_bytes)

            root_manifest_path = root / "manifest.json"
            root_manifest_bytes = root_manifest_path.read_bytes()
            root_manifest = json.loads(root_manifest_bytes)
            root_manifest["massive_ticker_type_count"] += 1
            _write_json(root_manifest_path, root_manifest)
            with self.assertRaisesRegex(ValueError, "count/hash lineage"):
                self._build(root)
            root_manifest_path.write_bytes(root_manifest_bytes)

            root_manifest = json.loads(root_manifest_bytes)
            root_manifest["date_manifests"][0]["ticker_type_dictionary"][
                "sha256"
            ] = "0" * 64
            _write_json(root_manifest_path, root_manifest)
            with self.assertRaisesRegex(ValueError, "date ticker-types lineage"):
                self._build(root)

    def test_changed_missing_and_extra_files_fail_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            checkpoint, authorization, freeze, requirements = self._build(root)
            target = root / EXPECTED_DATES[0] / "manifest.json"
            original = target.read_bytes()
            target.write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "source tree changed"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    authorization=authorization,
                )
            target.write_bytes(original)
            target.unlink()
            with self.assertRaisesRegex(ValueError, "source tree changed"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                )
            target.write_bytes(original)
            (root / EXPECTED_DATES[0] / "extra.bin").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "source tree changed"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                )

    def test_symlink_and_extra_or_missing_stage_roots_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            link = root / EXPECTED_DATES[0] / "escape"
            link.symlink_to(Path(temporary) / "outside")
            with self.assertRaisesRegex(ValueError, "symlink"):
                inventory_source_tree(root)
            link.unlink()
            (root / "causal-scanner-snapshot-v0.3").mkdir()
            with self.assertRaisesRegex(ValueError, "missing or extra"):
                inventory_source_tree(root)
            (root / "causal-scanner-snapshot-v0.3").rmdir()
            missing = root / "causal-alpaca-news-v0.2"
            (missing / "manifest.json").unlink()
            missing.rmdir()
            with self.assertRaisesRegex(ValueError, "missing or extra"):
                inventory_source_tree(root)

    def test_duplicate_and_escaping_inventory_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            checkpoint, _, freeze, requirements = self._build(root)
            duplicate = copy.deepcopy(checkpoint)
            duplicate["inventory"]["files"].append(
                copy.deepcopy(duplicate["inventory"]["files"][0])
            )
            duplicate["inventory"]["file_count"] += 1
            unsigned_inventory = {
                key: duplicate["inventory"][key]
                for key in ("directory_count", "directories", "file_count", "files")
            }
            duplicate["inventory"]["tree_content_sha256"] = canonical_fingerprint(
                unsigned_inventory
            )
            _rehash(duplicate)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                validate_source_checkpoint(
                    duplicate,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )

            escaping = copy.deepcopy(checkpoint)
            escaping["inventory"]["files"][0]["path"] = "../escape"
            unsigned_inventory = {
                key: escaping["inventory"][key]
                for key in ("directory_count", "directories", "file_count", "files")
            }
            escaping["inventory"]["tree_content_sha256"] = canonical_fingerprint(
                unsigned_inventory
            )
            _rehash(escaping)
            with self.assertRaisesRegex(ValueError, "escapes"):
                validate_source_checkpoint(
                    escaping,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )

    def test_bool_and_non_integer_counts_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            freeze, requirements, output = _environment_files(root)
            for value in (True, 6.0, -1):
                budget = _budget()
                budget["total_attempts"] = value
                with self.subTest(value=value), self.assertRaisesRegex(
                    ValueError, "integer"
                ):
                    build_source_checkpoint(
                        source_root=root,
                        authorization=_authorization(),
                        request_budget=budget,
                        environment_freeze_path=freeze,
                        requirements_path=requirements,
                        checkpoint_output_path=output,
                        **_provenance_kwargs(),
                    )
            checkpoint, _, freeze, requirements = self._build(root)
            checkpoint["inventory"]["files"][0]["size_bytes"] = True
            unsigned_inventory = {
                key: checkpoint["inventory"][key]
                for key in ("directory_count", "directories", "file_count", "files")
            }
            checkpoint["inventory"]["tree_content_sha256"] = canonical_fingerprint(
                unsigned_inventory
            )
            _rehash(checkpoint)
            with self.assertRaisesRegex(ValueError, "integer"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )

    def test_wrong_provenance_dates_and_authorization_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            checkpoint, authorization, freeze, requirements = self._build(root)
            expected = copy.deepcopy(checkpoint["provenance"])
            changed = copy.deepcopy(checkpoint)
            changed["provenance"]["authorization_commit_sha"] = "d" * 40
            _rehash(changed)
            with self.assertRaisesRegex(ValueError, "expected run"):
                validate_source_checkpoint(
                    changed,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    expected_provenance=expected,
                )

            dates = copy.deepcopy(checkpoint)
            dates["dates"] = list(reversed(EXPECTED_DATES))
            _rehash(dates)
            with self.assertRaisesRegex(ValueError, "frozen 30 dates"):
                validate_source_checkpoint(
                    dates,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )

            other_authorization = copy.deepcopy(authorization)
            other_authorization["registered_at_date"] = "2026-09-02"
            other_authorization["content_sha256"] = canonical_fingerprint(
                {
                    key: value
                    for key, value in other_authorization.items()
                    if key != "content_sha256"
                }
            )
            with self.assertRaisesRegex(ValueError, "different authorization"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    authorization=other_authorization,
                )

            corrupt = copy.deepcopy(authorization)
            corrupt["content_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_authorization_envelope(_write_temp_json(Path(temporary), corrupt))

    def test_environment_tamper_swapped_inputs_and_self_hash_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            checkpoint, _, freeze, requirements = self._build(root)
            freeze_before = freeze.read_bytes()
            freeze.write_bytes(freeze_before + b"tamper\n")
            with self.assertRaisesRegex(ValueError, "environment changed"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )
            freeze.write_bytes(freeze_before)
            requirements_before = requirements.read_bytes()
            requirements.write_bytes(requirements_before + b"tamper\n")
            with self.assertRaisesRegex(ValueError, "environment changed"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )
            requirements.write_bytes(requirements_before)
            with self.assertRaisesRegex(ValueError, "portable filename"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=requirements,
                    requirements_path=freeze,
                )

            swapped_labels = copy.deepcopy(checkpoint)
            environment = swapped_labels["environment"]
            environment["freeze_path"], environment["requirements_path"] = (
                environment["requirements_path"],
                environment["freeze_path"],
            )
            _rehash(swapped_labels)
            with self.assertRaisesRegex(ValueError, "portable paths"):
                validate_source_checkpoint(
                    swapped_labels,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )

            bad_self_hash = copy.deepcopy(checkpoint)
            bad_self_hash["environment"]["freeze_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "content hash mismatch"):
                validate_source_checkpoint(
                    bad_self_hash,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )

    def test_environment_symlink_nonfile_duplicate_and_unsafe_paths_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            freeze, requirements, output = _environment_files(root)
            common = {
                "source_root": root,
                "authorization": _authorization(),
                "request_budget": _budget(),
                "checkpoint_output_path": output,
                **_provenance_kwargs(),
            }

            real_freeze = freeze.with_name("real-freeze.txt")
            freeze.rename(real_freeze)
            freeze.symlink_to(real_freeze)
            with self.assertRaisesRegex(ValueError, "symlink"):
                build_source_checkpoint(
                    **common,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )
            freeze.unlink()
            real_freeze.rename(freeze)

            freeze_bytes = freeze.read_bytes()
            freeze.unlink()
            freeze.mkdir()
            with self.assertRaisesRegex(ValueError, "regular file"):
                build_source_checkpoint(
                    **common,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )
            freeze.rmdir()
            freeze.write_bytes(freeze_bytes)

            requirements.unlink()
            requirements.hardlink_to(freeze)
            with self.assertRaisesRegex(ValueError, "distinct files"):
                build_source_checkpoint(
                    **common,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )
            requirements.unlink()
            requirements.write_text("setuptools==84.0.0\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "checkpoint output"):
                build_source_checkpoint(
                    **{**common, "checkpoint_output_path": freeze},
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                )
            source_freeze = root / EXPECTED_DATES[0] / "pip-freeze.txt"
            source_freeze.write_bytes(freeze.read_bytes())
            with self.assertRaisesRegex(ValueError, "outside the source root"):
                build_source_checkpoint(
                    **common,
                    environment_freeze_path=source_freeze,
                    requirements_path=requirements,
                )
            source_freeze.unlink()
            traversing = freeze.parent / ".." / "environment" / "pip-freeze.txt"
            with self.assertRaisesRegex(ValueError, "parent traversal"):
                build_source_checkpoint(
                    **common,
                    environment_freeze_path=traversing,
                    requirements_path=requirements,
                )

    def test_post_freeze_validation_allows_only_scanner_snapshot_addition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            checkpoint, authorization, freeze, requirements = self._build(root)
            scanner = _build_scanner_snapshot_root(root)
            self.assertEqual(
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    authorization=authorization,
                    allow_scanner_snapshot_addition=True,
                ),
                checkpoint,
            )
            extra = root / "causal-alpaca-news-v0.2" / "late-extra.json"
            _write_json(extra, {})
            with self.assertRaisesRegex(ValueError, "files.*extras"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    allow_scanner_snapshot_addition=True,
                )
            extra.unlink()
            original = root / EXPECTED_DATES[0] / "manifest.json"
            original.write_bytes(original.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "checkpointed source file changed"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    allow_scanner_snapshot_addition=True,
                )

    def test_post_freeze_scanner_layout_rejects_rogue_missing_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            checkpoint, _, freeze, requirements = self._build(root)
            scanner = _build_scanner_snapshot_root(root)

            rogue = scanner / EXPECTED_DATES[0] / "rogue.json"
            _write_json(rogue, {})
            with self.assertRaisesRegex(ValueError, "files.*extras"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    allow_scanner_snapshot_addition=True,
                )
            rogue.unlink()

            rogue_directory = scanner / "rogue"
            rogue_directory.mkdir()
            with self.assertRaisesRegex(ValueError, "directories.*extras"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    allow_scanner_snapshot_addition=True,
                )
            rogue_directory.rmdir()

            missing = scanner / EXPECTED_DATES[0] / "scanner-snapshot.json"
            missing_bytes = missing.read_bytes()
            missing.unlink()
            with self.assertRaisesRegex(ValueError, "files.*incomplete"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    allow_scanner_snapshot_addition=True,
                )
            missing.write_bytes(missing_bytes)

            target = scanner / EXPECTED_DATES[0] / "manifest.json"
            target_bytes = target.read_bytes()
            target.unlink()
            target.symlink_to(scanner / EXPECTED_DATES[1] / "manifest.json")
            with self.assertRaisesRegex(ValueError, "symlink"):
                validate_source_checkpoint(
                    checkpoint,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    source_root=root,
                    allow_scanner_snapshot_addition=True,
                )
            target.unlink()
            target.write_bytes(target_bytes)

    def test_post_scanner_binding_cross_binds_checkpoint_file_and_final_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            checkpoint, authorization, freeze, requirements = self._build(root)
            _build_scanner_snapshot_root(root)
            output = root.parent / "provider-checkpoint" / "source-checkpoint.json"
            write_checkpoint_once(output, checkpoint)
            file_sha = hashlib.sha256(output.read_bytes()).hexdigest()
            binding = build_post_scanner_checkpoint_binding(
                checkpoint,
                checkpoint_file_sha256=file_sha,
                environment_freeze_path=freeze,
                requirements_path=requirements,
                checkpoint_output_path=output,
                source_root=root,
                authorization=authorization,
                expected_provenance=checkpoint["provenance"],
            )
            self.assertEqual(
                set(binding),
                {
                    "schema_version",
                    "binding_type",
                    "checkpoint_artifact_id",
                    "checkpoint_content_sha256",
                    "checkpoint_file_sha256",
                    "pre_scanner_tree_content_sha256",
                    "pre_scanner_file_count",
                    "pre_scanner_retained_file_bytes",
                    "post_scanner_tree_content_sha256",
                    "post_scanner_file_count",
                    "post_scanner_retained_file_bytes",
                    "environment",
                    "request_budget",
                    "blocked_attempts",
                    "provenance",
                    "authorization",
                    "sole_permitted_addition_id",
                    "content_sha256",
                },
            )
            unsigned = {
                key: value for key, value in binding.items() if key != "content_sha256"
            }
            self.assertEqual(binding["content_sha256"], canonical_fingerprint(unsigned))
            self.assertEqual(
                binding["post_scanner_file_count"],
                binding["pre_scanner_file_count"] + 61,
            )
            self.assertGreater(
                binding["post_scanner_retained_file_bytes"],
                binding["pre_scanner_retained_file_bytes"],
            )
            self.assertEqual(binding["environment"], checkpoint["environment"])
            with self.assertRaisesRegex(ValueError, "SHA-256 is invalid"):
                build_post_scanner_checkpoint_binding(
                    checkpoint,
                    checkpoint_file_sha256="bad",
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    checkpoint_output_path=output,
                    source_root=root,
                    authorization=authorization,
                    expected_provenance=checkpoint["provenance"],
                )
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                build_post_scanner_checkpoint_binding(
                    checkpoint,
                    checkpoint_file_sha256="0" * 64,
                    environment_freeze_path=freeze,
                    requirements_path=requirements,
                    checkpoint_output_path=output,
                    source_root=root,
                    authorization=authorization,
                    expected_provenance=checkpoint["provenance"],
                )

    def test_build_is_read_only_and_output_is_write_once_outside_source(self) -> None:
        legacy = (
            Path(__file__).resolve().parents[1]
            / "src/momentumbot/research/sealed_historical_source_acquisition_v03.py"
        )
        legacy_before = legacy.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_source_root(root)
            before = inventory_source_tree(root)
            checkpoint, _, _, _ = self._build(root)
            self.assertEqual(inventory_source_tree(root), before)
            output = Path(temporary) / "checkpoint.json"
            self.assertTrue(output_is_outside_source_root(output, root))
            self.assertFalse(output_is_outside_source_root(root / "checkpoint.json", root))
            write_checkpoint_once(output, checkpoint)
            with self.assertRaises(FileExistsError):
                write_checkpoint_once(output, checkpoint)
        self.assertEqual(legacy.read_bytes(), legacy_before)

    def test_checkpoint_module_and_script_import_no_provider_clients(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        paths = (
            repository
            / "src/momentumbot/research/sealed_historical_source_checkpoint_v01.py",
            repository / "scripts/build_sealed_historical_source_checkpoint_v04.py",
        )
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            self.assertFalse(
                any(name.startswith("momentumbot.providers") for name in imports),
                path,
            )


def _write_temp_json(root: Path, payload: object) -> Path:
    path = root / "authorization.json"
    _write_json(path, payload)
    return path


if __name__ == "__main__":
    unittest.main()
