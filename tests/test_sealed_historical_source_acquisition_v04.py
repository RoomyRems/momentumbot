from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, time
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import pandas as pd

from momentumbot.causal_scanner_snapshot_v03 import (
    build_causal_scanner_snapshot_artifacts,
)
from momentumbot.historical_profile_union_v01 import historical_profile_union_v0_1
from momentumbot.providers.massive import (
    reference_membership_fingerprint,
    reference_ticker_fingerprint,
)
from momentumbot.research.sealed_historical_source_acquisition_v04 import (
    AUXILIARY_MANIFEST_ROOTS,
    DATE_HASH_KEYS,
    EXPECTED_DATES,
    GATE_KEYS,
    MAX_CANDIDATES_PER_DATE_V04,
    SOURCE_HASH_KEYS,
    DeepValidationAPIs,
    build_acquisition_report_v04,
    expected_manifest_paths_v04,
    expected_source_file_paths_v04,
    load_acquisition_report_v04,
    summarize_source_root_v04,
    validate_acquisition_report_v04,
    validate_source_checkpoint_binding_v04,
    validate_source_summary_v04,
    _default_validation_apis,
    _source_tree_commitment,
    _validate_source_tree_shape,
)
from momentumbot.research.sealed_historical_source_authorization_v04 import (
    AUTHORIZATION_CONTENT_SHA256,
)
from momentumbot.scanner_source_inputs_v03 import (
    SOURCE_HASH_NAMES,
    write_scanner_source_input_bundle,
)
from momentumbot.research.sealed_historical_source_checkpoint_v01 import (
    inventory_source_tree,
)


PROFILE_MANIFEST = {
    "name": "historical-profile-union-v0.1",
    "fingerprint": "f" * 64,
}
PROFILE_UNION_MANIFEST = {
    "schema_version": 1,
    "profile_union_id": "historical-profile-union-v0.1",
    "fingerprint": "e" * 64,
}
MEMBERSHIP_SHA = "9" * 64


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_summary() -> dict[str, object]:
    manifest_hashes = {
        path: hashlib.sha256(path.encode("ascii")).hexdigest()
        for path in expected_manifest_paths_v04()
    }
    source_hashes = {
        key: hashlib.sha256(key.encode("ascii")).hexdigest()
        for key in SOURCE_HASH_KEYS
    }
    source_hashes["census_file"] = manifest_hashes["manifest.json"]
    date_hashes = {
        value: {
            key: hashlib.sha256(f"{value}:{key}".encode("ascii")).hexdigest()
            for key in DATE_HASH_KEYS
        }
        for value in EXPECTED_DATES
    }
    for value in EXPECTED_DATES:
        date_hashes[value]["market_manifest_file"] = manifest_hashes[
            f"causal-market-discovery-v0.3/{value}/manifest.json"
        ]
        date_hashes[value]["float_manifest_file"] = manifest_hashes[
            f"causal-sec-float-v0.2/{value}/manifest.json"
        ]
        date_hashes[value]["news_manifest_file"] = manifest_hashes[
            f"causal-alpaca-news-v0.2/{value}/manifest.json"
        ]
    return {
        "dates": list(EXPECTED_DATES),
        "census_page_counts": {value: 1 for value in EXPECTED_DATES},
        "census_row_counts": {value: 1 for value in EXPECTED_DATES},
        "candidate_counts": {value: 1 for value in EXPECTED_DATES},
        "canonical_source_input_compressed_bytes": {
            value: 100 for value in EXPECTED_DATES
        },
        "scanner_row_counts": {value: 1 for value in EXPECTED_DATES},
        "source_hashes": source_hashes,
        "date_hashes": date_hashes,
        "manifest_file_sha256": manifest_hashes,
        "source_tree_content_sha256": "4" * 64,
        "source_file_count": 767,
        "source_retained_file_bytes": 1_000_000,
        "provider_free_replay_exact_by_date": {
            value: True for value in EXPECTED_DATES
        },
        "gates": {key: True for key in GATE_KEYS},
    }


def _report_kwargs() -> dict[str, object]:
    by_host = {
        "api.massive.com": 1,
        "data.alpaca.markets": 2,
        "data.sec.gov": 3,
    }
    provenance = {
        "repository": "RoomyRems/momentumbot",
        "authorization_commit_sha": "b" * 40,
        "authorization_tree_sha": "c" * 40,
        "dispatcher_workflow_sha": "d" * 40,
        "dispatcher_workflow_ref": (
            "RoomyRems/momentumbot/.github/workflows/"
            "sealed-historical-source-acquisition-v04.yml@refs/heads/main"
        ),
        "workflow_run_id": "123456",
        "workflow_run_attempt": 1,
    }
    checkpoint: dict[str, object] = {
        "schema_version": 1,
        "binding_type": (
            "sealed_historical_source_checkpoint_post_scanner_binding_v0.1"
        ),
        "checkpoint_artifact_id": "sealed-historical-source-checkpoint-v0.1",
        "checkpoint_content_sha256": "1" * 64,
        "checkpoint_file_sha256": "2" * 64,
        "pre_scanner_tree_content_sha256": "3" * 64,
        "pre_scanner_file_count": 706,
        "pre_scanner_retained_file_bytes": 900_000,
        "post_scanner_tree_content_sha256": "4" * 64,
        "post_scanner_file_count": 767,
        "post_scanner_retained_file_bytes": 1_000_000,
        "environment": {
            "freeze_path": "environment/pip-freeze.txt",
            "freeze_size_bytes": 100,
            "freeze_sha256": "5" * 64,
            "requirements_path": (
                "environment/requirements-sealed-source-v04.txt"
            ),
            "requirements_size_bytes": 50,
            "requirements_sha256": "6" * 64,
        },
        "request_budget": {
            "schema_version": 1,
            "allowed_hosts": [
                "api.massive.com",
                "data.alpaca.markets",
                "data.sec.gov",
            ],
            "maximum_total_http_attempts": 40_000,
            "total_attempts": sum(by_host.values()),
            "by_host": dict(by_host),
        },
        "blocked_attempts": {
            "schema_version": 1,
            "total_blocked_attempts": 0,
            "by_category": {
                "hostname": 0,
                "https_transport": 0,
                "redirect": 0,
                "request_budget": 0,
                "socket": 0,
                "subprocess": 0,
            },
            "by_host": {},
        },
        "provenance": provenance,
        "authorization": {
            "authorization_id": "sealed-historical-source-acquisition-v0.4",
            "authorization_content_sha256": AUTHORIZATION_CONTENT_SHA256,
        },
        "sole_permitted_addition_id": "causal-scanner-snapshot-v0.3",
    }
    checkpoint["content_sha256"] = _fingerprint(checkpoint)
    return {
        "authorization_id": "sealed-historical-source-acquisition-v0.4",
        "authorization_content_sha256": AUTHORIZATION_CONTENT_SHA256,
        "source_checkpoint_binding": checkpoint,
        "source_summary": _valid_summary(),
        "request_budget": {
            "schema_version": 1,
            "total_attempts": sum(by_host.values()),
            "by_host": dict(by_host),
        },
        "retained_bytes": 1_000_000,
        **provenance,
    }


def _census_row() -> dict[str, object]:
    return {
        "ticker": "AAA",
        "active": True,
        "market": "stocks",
        "locale": "us",
        "primary_exchange": "XNAS",
        "type": "CS",
        "cik": "1",
        "composite_figi": "BBG000AAA",
        "share_class_figi": "BBG00AAA1",
    }


def _identity_payload(trading_date: str) -> dict[str, object]:
    return {
        "trading_date": trading_date,
        "rows": [{"ticker": "AAA"}],
        "summary": {"membership_sha256": MEMBERSHIP_SHA},
    }


def _build_synthetic_root(root: Path) -> None:
    row = _census_row()
    ticker_sha = reference_ticker_fingerprint([row])
    membership_sha = reference_membership_fingerprint([row])
    census_dates: list[dict[str, object]] = []
    for trading_date in EXPECTED_DATES:
        manifest = {
            "requested_asof_date": trading_date,
            "page_count": 1,
            "pages": [{"row_count": 1}],
            "pagination_exhausted": True,
            "page_row_sum": 1,
            "fetch_complete": True,
            "census_summary": {"row_count": 1},
            "census_content_sha256": ticker_sha,
            "membership_sha256": membership_sha,
        }
        census_dates.append(manifest)
        _write_json(root / trading_date / "manifest.json", manifest)
        _write_json(
            root / trading_date / "tickers.json",
            {
                "requested_asof_date": trading_date,
                "content_sha256": ticker_sha,
                "membership_sha256": membership_sha,
                "rows": [row],
            },
        )
    _write_json(
        root / "manifest.json",
        {
            "dates": list(EXPECTED_DATES),
            "date_manifests": census_dates,
            "all_fetches_complete": True,
            "current_alpaca_reconciliation_skipped": True,
        },
    )

    identity_root = root / "identity-test"
    _write_json(
        identity_root / "manifest.json",
        {
            "artifact_id": "identity-test",
            "dates": list(EXPECTED_DATES),
            "content_sha256": "1" * 64,
            "eligibility": {"complete_relative_to_provisional_membership": True},
        },
    )
    for auxiliary in AUXILIARY_MANIFEST_ROOTS:
        _write_json(
            root / auxiliary / "manifest.json",
            {
                "artifact": auxiliary,
                "dates": list(EXPECTED_DATES),
                "label_blind": True,
            },
        )

    market_children: list[dict[str, object]] = []
    float_commitments: list[dict[str, object]] = []
    news_children: list[dict[str, object]] = []
    input_children: list[dict[str, object]] = []
    scanner_children: list[dict[str, object]] = []
    for trading_date in EXPECTED_DATES:
        candidate_payload = {
            "trading_date": trading_date,
            "rows": [{"symbol": "AAA"}],
        }
        candidate_payload["content_sha256"] = _fingerprint(candidate_payload)
        membership_payload = _identity_payload(trading_date)
        target_basis_payload = {
            "trading_date": trading_date,
            "rows": [{"symbol": "AAA", "target_raw_close": "10"}],
        }
        target_basis_payload["content_sha256"] = _fingerprint(
            target_basis_payload
        )
        market_date = {
            "artifact_id": "market-test",
            "trading_date": trading_date,
            "strategy_profile": PROFILE_MANIFEST,
            "acquisition_profile_union": PROFILE_UNION_MANIFEST,
            "source_membership": {
                "membership_sha256": MEMBERSHIP_SHA,
                "membership_bundle_sha256": "1" * 64,
                "membership_payload_sha256": _fingerprint(membership_payload),
            },
            "files": {"float_target_basis": "float-target-basis.json"},
        }
        market_children.append(market_date)
        _write_json(root / "market-test" / trading_date / "manifest.json", market_date)
        _write_json(
            root / "market-test" / trading_date / "market-candidates.json",
            candidate_payload,
        )
        _write_json(
            root / "market-test" / trading_date / "float-target-basis.json",
            target_basis_payload,
        )

        float_date = {
            "artifact_id": "float-test",
            "trading_date": trading_date,
            "source_market_candidates_sha256": candidate_payload[
                "content_sha256"
            ],
            "source_market_discovery_manifest_sha256": _fingerprint(market_date),
            "source_float_target_basis_sha256": target_basis_payload[
                "content_sha256"
            ],
            "summary": {"records_sha256": _fingerprint([{"symbol": "AAA"}])},
        }
        float_date["content_sha256"] = _fingerprint(float_date)
        _write_json(root / "float-test" / trading_date / "manifest.json", float_date)
        _write_json(
            root / "float-test" / trading_date / "float-records.json",
            {"rows": [{"symbol": "AAA"}]},
        )
        float_commitments.append(
            {
                "trading_date": trading_date,
                "manifest": f"{trading_date}/manifest.json",
                "manifest_file_sha256": _file_sha256(
                    root / "float-test" / trading_date / "manifest.json"
                ),
                "manifest_content_sha256": float_date["content_sha256"],
            }
        )

        news_date = {
            "artifact_id": "news-test",
            "trading_date": trading_date,
            "acquisition_profile_union": PROFILE_UNION_MANIFEST,
            "strategy_profiles_modified": False,
            "source_market_candidates_sha256": candidate_payload[
                "content_sha256"
            ],
            "source_market_discovery_manifest_sha256": _fingerprint(market_date),
            "source_float_records_sha256": float_date["summary"][
                "records_sha256"
            ],
            "source_float_manifest_sha256": float_date["content_sha256"],
            "source_float_target_basis_sha256": target_basis_payload[
                "content_sha256"
            ],
        }
        news_children.append(news_date)
        _write_json(root / "news-test" / trading_date / "manifest.json", news_date)
        _write_json(
            root / "news-test" / trading_date / "news-records.json",
            {"events": [], "statuses": [{"symbol": "AAA"}]},
        )

        input_date = {
            "artifact_id": "inputs-test",
            "trading_date": trading_date,
            "acquisition_profile_union": PROFILE_UNION_MANIFEST,
            "strategy_profiles_modified": False,
            "basis": {
                "displayed_price": "raw_candidate_close",
                "cumulative_volume": "raw_candidate_volume",
                "percent_gain": "split_target_close_over_split_previous_close",
                "cross_sectional_rank": (
                    "split_target_close_over_split_previous_close"
                ),
                "raw_split_candidate_timestamp_coverage_required_equal": True,
            },
            "summary": {
                "compressed_size_bytes": 10,
                "logical_records_sha256": _fingerprint(f"inputs:{trading_date}"),
            },
        }
        input_date["source_hashes"] = {
            "identity_resolved_membership": MEMBERSHIP_SHA,
            "market_candidates": candidate_payload["content_sha256"],
            "market_discovery_manifest": _fingerprint(market_date),
            "causal_float_records": float_date["summary"]["records_sha256"],
            "causal_float_manifest": _fingerprint(float_date),
            "publication_timed_news_events": _fingerprint([]),
            "publication_timed_news_statuses": _fingerprint([{"symbol": "AAA"}]),
            "publication_timed_news_manifest": _fingerprint(news_date),
            "reacquired_market_inputs": input_date["summary"][
                "logical_records_sha256"
            ],
        }
        input_date["content_sha256"] = _fingerprint(input_date)
        input_children.append(input_date)
        _write_json(root / "inputs-test" / trading_date / "manifest.json", input_date)

        rows = [{"symbol": "AAA", "trading_date": trading_date}]
        snapshot_payload = {"trading_date": trading_date, "rows": rows}
        snapshot_payload["content_sha256"] = _fingerprint(snapshot_payload)
        scanner_date = {
            "artifact_id": "scanner-test",
            "trading_date": trading_date,
            "strategy_profile": PROFILE_MANIFEST,
            "acquisition_profile_union": PROFILE_UNION_MANIFEST,
            "strategy_profiles_modified": False,
        }
        scanner_date["content_sha256"] = _fingerprint(scanner_date)
        scanner_children.append(scanner_date)
        _write_json(root / "scanner-test" / trading_date / "manifest.json", scanner_date)
        _write_json(
            root / "scanner-test" / trading_date / "scanner-snapshot.json",
            snapshot_payload,
        )

    market_root = {
        "artifact_id": "market-test",
        "dates": list(EXPECTED_DATES),
        "discovery_policy": {"id": "market-test"},
        "acquisition_profile_union": PROFILE_UNION_MANIFEST,
        "source_membership_bundle_sha256": "1" * 64,
        "date_manifests": market_children,
        "eligibility": {"causal_market_discovery_complete": True},
    }
    market_root["content_sha256"] = _fingerprint(
        {
            key: market_root[key]
            for key in (
                "discovery_policy",
                "source_membership_bundle_sha256",
                "date_manifests",
            )
        }
    )
    _write_json(root / "market-test" / "manifest.json", market_root)

    float_root = {
        "artifact_id": "float-test",
        "dates": list(EXPECTED_DATES),
        "float_policy": {"id": "float-test"},
        "source_market_discovery_bundle_sha256": market_root["content_sha256"],
        "date_manifests": float_commitments,
        "eligibility": {"point_in_time_float_decisions_frozen": True},
    }
    float_root["content_sha256"] = _fingerprint(float_root)
    _write_json(root / "float-test" / "manifest.json", float_root)

    news_root = {
        "artifact_id": "news-test",
        "dates": list(EXPECTED_DATES),
        "news_policy": {"id": "news-test"},
        "temporal_boundary": {"causal": True},
        "acquisition_profile_union": PROFILE_UNION_MANIFEST,
        "strategy_profiles_modified": False,
        "source_market_discovery_bundle_sha256": market_root["content_sha256"],
        "source_float_bundle_sha256": float_root["content_sha256"],
        "date_manifests": news_children,
        "fatal_provider_errors": [],
        "eligibility": {"publication_timed_news_frozen": True},
    }
    news_root["content_sha256"] = _fingerprint(
        {
            key: news_root[key]
            for key in (
                "news_policy",
                "temporal_boundary",
                "source_market_discovery_bundle_sha256",
                "source_float_bundle_sha256",
                "date_manifests",
            )
        }
    )
    _write_json(root / "news-test" / "manifest.json", news_root)

    input_root = {
        "artifact_id": "inputs-test",
        "dates": list(EXPECTED_DATES),
        "date_manifests": input_children,
        "acquisition_profile_union": PROFILE_UNION_MANIFEST,
        "strategy_profiles_modified": False,
        "source_bundle_hashes": {
            "membership": "1" * 64,
            "market": market_root["content_sha256"],
            "float": float_root["content_sha256"],
            "news": news_root["content_sha256"],
        },
        "replay_boundary": {"canonical_runtime_inputs_persisted": True},
    }
    input_root["content_sha256"] = _fingerprint(input_root)
    _write_json(root / "inputs-test" / "manifest.json", input_root)

    scanner_root = {
        "artifact_id": "scanner-test",
        "dates": list(EXPECTED_DATES),
        "date_manifests": scanner_children,
        "acquisition_profile_union": PROFILE_UNION_MANIFEST,
        "strategy_profiles_modified": False,
        "source_bundle_hashes": {
            "membership": "1" * 64,
            "market": market_root["content_sha256"],
            "float": float_root["content_sha256"],
            "news": news_root["content_sha256"],
        },
        "source_input_bundle_sha256": input_root["content_sha256"],
        "eligibility": {"candidate_minute_dispositions_frozen": True},
    }
    scanner_root["content_sha256"] = _fingerprint(scanner_root)
    _write_json(root / "scanner-test" / "manifest.json", scanner_root)


def _fake_apis(*, replay_matches: bool = True) -> DeepValidationAPIs:
    def load_identity(root: Path, *, trading_date: str):
        return (
            [{"ticker": "AAA"}],
            _identity_payload(trading_date),
            json.loads((root / "manifest.json").read_text(encoding="utf-8")),
        )

    def load_market(root: Path):
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        payload = json.loads(
            (root / "market-candidates.json").read_text(encoding="utf-8")
        )
        return list(payload["rows"]), payload, manifest

    def load_float(root: Path, **_kwargs):
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        return [{"symbol": "AAA"}], manifest

    def load_target_basis(path: Path, **_kwargs):
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload["rows"]), payload

    def load_float_root(
        root: Path,
        *,
        expected_dates,
        expected_source_market_discovery_bundle_sha256,
    ):
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        unsigned = {
            key: value for key, value in manifest.items() if key != "content_sha256"
        }
        if manifest.get("content_sha256") != _fingerprint(unsigned):
            raise ValueError("float root content hash mismatch")
        if manifest.get("dates") != list(expected_dates):
            raise ValueError("float root dates changed")
        if (
            manifest.get("source_market_discovery_bundle_sha256")
            != expected_source_market_discovery_bundle_sha256
        ):
            raise ValueError("float source market hash changed")
        for commitment in manifest["date_manifests"]:
            path = root / commitment["manifest"]
            child = json.loads(path.read_text(encoding="utf-8"))
            if (
                _file_sha256(path) != commitment["manifest_file_sha256"]
                or child.get("content_sha256")
                != commitment["manifest_content_sha256"]
            ):
                raise ValueError("float date commitment changed")
        return manifest

    def load_news(root: Path, **_kwargs):
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        return [], [{"symbol": "AAA"}], manifest

    def load_inputs(root: Path, **_kwargs):
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        trading_date = date.fromisoformat(str(manifest["trading_date"]))
        return (
            SimpleNamespace(
                trading_date=trading_date,
                membership_symbols=("AAA",),
                candidate_symbols=("AAA",),
                previous_close_by_symbol={"AAA": 1.0},
                rank_split_minute_bars_by_symbol={},
                candidate_raw_minute_bars_by_symbol={},
                candidate_exact_rvol_by_symbol={},
                source_hashes=dict(manifest["source_hashes"]),
            ),
            manifest,
        )

    def load_scanner(root: Path, **_kwargs):
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        payload = json.loads(
            (root / "scanner-snapshot.json").read_text(encoding="utf-8")
        )
        return list(payload["rows"]), payload, manifest

    def replay_rows(*, trading_date: date, **_kwargs):
        rows = [{"symbol": "AAA", "trading_date": trading_date.isoformat()}]
        return rows if replay_matches else [*rows, {"symbol": "TAMPER"}]

    return DeepValidationAPIs(
        identity_policy_id="identity-test",
        market_policy_id="market-test",
        float_policy_id="float-test",
        news_policy_id="news-test",
        scanner_artifact_id="scanner-test",
        source_input_artifact_id="inputs-test",
        load_identity=load_identity,
        load_market=load_market,
        load_target_basis=load_target_basis,
        load_float_root=load_float_root,
        load_float=load_float,
        load_news=load_news,
        load_source_inputs=load_inputs,
        load_scanner=load_scanner,
        replay_rows=replay_rows,
        profile_manifest=lambda _profile: PROFILE_MANIFEST,
        profile_union_manifest=lambda: PROFILE_UNION_MANIFEST,
        validate_profile=lambda _profile: None,
    )


class SealedHistoricalSourceAcquisitionV04Tests(unittest.TestCase):
    def test_strict_report_round_trip(self) -> None:
        report = build_acquisition_report_v04(**_report_kwargs())
        validate_acquisition_report_v04(report)
        self.assertTrue(report["source_acquisition_gate_passed"])
        self.assertEqual(
            set(report["request_budget"]["observed_attempts_by_host"]),
            {"api.massive.com", "data.alpaca.markets", "data.sec.gov"},
        )

    def test_count_maps_require_exact_dates_and_real_nonnegative_ints(self) -> None:
        for invalid in (True, -1, 1.5):
            with self.subTest(invalid=invalid):
                summary = _valid_summary()
                summary["candidate_counts"][EXPECTED_DATES[0]] = invalid
                with self.assertRaisesRegex(ValueError, "candidate counts"):
                    validate_source_summary_v04(summary)
        summary = _valid_summary()
        summary["candidate_counts"].pop(EXPECTED_DATES[-1])
        with self.assertRaisesRegex(ValueError, "exactly the frozen 30 dates"):
            validate_source_summary_v04(summary)

        summary = _valid_summary()
        summary["candidate_counts"][EXPECTED_DATES[0]] = (
            MAX_CANDIDATES_PER_DATE_V04 + 1
        )
        with self.assertRaisesRegex(ValueError, "exceeds 100"):
            validate_source_summary_v04(summary)

    def test_request_hosts_are_exact_and_positive_integer_counted(self) -> None:
        for mutation in ("missing", "extra", "zero", "bool"):
            with self.subTest(mutation=mutation):
                values = _report_kwargs()
                budget = values["request_budget"]
                if mutation == "missing":
                    budget["by_host"].pop("data.sec.gov")
                    budget["total_attempts"] = 3
                elif mutation == "extra":
                    budget["by_host"]["example.com"] = 1
                    budget["total_attempts"] = 7
                elif mutation == "zero":
                    budget["by_host"]["data.sec.gov"] = 0
                    budget["total_attempts"] = 3
                else:
                    budget["by_host"]["data.sec.gov"] = True
                    budget["total_attempts"] = 4
                with self.assertRaisesRegex(ValueError, "provider"):
                    build_acquisition_report_v04(**values)

    def test_gates_must_be_real_boolean_true(self) -> None:
        summary = _valid_summary()
        summary["gates"]["news_complete"] = 1
        with self.assertRaisesRegex(ValueError, "real booleans true"):
            validate_source_summary_v04(summary)

    def test_sha_maps_must_be_nonempty_exact_and_valid(self) -> None:
        summary = _valid_summary()
        summary["source_hashes"] = {}
        with self.assertRaisesRegex(ValueError, "nonempty SHA-256 map"):
            validate_source_summary_v04(summary)
        summary = _valid_summary()
        summary["source_hashes"]["extra"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "keys changed"):
            validate_source_summary_v04(summary)

        summary = _valid_summary()
        summary["manifest_file_sha256"].pop(
            next(iter(summary["manifest_file_sha256"]))
        )
        with self.assertRaisesRegex(ValueError, "manifest file hashes keys changed"):
            validate_source_summary_v04(summary)

        summary = _valid_summary()
        summary["date_hashes"][EXPECTED_DATES[0]]["market_manifest_file"] = (
            "0" * 64
        )
        with self.assertRaisesRegex(ValueError, "date manifest file hashes disagree"):
            validate_source_summary_v04(summary)

        summary = _valid_summary()
        summary["source_hashes"]["census_file"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "census source hash differs"):
            validate_source_summary_v04(summary)

    def test_report_and_checkpoint_require_the_exact_frozen_authorization_hash(self) -> None:
        values = _report_kwargs()
        values["authorization_content_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "not the frozen v0.4 child"):
            build_acquisition_report_v04(**values)

        report = build_acquisition_report_v04(**_report_kwargs())
        report["authorization_content_sha256"] = "0" * 64
        report["source_checkpoint"]["authorization"][
            "authorization_content_sha256"
        ] = "0" * 64
        report["source_checkpoint"]["content_sha256"] = _fingerprint(
            {
                key: value
                for key, value in report["source_checkpoint"].items()
                if key != "content_sha256"
            }
        )
        report["content_sha256"] = _fingerprint(
            {key: value for key, value in report.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "authorization hash changed"):
            validate_acquisition_report_v04(report)

    def test_serialized_report_loader_rejects_duplicate_and_nonfinite_json(self) -> None:
        report = build_acquisition_report_v04(**_report_kwargs())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
            path.write_text(rendered, encoding="utf-8")
            self.assertEqual(load_acquisition_report_v04(path), report)

            path.write_text(
                rendered.replace(
                    '  "authorization_id":',
                    '  "authorization_id": "shadow",\n  "authorization_id":',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_acquisition_report_v04(path)

            path.write_text(
                rendered.replace(
                    '"observed_retained_bytes": 1000000',
                    '"observed_retained_bytes": NaN',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "non-finite JSON constant"):
                load_acquisition_report_v04(path)

    def test_checkpoint_final_tree_is_cross_bound_to_source_summary(self) -> None:
        report = build_acquisition_report_v04(**_report_kwargs())
        report["source_summary"]["source_tree_content_sha256"] = "9" * 64
        report["content_sha256"] = _fingerprint(
            {key: value for key, value in report.items() if key != "content_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "checkpoint tree differs"):
            validate_acquisition_report_v04(report)

    def test_real_v04_completed_file_census_rejects_one_extra_file(self) -> None:
        paths = expected_source_file_paths_v04()
        self.assertEqual(len(paths), 767)
        self.assertEqual(len(expected_manifest_paths_v04()), 191)
        apis = replace(
            _fake_apis(),
            identity_policy_id="identity-resolved-universe-v0.1",
            market_policy_id="causal-market-discovery-v0.3",
            float_policy_id="causal-sec-float-v0.2",
            news_policy_id="causal-alpaca-news-v0.2",
            scanner_artifact_id="causal-scanner-snapshot-v0.3",
            source_input_artifact_id="causal-scanner-source-inputs-v0.2",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            for relative in paths:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"{}\n" if path.suffix == ".json" else b"x\n")
            _validate_source_tree_shape(root, apis=apis)
            checkpoint_inventory = inventory_source_tree(
                root,
                allow_scanner_snapshot_addition=True,
            )
            commitment = _source_tree_commitment(root)
            self.assertEqual(
                commitment["tree_content_sha256"],
                checkpoint_inventory["tree_content_sha256"],
            )
            self.assertEqual(
                commitment["file_count"], checkpoint_inventory["file_count"]
            )
            (root / EXPECTED_DATES[0] / "rogue.bin").write_bytes(b"rogue")
            with self.assertRaisesRegex(ValueError, "completed file paths changed"):
                _validate_source_tree_shape(root, apis=apis)

    def test_provenance_requires_commit_tree_dispatcher_ref_run_and_attempt(self) -> None:
        mutations = {
            "authorization_tree_sha": "bad",
            "dispatcher_workflow_sha": "e" * 39,
            "dispatcher_workflow_ref": "unbound.yml",
            "workflow_run_id": 0,
            "workflow_run_attempt": True,
        }
        for field, invalid in mutations.items():
            with self.subTest(field=field):
                values = _report_kwargs()
                values[field] = invalid
                with self.assertRaises(ValueError):
                    build_acquisition_report_v04(**values)

        values = _report_kwargs()
        values["workflow_run_attempt"] = 1.0
        with self.assertRaisesRegex(ValueError, "integer"):
            build_acquisition_report_v04(**values)
        for field, invalid in (
            ("workflow_run_id", "00123"),
            (
                "dispatcher_workflow_ref",
                "RoomyRems/momentumbot/.github/workflows/other.yml@refs/heads/main",
            ),
            (
                "dispatcher_workflow_ref",
                "RoomyRems/momentumbot/.github/workflows/"
                "sealed-historical-source-acquisition-v04.yml@"
                "refs/heads/phase-3-historical-snapshot",
            ),
        ):
            with self.subTest(field=field, invalid=invalid):
                values = _report_kwargs()
                values[field] = invalid
                with self.assertRaises(ValueError):
                    build_acquisition_report_v04(**values)

    def test_report_nested_fields_and_false_booleans_are_strict(self) -> None:
        values = _report_kwargs()
        values["request_budget"]["unexpected"] = "ignored"
        with self.assertRaisesRegex(ValueError, "fields changed"):
            build_acquisition_report_v04(**values)

        report = build_acquisition_report_v04(**_report_kwargs())
        report["cost"]["databento_called"] = 0
        report["content_sha256"] = _fingerprint(
            {
                key: value
                for key, value in report.items()
                if key != "content_sha256"
            }
        )
        with self.assertRaisesRegex(ValueError, "cost boundary changed"):
            validate_acquisition_report_v04(report)

        for section, field in (
            ("request_budget", "maximum_total_http_attempts"),
            ("retention", "maximum_retained_bytes"),
        ):
            with self.subTest(section=section):
                changed = build_acquisition_report_v04(**_report_kwargs())
                changed[section][field] = float(changed[section][field])
                changed["content_sha256"] = _fingerprint(
                    {
                        key: value
                        for key, value in changed.items()
                        if key != "content_sha256"
                    }
                )
                with self.assertRaises(ValueError):
                    validate_acquisition_report_v04(changed)

    def test_default_loader_round_trip_replays_normalized_source_tape(self) -> None:
        apis = _default_validation_apis()
        profile = replace(
            historical_profile_union_v0_1(),
            no_new_entries_after=time(7, 2),
        )
        trading_date = date(2025, 5, 30)
        timestamp = pd.Timestamp("2025-05-30T11:00:00Z")
        rank_frames = {
            "AAA": pd.DataFrame({"close": [10.0]}, index=[timestamp])
        }
        raw_frames = {
            "AAA": pd.DataFrame(
                {"close": [10.0], "volume": [1_000.0]},
                index=[timestamp],
            )
        }
        rvol = {"AAA": pd.Series([6.0], index=[timestamp])}
        candidates = [
            {
                "symbol": "AAA",
                "previous_close": 8.0,
                "first_market_qualified_bar_started_at": timestamp.isoformat(),
                "first_market_qualified_at": (
                    timestamp + pd.Timedelta(minutes=1)
                ).isoformat(),
            }
        ]
        float_records = [
            {
                "symbol": "AAA",
                "float_classification": "pass",
                "float_pillar_pass": True,
                "estimated_float_shares": 5_000_000,
                "float_asof": "2025-05-29T12:00:00+00:00",
                "method": "test-causal-float",
                "sec_status": "success",
            }
        ]
        news_statuses = [{"symbol": "AAA", "provider_status": "success"}]
        upstream = {
            name: hashlib.sha256(name.encode("ascii")).hexdigest()
            for name in SOURCE_HASH_NAMES[:-1]
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source-input"
            write_scanner_source_input_bundle(
                source_root,
                trading_date=trading_date,
                profile=profile,
                membership_symbols=["AAA"],
                candidate_symbols=["AAA"],
                previous_close_by_symbol={"AAA": 8.0},
                rank_split_minute_bars_by_symbol=rank_frames,
                candidate_raw_minute_bars_by_symbol=raw_frames,
                candidate_exact_rvol_by_symbol=rvol,
                upstream_source_hashes=upstream,
            )
            inputs, source_manifest = apis.load_source_inputs(
                source_root,
                profile=profile,
            )
            rows = apis.replay_rows(
                trading_date=trading_date,
                profile=profile,
                candidate_rows=candidates,
                float_records=float_records,
                news_events=[],
                news_statuses=news_statuses,
                membership_symbols=inputs.membership_symbols,
                previous_close_by_symbol=inputs.previous_close_by_symbol,
                rank_split_minute_bars_by_symbol=(
                    inputs.rank_split_minute_bars_by_symbol
                ),
                candidate_raw_minute_bars_by_symbol=(
                    inputs.candidate_raw_minute_bars_by_symbol
                ),
                candidate_exact_rvol_by_symbol=(
                    inputs.candidate_exact_rvol_by_symbol
                ),
            )
            payload, manifest = build_causal_scanner_snapshot_artifacts(
                trading_date=trading_date,
                profile=profile,
                candidate_rows=candidates,
                membership_symbols=inputs.membership_symbols,
                rows=rows,
                source_hashes=inputs.source_hashes,
                previous_close_by_symbol=inputs.previous_close_by_symbol,
                rank_split_minute_bars_by_symbol=(
                    inputs.rank_split_minute_bars_by_symbol
                ),
                candidate_raw_minute_bars_by_symbol=(
                    inputs.candidate_raw_minute_bars_by_symbol
                ),
            )
            snapshot_root = root / "snapshot"
            snapshot_root.mkdir()
            _write_json(snapshot_root / "scanner-snapshot.json", payload)
            _write_json(snapshot_root / "manifest.json", manifest)
            loaded_rows, loaded_payload, loaded_manifest = apis.load_scanner(
                snapshot_root,
                candidate_rows=candidates,
                profile=profile,
                source_inputs=inputs,
            )
        self.assertEqual(source_manifest["basis"]["cross_sectional_rank"], (
            "split_target_close_over_split_previous_close"
        ))
        self.assertEqual(loaded_rows, rows)
        self.assertEqual(loaded_payload, payload)
        self.assertEqual(loaded_manifest, manifest)

    def test_deep_summary_validates_all_30_dates_and_exact_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_synthetic_root(root)
            summary = summarize_source_root_v04(
                root,
                profile=historical_profile_union_v0_1(),
                _apis=_fake_apis(),
            )
        self.assertEqual(summary["dates"], list(EXPECTED_DATES))
        self.assertEqual(set(summary["date_hashes"]), set(EXPECTED_DATES))
        self.assertTrue(all(summary["provider_free_replay_exact_by_date"].values()))

    def test_deep_summary_rejects_root_date_manifest_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_synthetic_root(root)
            path = root / "inputs-test" / EXPECTED_DATES[0] / "manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["tampered"] = True
            _write_json(path, payload)
            with self.assertRaisesRegex(ValueError, "root/date manifest mismatch"):
                summarize_source_root_v04(
                    root,
                    profile=historical_profile_union_v0_1(),
                    _apis=_fake_apis(),
                )

    def test_deep_summary_rejects_profile_union_or_rank_basis_tamper(self) -> None:
        for target in ("profile_union", "rank_basis", "source_lineage"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "source"
                _build_synthetic_root(root)
                if target == "profile_union":
                    path = root / "market-test" / "manifest.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["acquisition_profile_union"] = {"profile_union_id": "bad"}
                    _write_json(path, payload)
                    pattern = "root content hash mismatch|profile union changed"
                else:
                    path = root / "inputs-test" / EXPECTED_DATES[0] / "manifest.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if target == "rank_basis":
                        payload["basis"]["cross_sectional_rank"] = "raw"
                        pattern = "normalized rank basis changed"
                    else:
                        payload["source_hashes"]["market_candidates"] = "0" * 64
                        pattern = "upstream lineage changed"
                    payload["content_sha256"] = _fingerprint(
                        {
                            key: value
                            for key, value in payload.items()
                            if key != "content_sha256"
                        }
                    )
                    _write_json(path, payload)
                    parent_path = root / "inputs-test" / "manifest.json"
                    parent = json.loads(parent_path.read_text(encoding="utf-8"))
                    parent["date_manifests"][0] = payload
                    parent["content_sha256"] = _fingerprint(
                        {
                            key: value
                            for key, value in parent.items()
                            if key != "content_sha256"
                        }
                    )
                    _write_json(parent_path, parent)
                    scanner_parent_path = root / "scanner-test" / "manifest.json"
                    scanner_parent = json.loads(
                        scanner_parent_path.read_text(encoding="utf-8")
                    )
                    scanner_parent["source_input_bundle_sha256"] = parent[
                        "content_sha256"
                    ]
                    scanner_parent["content_sha256"] = _fingerprint(
                        {
                            key: value
                            for key, value in scanner_parent.items()
                            if key != "content_sha256"
                        }
                    )
                    _write_json(scanner_parent_path, scanner_parent)
                with self.assertRaisesRegex(ValueError, pattern):
                    summarize_source_root_v04(
                        root,
                        profile=historical_profile_union_v0_1(),
                        _apis=_fake_apis(),
                    )

    def test_deep_summary_rejects_unexpected_manifest_or_date_directory(self) -> None:
        for target in ("manifest", "date_directory"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "source"
                _build_synthetic_root(root)
                if target == "manifest":
                    _write_json(root / "rogue" / "manifest.json", {"rogue": True})
                    pattern = "top-level directories changed|manifest paths changed"
                else:
                    (root / "scanner-test" / "2099-01-01").mkdir()
                    pattern = "date directories changed"
                with self.assertRaisesRegex(ValueError, pattern):
                    summarize_source_root_v04(
                        root,
                        profile=historical_profile_union_v0_1(),
                        _apis=_fake_apis(),
                    )

    def test_deep_summary_strictly_decodes_every_json_source_file(self) -> None:
        for mutation, pattern in (
            ("duplicate", "duplicate JSON key"),
            ("nonfinite", "non-finite JSON constant"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "source"
                _build_synthetic_root(root)
                path = (
                    root
                    / "market-test"
                    / EXPECTED_DATES[0]
                    / "market-candidates.json"
                )
                rendered = path.read_text(encoding="utf-8")
                if mutation == "duplicate":
                    rendered = rendered.replace(
                        '  "trading_date":',
                        '  "trading_date": "shadow",\n  "trading_date":',
                        1,
                    )
                else:
                    rendered = rendered.replace(
                        '  "rows": [',
                        '  "nonfinite": NaN,\n  "rows": [',
                        1,
                    )
                path.write_text(rendered, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, pattern):
                    summarize_source_root_v04(
                        root,
                        profile=historical_profile_union_v0_1(),
                        _apis=_fake_apis(),
                    )

    def test_deep_summary_rejects_provider_free_replay_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _build_synthetic_root(root)
            with self.assertRaisesRegex(ValueError, "provider-free scanner replay differs"):
                summarize_source_root_v04(
                    root,
                    profile=historical_profile_union_v0_1(),
                    _apis=_fake_apis(replay_matches=False),
                )

    def test_report_hash_tamper_is_rejected(self) -> None:
        report = build_acquisition_report_v04(**_report_kwargs())
        changed = copy.deepcopy(report)
        changed["retention"]["observed_retained_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "report hash mismatch"):
            validate_acquisition_report_v04(changed)


if __name__ == "__main__":
    unittest.main()
