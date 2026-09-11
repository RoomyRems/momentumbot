import gzip
import io
import json
from pathlib import Path
import unittest
import zipfile

import pandas as pd

from momentumbot.research import early_pullback_selection_v01 as experiment


ROOT = Path(__file__).resolve().parents[1]


def bars():
    return pd.DataFrame(
        [(10, 9, 100), (9.8, 9.2, 70), (10.2, 9.5, 120),
         (10, 9.6, 50), (10.4, 9.8, 150), (10.1, 9.9, 40)],
        columns=["high", "low", "volume"],
        index=pd.date_range("2024-01-02T12:00:00Z", periods=6, freq="10s"),
    )


def select(frame, **changes):
    kwargs = dict(candidate_qualified_at=bars().index[0],
                  source_bar_start=frame.index[-1],
                  decision_at=frame.index[-1] + pd.Timedelta(seconds=10))
    kwargs.update(changes)
    return experiment.select_causal_prefix(frame, **kwargs)


class CausalEarlyPullbackTests(unittest.TestCase):
    def test_first_and_second_selected_third_withheld(self):
        for length, ordinal in ((2, 1), (4, 2), (6, 3)):
            with self.subTest(ordinal=ordinal):
                result = select(bars().iloc[:length])
                self.assertEqual(result["pullback_number"], ordinal)
                self.assertEqual(result["selected"], ordinal <= 2)
                self.assertFalse(result["order_authorized"])
                experiment.verify_frozen(result)

    def test_withheld_prefix_does_not_reset_on_next_bar(self):
        frame = bars()
        frame.loc[frame.index[-1] + pd.Timedelta(seconds=10)] = (10.2, 10, 30)
        self.assertEqual(select(frame)["pullback_number"], 3)
        self.assertFalse(select(frame)["selected"])

    def test_qualification_anchor_is_not_first_entry(self):
        frame = bars().iloc[2:]
        result = select(frame, candidate_qualified_at=frame.index[0])
        self.assertEqual(result["pullback_number"], 2)

    def test_equal_running_high_does_not_confirm_resumption(self):
        frame = bars().iloc[:4].copy()
        frame.iloc[2, 0] = 10
        self.assertEqual(select(frame)["pullback_number"], 1)

    def test_prefix_only_no_fill_or_label_inputs(self):
        result = select(bars())
        self.assertFalse(result["original_trigger_authenticated_by_this_helper"])
        for column in ("ross_pullback_number", "pnl", "future_high", "symbol", "open"):
            frame = bars().assign(**{column: 1})
            with self.subTest(column=column), self.assertRaises(ValueError):
                select(frame)

    def test_decision_cannot_use_incomplete_or_expired_bar(self):
        frame = bars()
        for seconds in (0, 9.999, 20, 21):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                select(frame, decision_at=frame.index[-1] + pd.Timedelta(seconds=seconds))
        self.assertFalse(select(frame, decision_at=frame.index[-1] +
                                pd.Timedelta(seconds=19.999))["selected"])

    def test_future_prefix_is_rejected_not_silently_sliced(self):
        with self.assertRaises(ValueError):
            select(bars(), source_bar_start=bars().index[-2])

    def test_invalid_indices_fail(self):
        frames = [bars().iloc[::-1], pd.concat([bars(), bars().iloc[-1:]])]
        naive = bars().copy()
        naive.index = naive.index.tz_localize(None)
        frames.append(naive)
        off_grid = bars().copy()
        off_grid.index = off_grid.index + pd.Timedelta(seconds=1)
        frames.append(off_grid)
        missing_time = bars().copy()
        missing_time.index = pd.DatetimeIndex([*bars().index[:-1], pd.NaT])
        frames.append(missing_time)
        for frame in frames:
            with self.subTest(index=str(frame.index)), self.assertRaises(ValueError):
                select(frame)

    def test_empty_prefix_fails(self):
        with self.assertRaises(ValueError):
            experiment.select_causal_prefix(bars().iloc[:0],
                candidate_qualified_at=bars().index[0], source_bar_start=bars().index[-1],
                decision_at=bars().index[-1] + pd.Timedelta(seconds=10))

    def test_naive_or_missing_clock_fails(self):
        for key in ("candidate_qualified_at", "source_bar_start", "decision_at"):
            for value in (pd.NaT, pd.Timestamp("2024-01-02")):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    select(bars(), **{key: value})

    def test_prequalification_prefix_fails(self):
        with self.assertRaises(ValueError):
            select(bars(), candidate_qualified_at=bars().index[1])

    def test_invalid_market_values_fail(self):
        for column, value in (("high", float("nan")), ("high", float("inf")),
                              ("low", 0), ("low", 20), ("volume", -1)):
            frame = bars().astype(float)
            frame.loc[frame.index[1], column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                select(frame)
        for value in ("10", True):
            frame = bars().astype(object)
            frame.iloc[0, 0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                select(frame)

    def test_timestamp_resolution_does_not_change_decision(self):
        reference = select(bars())
        for unit in ("ns", "us", "ms", "s"):
            frame = bars().copy()
            frame.index = frame.index.as_unit(unit)
            with self.subTest(unit=unit):
                self.assertEqual(select(frame), reference)

    def test_input_not_mutated_and_prefix_identity_changes_with_market_evidence(self):
        frame = bars()
        original = frame.copy(deep=True)
        result = select(frame)
        pd.testing.assert_frame_equal(frame, original)
        frame.iloc[-1, 2] += 1
        self.assertNotEqual(select(frame)["ordinal_prefix_sha256"], result["ordinal_prefix_sha256"])


class PanelSelectionTests(unittest.TestCase):
    def test_date_only_inventory_includes_path_and_nested_archives(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("2025-02-04/data.json.gz", gzip.compress(
                b'{"date":"2025-02-05", "outcome":"DO_NOT_PERSIST_ME"}'))
        result = experiment.build_exclusions([
            ("2025-02-03.py", b"2025-02-30 2024-02-01 2025-02-06"),
            ("archive.zip", buffer.getvalue()),
        ])
        self.assertEqual(result["excluded_dates"],
                         ["2025-02-03", "2025-02-04", "2025-02-05", "2025-02-06"])
        self.assertNotIn("DO_NOT_PERSIST_ME", json.dumps(result))

    def test_inventory_order_irrelevant_and_bytes_bound(self):
        files = [("b.json", b"2025-02-03"), ("a.txt", b"2025-02-04")]
        left = experiment.build_exclusions(files)
        self.assertEqual(left, experiment.build_exclusions(reversed(files)))
        files[0] = ("b.json", b"2025-02-03 ")
        right = experiment.build_exclusions(files)
        self.assertEqual(left["excluded_dates"], right["excluded_dates"])
        self.assertNotEqual(left["inventory_sha256"], right["inventory_sha256"])

    def test_empty_duplicate_or_corrupt_inventory_fails(self):
        for files in ([], [("a", b""), ("a", b"")], [("a.gz", b"bad")]):
            with self.subTest(files=files), self.assertRaises((ValueError, OSError)):
                experiment.build_exclusions(files)

    def test_selection_deterministic_full_block_no_excluded_date(self):
        exclusions = experiment.build_exclusions([("a", b"2025-02-03 2025-02-04")])
        left = experiment.select_panel(exclusions)
        self.assertEqual(left, experiment.select_panel(exclusions))
        self.assertEqual(len(left["selected_dates"]), 30)
        self.assertFalse(set(left["selected_dates"]) & set(exclusions["excluded_dates"]))
        self.assertFalse(left["date_replacement_allowed"])
        self.assertFalse(left["seed_retry_allowed"])

    def test_exhausted_panel_fails_without_relaxing_exclusions(self):
        exclusions = experiment.build_exclusions([
            ("all", " ".join(experiment.bounded_full_sessions()).encode())])
        with self.assertRaisesRegex(ValueError, "no complete fresh"):
            experiment.select_panel(exclusions)

    def test_tampered_exclusion_hash_and_parent_fail(self):
        exclusions = experiment.build_exclusions([("a", b"2025-02-03")])
        exclusions["excluded_dates"] = []
        with self.assertRaisesRegex(ValueError, "content hash"):
            experiment.select_panel(exclusions)
        exclusions.pop("content_sha256")
        exclusions["parent_commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "parent"):
            experiment.select_panel(experiment.freeze(exclusions))

    def test_duplicate_exclusions_fail_even_if_rehashed(self):
        exclusions = experiment.build_exclusions([("a", b"2025-02-03")])
        exclusions.pop("content_sha256")
        exclusions["excluded_dates"] *= 2
        with self.assertRaisesRegex(ValueError, "sorted and unique"):
            experiment.select_panel(experiment.freeze(exclusions))


class SavedRegistrationTests(unittest.TestCase):
    def test_registration_and_implementation_bindings(self):
        contract = experiment.validate_registration(ROOT)
        self.assertEqual(contract["parent_commit"], experiment.PARENT)
        self.assertEqual(contract["status"], "registered_synthetic_mechanics_only_no_market_evaluation")

    def test_all_authority_closed_and_both_complete_arms_required(self):
        contract = experiment.validate_registration(ROOT)
        self.assertTrue(all(value is False for value in contract["authority"].values()))
        self.assertEqual(contract["evaluation"]["dated_records_both_arms"], 720)
        self.assertEqual(contract["evaluation"]["paths_per_arm"], 12)
        self.assertFalse(contract["causal_protocol"]["paired_historical_account_runner_implemented"])
        self.assertFalse(contract["causal_protocol"]["source_authentication_adapter_implemented"])

    def test_old_baseline_and_prior_exclusions_cannot_be_holdout(self):
        contract = experiment.validate_registration(ROOT)
        exclusions = json.loads((ROOT / experiment.EXCLUSION_PATH).read_bytes())
        baseline = json.loads((ROOT / "research/strategy/sealed-historical-walk-forward-v0.1.json").read_bytes())
        old = set(baseline["sampling_contract"]["selected_dates"])
        prior = json.loads((ROOT / "research/data-audits/sealed-historical-date-exclusions-v0.1.json").read_bytes())
        old.update(row["date"] for row in prior["excluded_dates"])
        self.assertTrue(old <= set(exclusions["excluded_dates"]))
        self.assertFalse(old & set(contract["sampling"]["selected_dates"]))
        self.assertFalse(exclusions["outside_repository_exposure_certified"])

    def test_saved_panel_reproduces_and_no_claim_of_fresh_external_exposure(self):
        contract = experiment.validate_registration(ROOT)
        exclusions = json.loads((ROOT / experiment.EXCLUSION_PATH).read_bytes())
        self.assertEqual(exclusions["content_sha256"], experiment.EXCLUSION_CONTENT_SHA256)
        self.assertEqual(contract["sampling"], experiment.select_panel(exclusions))
        self.assertEqual(contract["sampling"]["status"],
                         "repository_unreferenced_not_certified_unseen_outside_repository")


if __name__ == "__main__":
    unittest.main()
