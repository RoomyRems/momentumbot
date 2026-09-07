"""Frozen evidence and offline gates for the historical record-order adapter."""
from __future__ import annotations

import ast
import base64
import copy
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path

from momentumbot.research import sealed_historical_execution_diagnostic_v01 as diagnostic
from momentumbot.research import sealed_historical_record_order_v01 as adapter
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal,
)

CONTRACT_PATH = f"research/strategy/{adapter.CONTRACT_ID}.json"
MODULE_PATH = "src/momentumbot/research/sealed_historical_record_order_v01.py"
FIXTURE_PATH = "tests/fixtures/sealed_historical_record_order_v01_gits.json"
FIXTURE_SHA = "a3b36b51b768a93ada4821d693cebc3225f7a0ee338e1a962adf240a5c022473"
AUDIT_PATH = "research/data-audits/sealed-historical-execution-input-diagnostic-v0.1-independent-verification-34069896968.json"
AUDIT_SHA = "9c4cf8536cb560e814c0c3a65e5ba5c4d4564596e88bc2dcc1517fbcc116fa26"
AUDIT_FILE_SHA = "4bbbc90dc68199c51afc18bede861a9c0fbb8c2c16c4d8d9c7d7f208a40af69a"
PROJECTION_SHA = "1ba1571113bee4577785dbd7c4b880cac6043c67eef03f0c9f26eae67f3802e4"
PROJECTION_CONTENT_SHA = "9f4fd81be871d19dc12ed28df03d0586d31a129a6c598e2ba50d1c4aad9ffa1c"
NORMALIZED_SHA = "d0d7742a17bf95201e157917f62e5f1a50372e3186ecda087b82891a4e9050c5"
RESULT_ZIP_SHA = "5626dd395c5bc4af329721d768bc1c1f2f8ad5fb02df7833aa5dc581c11fc3d7"
# Populated from the immutable parent at registration, never recomputed at runtime.
FROZEN_FILES = {'src/momentumbot/research/execution_realism.py': '446509405e3f44e3924c852569c5b06a096f61330552ede850a55c3da5794177', 'src/momentumbot/research/prospective_market_input_capture.py': '7b736e329a9d12eb2dfdeb09473fd04fc1caa0416eb1cb84ff2db7f4819ae9ee', 'src/momentumbot/research/prospective_market_input_acquisition.py': '5f1e354ae74512c03f78413b9e19b753ecc210083f41460468f124d1a23fcfae', 'src/momentumbot/research/sealed_historical_execution_inputs_v01.py': 'f100c220ed4fe5a6511d854599d8ed1494aaf554540a4fcabf6646f856b2a40f', 'research/strategy/prospective-management-execution-v0.1.json': '3760a73d4cc5d209098b75d555fb1f1a4ebcd7c0ecc428b1a16c39c2055008f8', 'research/strategy/prospective-market-input-capture-v0.1.json': 'b3bb179b0bc1032405be4db3ff7fe9499d42870d60d5cb372ba1f56aba8f711c', 'research/runtime/sealed-historical-execution-input-plan-v0.1/opportunity-manifest.json': 'e784f26b3e0fcabd465feb49f4fa7ca0f4444cff737f04d4e0455df64a03469c', 'research/runtime/sealed-historical-execution-input-plan-v0.1/request-manifest.json': 'ee0701cfbe81bfb546c1fb2d2573cf824b434d3a34ff6f1dffdd8cec5435a2e3', 'research/runtime/sealed-historical-execution-input-plan-v0.1/freeze-manifest.json': '867ffa66b94890ba06d73e0e70d82058793d8cea76eb3eef44bfb828fdd2df9a'}


def contract() -> dict:
    return seal({
        "schema_version": 1, "contract_id": adapter.CONTRACT_ID,
        "artifact_type": "offline_lossless_historical_record_order_registration",
        "parent_commit_sha": "726f00344ba061a1c6e71be64db7cd3b239eead0",
        "parent_tree_sha": "ddd901f72c45d5b48a0b1460469ee1e0ceb8c4c9",
        "diagnostic_run_id": 34069896968, "diagnostic_run_attempt": 1,
        "diagnostic_result_artifact_id": 10000122082,
        "diagnostic_result_zip_sha256": RESULT_ZIP_SHA,
        "diagnostic_audit_content_sha256": AUDIT_SHA,
        "diagnostic_audit_file_sha256": AUDIT_FILE_SHA,
        "diagnostic_projection_file_sha256": PROJECTION_SHA,
        "diagnostic_projection_content_sha256": PROJECTION_CONTENT_SHA,
        "diagnostic_normalized_content_sha256": NORMALIZED_SHA,
        "fixture_file_sha256": FIXTURE_SHA,
        "frozen_parent_file_sha256": FROZEN_FILES,
        "original_request_list_content_sha256": diagnostic.quote.REQUEST_LIST_SHA256,
        "frozen_date_count": 30, "frozen_opportunity_count": 109,
        "frozen_request_count": 90, "frozen_symbol_date_count": 45,
        "normalized_quote_fields": sorted(adapter.QUOTE_FIELDS),
        "additional_quote_fields": sorted(adapter.ORDER_FIELDS),
        "source_record_index": "zero_based_original_per_request_position_before_any_filtering",
        "native_key": ["ts_recv_ns", "sequence"],
        "native_key_requirement": "nondecreasing_in_original_record_order",
        "complete_tape_ordinals": "contiguous_from_zero",
        "window_ordinals": "original_strictly_increasing_ordinals_gaps_allowed_no_renumbering",
        "native_timestamp_and_sequence_rewriting": False,
        "sorting_or_deduplication": False,
        "equal_quote_status_receive_time": "unavailable_no_cross_schema_order_inferred",
        "unknown_status": "unchanged_fail_closed_window",
        "capture_mechanics": "frozen_loop_plus_two_provenance_fields_ast_equivalent",
        "execution_mechanics": "frozen_body_with_only_record_order_validator_replaced_ast_equivalent",
        "execution_policy_change": False, "status_vocabulary_change": False,
        "diagnostic_fixture_runtime_input_eligible": False,
        "provider_calls_authorized": 0, "acquisition_gate_passed": False,
        "historical_account_or_fill_simulation_authorized": False,
        "backtesting_authorized": False, "retrospective_access_authorized": False,
        "next_gate": "separately_registered_bounded_acquisition_child_then_independent_complete_input_verification",
    })


def _function(source: str, name: str) -> ast.FunctionDef:
    matches = [node for node in ast.parse(source).body
               if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError("mechanical function missing or repeated")
    return matches[0]


def validate_mechanical_equivalence(root: Path) -> None:
    source = (root / MODULE_PATH).read_text()
    old = _function((root / "src/momentumbot/research/execution_realism.py").read_text(),
                    "simulate_marketable_limit_order")
    new = _function(source, "simulate_record_order_limit_order")
    body = copy.deepcopy(new.body)
    call = body[1].value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "_validate_record_order_stream":
        raise ValueError("versioned execution validator differs")
    call.func.id = "_validate_quote_stream"
    if ast.dump(ast.Module(body=body, type_ignores=[])) != ast.dump(ast.Module(body=old.body, type_ignores=[])):
        raise ValueError("frozen execution mechanics changed beyond ordering validator")

    old = _function((root / "src/momentumbot/research/prospective_market_input_capture.py").read_text(),
                    "build_market_input_capture")
    old_loop = next(node for node in old.body if isinstance(node, ast.For)
                    and isinstance(node.target, ast.Name) and node.target.id == "opportunity")
    new = _function(source, "_capture_window")
    expected = ast.parse("opportunities = (opportunity,)\ncaptures = []\nfor opportunity in opportunities:\n    pass\nreturn captures[0]").body
    observed = copy.deepcopy(new.body)
    if len(observed) != 4 or not isinstance(observed[2], ast.For):
        raise ValueError("versioned capture wrapper changed")
    removed = []
    for node in ast.walk(observed[2]):
        if isinstance(node, ast.Dict):
            pairs = []
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in adapter.ORDER_FIELDS:
                    if not (isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name)
                            and value.value.id == "quote" and value.attr == key.value):
                        raise ValueError("quote provenance was not preserved directly")
                    removed.append(key.value)
                else:
                    pairs.append((key, value))
            node.keys, node.values = [p[0] for p in pairs], [p[1] for p in pairs]
    expected[2] = old_loop
    if sorted(removed) != sorted(adapter.ORDER_FIELDS) or ast.dump(ast.Module(body=observed, type_ignores=[])) != ast.dump(ast.Module(body=expected, type_ignores=[])):
        raise ValueError("frozen capture mechanics changed beyond provenance fields")


def validate_registration(root: Path) -> dict:
    diagnostic.validate_inputs(root)
    if file_sha(root / AUDIT_PATH) != AUDIT_FILE_SHA or frozen(root / AUDIT_PATH)["content_sha256"] != AUDIT_SHA:
        raise ValueError("independent diagnostic evidence differs")
    for path, expected in FROZEN_FILES.items():
        if file_sha(root / path) != expected:
            raise ValueError("immutable parent file differs: " + path)
    require_exact(frozen(root / CONTRACT_PATH), contract(), "record-order registration")
    validate_mechanical_equivalence(root)
    return seal({"contract_content_sha256": contract()["content_sha256"],
                 "verification_passed": True, "provider_calls": 0,
                 "acquisition_gate_passed": False})


def diagnostic_fixture(root: Path) -> tuple[list[dict], list[dict]]:
    """Verify all typed fields before extracting the frozen seven-field rows."""
    if file_sha(root / FIXTURE_PATH) != FIXTURE_SHA:
        raise ValueError("diagnostic regression fixture bytes differ")
    fixture = json.loads((root / FIXTURE_PATH).read_text())
    raw = base64.b64decode(fixture["gzip_base64"], validate=True)
    if hashlib.sha256(raw).hexdigest() != PROJECTION_SHA:
        raise ValueError("exact diagnostic gzip differs")
    projected = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    if canonical_fingerprint(projected) != PROJECTION_CONTENT_SHA or len(projected) != 1136:
        raise ValueError("diagnostic full normalized projection differs")
    mapping = {"symbol": "symbol", "ts_recv": "ts_recv_ns", "sequence": "sequence",
               "bid_px_00": "bid_px_nanos", "bid_sz_00": "bid_size",
               "ask_px_00": "ask_px_nanos", "ask_sz_00": "ask_size"}
    rows = []
    for index, row in enumerate(projected):
        if row["index"] != index or set(row["fields"]) != set(diagnostic.FIELDS):
            raise ValueError("diagnostic original row positions or fields differ")
        fields = row["fields"]
        for field, value in fields.items():
            kind = "text" if field in {"symbol", "action", "side"} else "integer"
            if value.get("kind") != kind or set(value) != {"kind", "value"}:
                raise ValueError("diagnostic typed scalar differs")
        rows.append({target: fields[source]["value"] for source, target in mapping.items()})
    if canonical_fingerprint(rows) != NORMALIZED_SHA:
        raise ValueError("unchanged seven-field normalization differs")
    return projected, rows


def verify_diagnostic_adapter(root: Path) -> dict:
    validate_registration(root)
    projected, rows = diagnostic_fixture(root)
    indexed = [dict(row, source_request_sha256=diagnostic.REQUEST_SHA, source_record_index=i)
               for i, row in enumerate(rows)]
    events = adapter.quote_events(indexed, diagnostic.request())
    restored = [{k: v for k, v in asdict(event).items() if k in adapter.QUOTE_FIELDS} for event in events]
    require_exact(restored, rows, "lossless native diagnostic rows")
    pairs = [(i-1, i) for i in range(1, len(events))
             if (events[i].ts_recv_ns, events[i].sequence) == (events[i-1].ts_recv_ns, events[i-1].sequence)]
    if len(pairs) != 175 or any(projected[a]["fields"]["action"]["value"] != "T"
                              or projected[b]["fields"]["action"]["value"] != "C"
                              or rows[a] == rows[b] for a, b in pairs):
        raise ValueError("complete distinct Trade/Cancel tie population differs")
    return seal({"schema_version": 1, "artifact_type": "offline_historical_record_order_regression",
        "contract_id": adapter.CONTRACT_ID, "contract_content_sha256": contract()["content_sha256"],
        "diagnostic_run_id": 34069896968, "diagnostic_result_artifact_id": 10000122082,
        "diagnostic_result_zip_sha256": RESULT_ZIP_SHA,
        "projection_file_sha256": PROJECTION_SHA, "projection_content_sha256": PROJECTION_CONTENT_SHA,
        "fixture_file_sha256": FIXTURE_SHA, "adapter_file_sha256": file_sha(root / MODULE_PATH),
        "normalized_native_content_sha256": canonical_fingerprint(restored),
        "record_ordered_content_sha256": canonical_fingerprint(indexed),
        "row_count": len(events), "distinct_trade_cancel_native_key_pairs": len(pairs),
        "native_fields_unchanged": True, "original_positions_preserved": True,
        "capture_mechanics_ast_equivalent": True, "execution_mechanics_ast_equivalent": True,
        "provider_calls": 0, "diagnostic_rows_used_for_capture_or_execution": False,
        "historical_account_or_fill_simulation_executed": False,
        "acquisition_gate_passed": False, "runtime_input_eligible": False,
        "backtesting_executed": False, "retrospective_inputs_loaded": False,
        "next_gate": contract()["next_gate"]})
