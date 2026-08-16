from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from momentumbot.historical_float import (
    BasisObservation,
    build_causal_float_record,
    causal_float_records_fingerprint,
    causal_float_v0_1_manifest,
    estimate_float_row,
    float_evidence_available_at,
    load_causal_float_records,
    observe_basis,
    select_float_evidence,
    validate_causal_float_records,
)
from momentumbot.providers.sec_edgar import (
    OutstandingSharesDisclosure,
    ParsedCompanyFacts,
    PublicFloatDisclosure,
)


class HistoricalFloatTests(unittest.TestCase):
    def test_evidence_selection_excludes_disclosure_after_qualification(self) -> None:
        before = datetime(2025, 3, 1, 15, tzinfo=timezone.utc)
        after = datetime(2025, 5, 1, 15, tzinfo=timezone.utc)
        facts = ParsedCompanyFacts(
            public_float=(
                PublicFloatDisclosure(
                    cik="0000000001",
                    measure_date=date(2024, 6, 30),
                    public_float_usd=12_000_000,
                    filed_date=date(2025, 3, 1),
                    available_at=before,
                    accession="before-public",
                    form="10-K",
                ),
                PublicFloatDisclosure(
                    cik="0000000001",
                    measure_date=date(2025, 3, 31),
                    public_float_usd=2_000_000,
                    filed_date=date(2025, 5, 1),
                    available_at=after,
                    accession="future-public",
                    form="10-K/A",
                ),
            ),
            outstanding_shares=(
                OutstandingSharesDisclosure(
                    cik="0000000001",
                    measure_date=date(2024, 6, 30),
                    shares=8_000_000,
                    filed_date=date(2025, 3, 1),
                    available_at=before,
                    accession="before-shares",
                    form="10-K",
                ),
                OutstandingSharesDisclosure(
                    cik="0000000001",
                    measure_date=date(2025, 4, 30),
                    shares=5_000_000,
                    filed_date=date(2025, 5, 1),
                    available_at=after,
                    accession="future-shares",
                    form="10-Q",
                ),
            ),
        )

        selected = select_float_evidence(
            facts,
            symbol="AAA",
            cik="0000000001",
            first_market_qualified_at=datetime(
                2025, 4, 3, 11, tzinfo=timezone.utc
            ),
        )

        self.assertEqual(selected["public_float"]["accession"], "before-public")
        self.assertEqual(
            selected["current_outstanding"]["accession"], "before-shares"
        )
        self.assertNotIn("future", str(selected))
        self.assertEqual(float_evidence_available_at(selected), before.isoformat())

    def test_selected_evidence_produces_split_normalized_bound(self) -> None:
        candidate = {
            "symbol": "AAA",
            "cik": "0000000001",
            "first_market_qualified_at": "2025-04-03T11:00:00+00:00",
            "public_float": None,
            "anchor_outstanding": None,
            "current_outstanding": {
                "measure_date": "2025-02-01",
                "shares": 90_000_000,
                "accession": "shares",
                "available_at": "2025-03-01T15:00:00+00:00",
            },
        }
        observation = BasisObservation(
            requested_date="2025-02-01",
            observed_date="2025-01-31",
            raw_close=0.10,
            split_close=1.00,
            share_factor_to_target_basis=0.10,
        )

        row = estimate_float_row(
            candidate,
            {"current:2025-02-01": observation},
        )

        self.assertEqual(row.estimated_float_shares, 9_000_000)
        self.assertTrue(row.float_pillar_pass)
        self.assertEqual(row.method, "sec_outstanding_shares_upper_bound")

    def test_latest_measure_date_wins_over_later_old_amendment(self) -> None:
        facts = ParsedCompanyFacts(
            public_float=(),
            outstanding_shares=(
                OutstandingSharesDisclosure(
                    cik="0000000001",
                    measure_date=date(2025, 3, 31),
                    shares=8_000_000,
                    filed_date=date(2025, 4, 15),
                    available_at=datetime(
                        2025, 4, 15, 20, tzinfo=timezone.utc
                    ),
                    accession="newer-measure",
                    form="10-Q",
                ),
                OutstandingSharesDisclosure(
                    cik="0000000001",
                    measure_date=date(2024, 12, 31),
                    shares=20_000_000,
                    filed_date=date(2025, 4, 20),
                    available_at=datetime(
                        2025, 4, 20, 20, tzinfo=timezone.utc
                    ),
                    accession="later-old-amendment",
                    form="10-K/A",
                ),
            ),
        )

        selected = select_float_evidence(
            facts,
            symbol="AAA",
            cik="0000000001",
            first_market_qualified_at=datetime(
                2025, 4, 30, 11, tzinfo=timezone.utc
            ),
        )

        self.assertEqual(
            selected["current_outstanding"]["accession"], "newer-measure"
        )

    def test_basis_observation_never_uses_a_forward_price(self) -> None:
        index = pd.DatetimeIndex(["2025-02-03T00:00:00Z"])
        raw = pd.DataFrame({"close": [1.0]}, index=index)
        split = pd.DataFrame({"close": [10.0]}, index=index)

        observed = observe_basis(raw, split, date(2025, 2, 1))

        self.assertIsNone(observed.observed_date)
        self.assertIsNone(observed.share_factor_to_target_basis)

    def test_float_record_contract_rejects_tampered_future_evidence(self) -> None:
        selected = {
            "symbol": "AAA",
            "cik": "0000000001",
            "first_market_qualified_at": "2025-04-03T11:00:00+00:00",
            "public_float": None,
            "anchor_outstanding": None,
            "current_outstanding": None,
        }
        record = build_causal_float_record(
            selected,
            {},
            sec_status="sec_companyfacts_not_found",
        )
        candidate = {
            "symbol": "AAA",
            "selected_cik": "1",
            "first_market_qualified_at": "2025-04-03T11:00:00+00:00",
        }

        validate_causal_float_records([candidate], [record])
        record["selected_evidence"]["current_outstanding"] = {
            "shares": 1_000_000,
            "measure_date": "2025-04-03",
            "available_at": "2025-04-03T12:00:00+00:00",
            "accession": "future",
        }
        with self.assertRaisesRegex(ValueError, "future current_outstanding"):
            validate_causal_float_records([candidate], [record])

    def test_float_loader_verifies_source_counts_and_record_hash(self) -> None:
        selected = {
            "symbol": "AAA",
            "cik": "0000000001",
            "first_market_qualified_at": "2025-04-03T11:00:00+00:00",
            "public_float": None,
            "anchor_outstanding": None,
            "current_outstanding": None,
        }
        record = build_causal_float_record(
            selected,
            {},
            sec_status="sec_companyfacts_not_found",
        )
        candidate = {
            "symbol": "AAA",
            "selected_cik": "1",
            "first_market_qualified_at": "2025-04-03T11:00:00+00:00",
        }
        candidate_payload = {"content_sha256": "market-candidates"}
        manifest = {
            "artifact_id": "causal-sec-float-v0.1",
            "float_policy": causal_float_v0_1_manifest(),
            "source_market_candidates_sha256": "market-candidates",
            "summary": {
                "market_candidate_count": 1,
                "float_decision_count": 1,
                "float_pass_count": 0,
                "float_fail_count": 0,
                "float_unknown_fail_closed_count": 1,
                "provider_error_count": 0,
                "records_sha256": causal_float_records_fingerprint([record]),
            },
            "eligibility": {
                "complete_relative_to_market_candidates": True,
                "point_in_time_float_decisions_frozen": True,
                "full_feature_snapshot_complete": False,
            },
            "knowledge_policy": {
                "uses_benchmark_labels": False,
                "uses_future_filings": False,
                "raw_future_disclosures_persisted": False,
                "unknown_float_fails_closed": True,
            },
            "files": {"float_records": "float-records.json"},
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            records_path = root / "float-records.json"
            records_path.write_text(
                json.dumps({"rows": [record]}), encoding="utf-8"
            )
            (root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            rows, loaded_manifest = load_causal_float_records(
                root,
                candidate_rows=[candidate],
                candidate_payload=candidate_payload,
            )

            self.assertEqual(rows, [record])
            self.assertEqual(loaded_manifest, manifest)
            record["method"] = "tampered"
            records_path.write_text(
                json.dumps({"rows": [record]}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "record fingerprint"):
                load_causal_float_records(
                    root,
                    candidate_rows=[candidate],
                    candidate_payload=candidate_payload,
                )


if __name__ == "__main__":
    unittest.main()
