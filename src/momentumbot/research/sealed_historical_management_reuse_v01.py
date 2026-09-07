"""Verify exact retained management sources and derive only uncovered intervals.

This stage preserves source evidence and request coverage. It neither filters
execution-eligible prints nor projects exits or executes account sessions.
"""
from __future__ import annotations

from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import urlencode
import zipfile

import pandas as pd

from momentumbot.research import sealed_historical_account_inputs_v01 as accounts
from momentumbot.research import sealed_historical_micro_inputs_v01 as sip
from momentumbot.research import sealed_historical_micro_session_inputs_v02 as bars
from momentumbot.research.sealed_historical_execution_quote_v01 import (
    canonical_fingerprint, file_sha, frozen, require_exact, seal,
)

CONTRACT_ID = "sealed-historical-management-source-reuse-v0.1"
CONTRACT_PATH = f"research/strategy/{CONTRACT_ID}.json"
MISSING_ID = "sealed-historical-management-missing-inputs-v0.1"
MISSING_PATH = f"research/strategy/{MISSING_ID}.json"
OUTPUT_PATH = f"research/runtime/{CONTRACT_ID}"
MODULE_PATH = "src/momentumbot/research/sealed_historical_management_reuse_v01.py"
SCRIPT_PATH = "scripts/verify_sealed_historical_management_reuse_v01.py"
WORKFLOW_PATH = ".github/workflows/sealed-historical-management-reuse-v01.yml"
PARENT_COMMIT = "cf729c27d3e458e4762ee1d60d48a6c57a25a5d8"
PARENT_TREE = "c3ca04d647c9f6126dd4b88601c011f46cc6825d"
ACCOUNT_AUDIT = "research/data-audits/sealed-historical-account-management-inputs-v0.1-independent-verification.json"
AUDITS = {
    "sip_transactions": "research/data-audits/sealed-historical-micro-input-v0.1-independent-verification-34053730042.json",
    "raw_sip_1m_bars": "research/data-audits/sealed-historical-micro-session-input-v0.2-independent-verification-34054580516.json",
}
KINDS = {"sip_transactions": "sip_trades", "raw_sip_1m_bars": "session_1m_raw"}
FROZEN_FILES = {'.github/workflows/sealed-historical-account-inputs-v01.yml': '67b8d897d44e39e72dc1c588b4fabd66e0ffb25b401db678d7161b4b8f55f33b',
 'requirements-sealed-execution-quote-v01.txt': '03f4da335027e4c83bcf38e523c2e11aeaae49778f5bd6caa47e4703348b31b4',
 'research/data-audits/sealed-historical-account-management-inputs-v0.1-independent-verification.json': '6df3380245fee31519c1c5f2f8ac9201be7ab1e901f97500a43f422a1576dfe3',
 'research/data-audits/sealed-historical-execution-input-availability-v0.1-independent-verification.json': 'f5f1369adc03d908ca6fed0a934798f20829427277be0442ecc5f991371a0e34',
 'research/data-audits/sealed-historical-micro-input-v0.1-independent-verification-34053730042.json': '6002a536998d2ee3760df99137d199155be2133196cea1408be57e873792cf19',
 'research/data-audits/sealed-historical-micro-session-input-v0.2-independent-verification-34054580516.json': 'c62477e8047d3b2c28863f24a6e2e5ce977fd1a51685cf7e911bb59ce6799afd',
 'research/runtime/sealed-historical-account-management-inputs-v0.1/account-seeds.json': '2579ee6d763001e57494a6e6739b9c3142ba31fde77549b59a6907e05ef47ec1',
 'research/runtime/sealed-historical-account-management-inputs-v0.1/account-session-input-plan.json': '8ca638578e7957c88f4314e0768a3c379ee0bd1278bd6d8c8e9caa2144f05108',
 'research/runtime/sealed-historical-account-management-inputs-v0.1/freeze-manifest.json': 'eed7aa35e74e16e6904ad01fd3bb930792add7825133103a967e1568d7a5a54f',
 'research/runtime/sealed-historical-account-management-inputs-v0.1/management-request-manifest.json': 'd493f770de187454d08a631a3b183cbc616fa302fbac9bd51c67be8ed6316379',
 'research/runtime/sealed-historical-account-management-inputs-v0.1/readiness-report.json': 'c5876e9fa08e09cfb33e57e35938856a16e160bebf3f98fc6640a772875a50b3',
 'research/runtime/sealed-historical-execution-availability-v0.1/manifest.json': '6ed576e70dee9f439fdd2a1773f89931e6de23a73ea56e1ff1d9c81650bc8380',
 'research/strategy/paper-account-scarcity-policy-v0.1.json': '12c968d873cb459a9e65181b3bb2533b110006eddd9bf95b0def38a085c5a8fa',
 'research/strategy/prospective-management-execution-v0.1.json': '3760a73d4cc5d209098b75d555fb1f1a4ebcd7c0ecc428b1a16c39c2055008f8',
 'research/strategy/prospective-management-window-capture-v0.1.json': 'dd42ad3b7e826e8893f63809d6c9804ac0efbfae708992e5c5bd4c0220ee5ae7',
 'research/strategy/sealed-historical-account-management-inputs-v0.1.json': '222fcf457971657e3705a53dee6d8dcf8ede26770fa905cad4a101c39a2aca2b',
 'research/strategy/sealed-historical-execution-input-availability-v0.1.json': 'c7ab0f91782b11b7944946e3edea3d105e44b757058929a7f2e5cb3c12159f31',
 'research/strategy/sealed-historical-walk-forward-v0.1.json': '063df5e36210386a7c25890963ace5a7b2a70fdafb07f9103c5d402c69b195e2',
 'scripts/build_sealed_historical_account_inputs_v01.py': '307cabdde121cc56d61fa4486194791e6ed50482789bb4d51cb371cfc3ea0a90',
 'scripts/run_offline_python_v13.py': 'fd28ca7e4a27832721a890a1a41af36863a7f13568ca9e85e17c2d5f35e0627d',
 'src/momentumbot/micro_execution.py': '234836c30b51fb8789aae345f159cfe2226b2d7bdbd6a2254380ca14eda4c266',
 'src/momentumbot/models.py': 'efa4857a1fa92d24896b750b7df4846abd952fafd966f046054e0aad21325a82',
 'src/momentumbot/providers/alpaca_trades.py': 'ad5a8a944722b123bfa087d28e96b3de73054419afc184df5c1734663786f432',
 'src/momentumbot/research/account_priority_policy.py': '3c0254bcd06425670e7158fb6c2be44edaa6c6f4b74c045798148f9d43e250d7',
 'src/momentumbot/research/campaign_portfolio.py': '5e8b5fb8e42cc739b8337bb544b811e57ccda2df5e7f46ca65ef5a30472149c4',
 'src/momentumbot/research/prospective_account_evaluation.py': '56ccebf7725ef04a797e4b5dead0ecd091ef9e9866290bf6e67b90283a9dd3bd',
 'src/momentumbot/research/prospective_management_window.py': 'bc431e578c7c85e1c72c72eda60ff212cf128cd5fd52cae3dcbed1bcc36523e8',
 'src/momentumbot/research/sealed_historical_account_inputs_v01.py': 'b7a28487807dd5d841a205d6ab74429fb3ed5f0f74b345712c57579e360228dd',
 'src/momentumbot/research/sealed_historical_execution_availability_v01.py': 'ef541e915e75c10641c57e42cd4a62fbb66b472c6b40a02d4c2ad85d6dbedb37',
 'src/momentumbot/research/sealed_historical_execution_inputs_v01.py': 'f100c220ed4fe5a6511d854599d8ed1494aaf554540a4fcabf6646f856b2a40f',
 'src/momentumbot/research/sealed_historical_execution_quote_v01.py': 'be5d81c039ba0256b2622ea65d2f966f56fa2f9a87b77f2e39485d92c6464383',
 'src/momentumbot/research/sealed_historical_micro_inputs_v01.py': 'b6f5029fe7ae33a34d38df1fa4f6797cdab4a3b6f4ca5cc9aa98e234914b75b5',
 'src/momentumbot/research/sealed_historical_micro_session_inputs_v02.py': 'c3d5d5f1e9ff988f914dcd6b4d5f4b647dd5f838a8cb39ea4a59eb4bd139ec13',
 'src/momentumbot/research/sealed_historical_record_order_v01.py': '407e02fc6fe908e26715fac2799f0debf356e96336b640e795b50287762dec6b',
 'src/momentumbot/research/trade_management_shadow.py': '9309593b839a4260bd6ef8d34d1eec5c905128dcf502218032cb7c0f142af180'}
BOUNDARY = dict(accounts.BOUNDARY)
NEXT_GATE = "implement_and_validate_separately_consumed_capture_for_exact_10_missing_management_resources"
STAMP = re.compile(br'"t":"([^"\\]+)"')


def _json(raw: bytes) -> dict:
    def pairs(items):
        value = {}
        for key, child in items:
            if key in value:
                raise ValueError("duplicate source JSON key")
            value[key] = child
        return value
    value = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("source object required")
    return value


def _sealed(raw: bytes) -> dict:
    value = _json(raw)
    require_exact(value, seal({k: v for k, v in value.items() if k != "content_sha256"}), "source content seal")
    return value


def _canonical_line(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def partition_interval(start: int, end: int, covered: list[tuple[int, int]]) -> tuple[list[list[int]], list[list[int]]]:
    """Intersect, union, and complement half-open intervals using exact integers."""
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise ValueError("positive exact half-open interval required")
    merged: list[list[int]] = []
    for lower, upper in sorted(covered):
        if type(lower) is not int or type(upper) is not int or lower < 0 or upper <= lower:
            raise ValueError("invalid source interval")
        lower, upper = max(start, lower), min(end, upper)
        if lower >= upper:
            continue
        if merged and lower <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], upper)
        else:
            merged.append([lower, upper])
    gaps, cursor = [], start
    for lower, upper in merged:
        if cursor < lower:
            gaps.append([cursor, lower])
        cursor = upper
    if cursor < end:
        gaps.append([cursor, end])
    return merged, gaps


def source_requests(root: Path) -> dict[str, list[dict]]:
    plan = root / sip.PLAN_RELATIVE
    return {"sip_transactions": sip.derive_requests(plan), "raw_sip_1m_bars": bars.derive_requests(plan)}


def derive_coverage(root: Path) -> tuple[list[dict], list[dict]]:
    manifest = frozen(root / accounts.OUTPUT_PATH / "management-request-manifest.json")
    resources, missing = [], []
    sources = source_requests(root)
    for request in manifest["requests"]:
        for resource in ("raw_sip_1m_bars", "sip_transactions"):
            matches = [s for s in sources[resource] if s["kind"] == KINDS[resource]
                       and (s["trading_date"], s["symbol"]) == (request["trading_date"], request["symbol"])]
            if len(matches) != 1:
                raise ValueError("exact retained source identity required")
            source = matches[0]
            interval = (int(pd.Timestamp(source["start_inclusive"]).value), int(pd.Timestamp(source["end_exclusive"]).value))
            covered, gaps = partition_interval(request["start_ns"], request["end_ns"], [interval])
            coverage_id = request["request_id"] + ":" + resource
            resources.append({"coverage_id": coverage_id, "management_request_id": request["request_id"],
                "resource": resource, "trading_date": request["trading_date"], "symbol": request["symbol"],
                "required_start_ns": request["start_ns"], "required_end_ns": request["end_ns"],
                "source_request_id": source["request_id"], "covered_intervals": covered, "missing_intervals": gaps,
                "coverage_status": "full_request_envelope" if not gaps else "partial_request_envelope",
                "opportunity_ids": request["opportunity_ids"]})
            for lower, upper in gaps:
                body = {"coverage_id": coverage_id, "management_request_id": request["request_id"],
                    "resource": resource, "kind": KINDS[resource], "trading_date": request["trading_date"],
                    "symbol": request["symbol"], "asof": request["trading_date"], "feed": "sip",
                    "adjustment": "raw" if resource == "raw_sip_1m_bars" else None,
                    "start_ns": lower, "end_ns": upper, "end_exclusive": True,
                    "opportunity_ids": request["opportunity_ids"]}
                missing.append({**body, "request_id": canonical_fingerprint(body)})
    return resources, missing


def contract(root: Path) -> dict:
    return seal({"schema_version": 1, "contract_id": CONTRACT_ID,
        "artifact_type": "registered_provider_free_management_source_reuse_verification",
        "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "frozen_parent_file_sha256": FROZEN_FILES,
        "hypothesis": "exact_retained_sources_supply_covered_management_intervals_without_source_or_policy_changes",
        "source_audits": {key: frozen(root / path)["content_sha256"] for key, path in AUDITS.items()},
        "normalization": "unchanged_micro_input_normalized_row_for_every_selected_source_record",
        "coverage_basis": "complete_exhausted_request_envelopes_never_first_or_last_observed_record",
        "order": "zero_based_original_source_record_ordinal_no_sort_or_deduplication",
        "selected_row_commitment": "sha256_of_decimal_source_ordinal_colon_exact_canonical_jsonl_bytes_in_original_order",
        "whole_archive_verification": "exact_zip_all_members_all_receipts_all_uncompressed_tape_hashes_and_row_counts",
        "irrelevant_rows": "not_exposed_to_management_runtime_prior_verified_normalization_bound_by_exact_bytes",
        "partial_windows": "retain_reusable_prefix_and_exact_uncovered_tail_without_imputing_missing_records",
        "management_trade_eligibility_filter_applied": False,
        "retrospective_labels_or_transcripts_allowed": False,
        "next_gate": NEXT_GATE, **BOUNDARY})


def missing_contract(root: Path) -> dict:
    _, requests = derive_coverage(root)
    return seal({"schema_version": 1, "contract_id": MISSING_ID,
        "artifact_type": "unarmed_exact_missing_management_capture_requirements",
        "parent_account_input_commit_sha": PARENT_COMMIT,
        "reuse_contract_content_sha256": contract(root)["content_sha256"],
        "requests": requests, "request_manifest_sha256": canonical_fingerprint(requests),
        "logical_request_count": len(requests), "merged_window_count": len({r["management_request_id"] for r in requests}),
        "maximum_http_attempts": 512, "maximum_normalized_compressed_bytes": 100_000_000,
        "page_limit": 10_000, "maximum_response_bytes": 16_000_000,
        "minimum_request_interval_seconds": 0.35,
        "incremental_provider_cost_usd": "0", "provider": "existing_alpaca_market_data_subscription",
        "allowed_host": "data.alpaca.markets", "allowed_method": "GET",
        "allowed_paths": ["/v2/stocks/bars", "/v2/stocks/trades"],
        "wire_end": "exact_exclusive_end_minus_one_nanosecond", "pagination": "ascending_exhaust_each_exact_request",
        "automatic_retries_allowed": False, "redirects_allowed": False,
        "empty_exhausted_segment": "retain_zero_record_receipt_as_source_evidence_never_infer_a_trade_or_exit_outcome",
        "execution_child_required": True, "tested_capture_implementation_required": True,
        "verified_reuse_result_required": True, "durable_consumption_before_provider_access_required": True,
        "separate_ledger_required": True, "failed_partial_evidence_retained": True,
        "workflow_reruns_allowed": False, "existing_captures_may_be_modified": False,
        "provider_access_authorized_by_this_registration": False, **BOUNDARY})


def validate_registration(root: Path) -> dict:
    for name, expected in FROZEN_FILES.items():
        accounts.availability._regular(root / name)
        if file_sha(root / name) != expected:
            raise ValueError("frozen management reuse parent differs: " + name)
    accounts.verify_bundle(root, root / accounts.OUTPUT_PATH)
    require_exact(frozen(root / CONTRACT_PATH), contract(root), "management reuse registration")
    require_exact(frozen(root / MISSING_PATH), missing_contract(root), "exact missing capture registration")
    return seal({"verification_passed": True, "contract_content_sha256": contract(root)["content_sha256"], **BOUNDARY})


def missing_request_url(root: Path, request_id: str, page_token: str | None = None) -> str:
    """Render a registered URL for review; there is no provider transport here."""
    validate_registration(root)
    matches = [r for r in missing_contract(root)["requests"] if r["request_id"] == request_id]
    if len(matches) != 1:
        raise ValueError("unregistered missing request")
    if page_token is not None and (not isinstance(page_token, str) or not page_token):
        raise ValueError("invalid opaque page token")
    r = matches[0]
    query = {"symbols": r["symbol"], "start": pd.Timestamp(r["start_ns"], unit="ns", tz="UTC").isoformat(),
        "end": pd.Timestamp(r["end_ns"] - 1, unit="ns", tz="UTC").isoformat(),
        "feed": r["feed"], "asof": r["asof"], "sort": "asc", "limit": 10_000}
    path = "/v2/stocks/trades"
    if r["kind"] == "session_1m_raw":
        path = "/v2/stocks/bars"
        query.update(timeframe="1Min", adjustment="raw")
    if page_token is not None:
        query["page_token"] = page_token
    return "https://data.alpaca.markets" + path + "?" + urlencode(query)


def source_spec(root: Path, resource: str) -> dict:
    audit = frozen(root / AUDITS[resource])
    prefix = "capture_" if resource == "sip_transactions" else ""
    return {"artifact_id": audit["capture_artifact_id"], "run_id": audit["run_id"],
        "zip_sha256": audit["capture_zip_sha256"], "file_count": audit["verified_file_count"],
        "report_file_sha256": audit[prefix + "report_file_sha256"],
        "inventory_file_sha256": audit[prefix + "inventory_file_sha256"],
        "provider_attempts": audit["provider_attempts"], "record_count": audit["normalized_row_count"],
        "prior_audit_content_sha256": audit["content_sha256"]}


def _safe_members(archive: zipfile.ZipFile, expected_count: int) -> list[str]:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != expected_count or len(names) != len(set(names)):
        raise ValueError("source ZIP member population differs")
    for info in infos:
        path = PurePosixPath(info.filename)
        mode = info.external_attr >> 16
        if (path.is_absolute() or ".." in path.parts or "\\" in info.filename or path.as_posix() != info.filename
                or info.is_dir() or stat.S_ISLNK(mode) or info.flag_bits & 1):
            raise ValueError("unsafe source ZIP member")
    return names


def _scan_tape(archive: zipfile.ZipFile, request: dict, receipt: dict, selectors: list[dict]) -> tuple[dict, list[dict]]:
    """Recheck complete logical tape bytes; normalize only required source rows."""
    logical, count, last_byte = hashlib.sha256(), 0, b""
    selected = {s["coverage_id"]: {"digest": hashlib.sha256(), "count": 0, "first": None, "last": None} for s in selectors}
    with archive.open(receipt["path"]) as member, gzip.GzipFile(fileobj=member) as tape:
        if not selectors:
            for block in iter(lambda: tape.read(1024 * 1024), b""):
                logical.update(block); count += block.count(b"\n"); last_byte = block[-1:]
        else:
            previous = None
            for ordinal, raw in enumerate(tape):
                logical.update(raw); count += 1; last_byte = raw[-1:]
                match = STAMP.search(raw)
                if match is None:
                    raise ValueError("source row timestamp missing")
                timestamp = pd.Timestamp(match.group(1).decode())
                if pd.isna(timestamp) or timestamp.tzinfo is None:
                    raise ValueError("invalid source timestamp")
                ts = int(timestamp.value)
                if previous is not None and ts < previous:
                    raise ValueError("source tape order differs")
                previous = ts
                matches = [s for s in selectors if any(lower <= ts < upper for lower, upper in s["covered_intervals"])]
                if not matches:
                    continue
                row = _json(raw)
                normalized = sip.normalized_row(row, request)
                if _canonical_line(normalized) != raw:
                    raise ValueError("retained row normalization changed")
                for selector in matches:
                    item = selected[selector["coverage_id"]]
                    item["digest"].update(str(ordinal).encode() + b":" + raw)
                    item["count"] += 1
                    if item["first"] is None:
                        item["first"] = ordinal
                    item["last"] = ordinal
    if (last_byte != b"\n" or count != receipt["record_count"] or logical.hexdigest() != receipt["logical_sha256"]):
        raise ValueError("source logical tape hash or count differs")
    selections = [{"coverage_id": key, "selected_record_count": item["count"],
        "selected_records_sha256": item["digest"].hexdigest(),
        "first_source_record_ordinal": item["first"], "last_source_record_ordinal": item["last"],
        "source_request_id": request["request_id"], "source_tape_file_sha256": receipt["file_sha256"],
        "source_tape_logical_sha256": receipt["logical_sha256"], "source_tape_record_count": count,
        "normalization_verified": True, "management_trade_eligibility_filter_applied": False} for key, item in selected.items()]
    return {"request_id": request["request_id"], "record_count": count, "logical_sha256": logical.hexdigest()}, selections


def _verify_archive(path: Path, spec: dict, expected_requests: list[dict], selectors: list[dict], progress=None) -> tuple[dict, list[dict]]:
    accounts.availability._regular(path)
    if file_sha(path) != spec["zip_sha256"]:
        raise ValueError("exact retained source ZIP differs")
    selections, tape_proofs = [], []
    with zipfile.ZipFile(path) as archive:
        names = _safe_members(archive, spec["file_count"])
        inventory = _sealed(archive.read("capture-inventory.json"))
        report = _sealed(archive.read("capture-report.json"))
        actual = {}
        for name in names:
            digest = hashlib.sha256()
            with archive.open(name) as member:
                for block in iter(lambda: member.read(1024 * 1024), b""):
                    digest.update(block)
            actual[name] = digest.hexdigest()
        if actual["capture-inventory.json"] != spec["inventory_file_sha256"] or actual["capture-report.json"] != spec["report_file_sha256"]:
            raise ValueError("retained source metadata differs")
        require_exact(inventory["files"], {k: v for k, v in actual.items() if k != "capture-inventory.json"}, "all source member bytes")
        require_exact(_sealed(archive.read("requests.json"))["requests"], expected_requests, "original source requests")
        ledger = _json(archive.read("request-ledger.json"))
        if (inventory["complete"] is not True or report["status"] != "complete"
                or report["logical_requests_completed"] != len(expected_requests)
                or len(report["receipts"]) != len(expected_requests)
                or inventory["provider_attempts"] != spec["provider_attempts"]
                or ledger["total_attempts"] != spec["provider_attempts"]
                or inventory["blocked_attempts"] != 0 or ledger["blocked_attempts"] != 0):
            raise ValueError("retained source completeness or ledger differs")
        receipt_index = {r["request_id"]: r for r in report["receipts"]}
        if set(receipt_index) != {r["request_id"] for r in expected_requests}:
            raise ValueError("receipt request identities differ")
        selectors_by_source = defaultdict(list)
        for selector in selectors:
            selectors_by_source[selector["source_request_id"]].append(selector)
        for i, request in enumerate(expected_requests, 1):
            receipt = receipt_index[request["request_id"]]
            require_exact(_sealed(archive.read("receipts/" + request["request_id"] + ".json")), seal(receipt), "individual source receipt")
            expected_path = f"dates/{request['trading_date']}/{request['symbol']}-{request['kind']}.jsonl.gz"
            if (receipt["path"] != expected_path or receipt["complete"] is not True
                    or receipt["file_sha256"] != actual[expected_path]
                    or receipt["retained_bytes"] != archive.getinfo(expected_path).file_size
                    or type(receipt["pages"]) is not int or receipt["pages"] < 1):
                raise ValueError("source receipt differs")
            proof, picked = _scan_tape(archive, request, receipt, selectors_by_source[request["request_id"]])
            tape_proofs.append(proof); selections.extend(picked)
            if progress is not None and (i % 20 == 0 or i == len(expected_requests)):
                progress({"artifact_id": spec["artifact_id"], "verified_tapes": i, "total_tapes": len(expected_requests)})
        if sum(p["record_count"] for p in tape_proofs) != spec["record_count"]:
            raise ValueError("total source record count differs")
    return seal({"verification_passed": True, **spec, "verified_file_count": len(names),
        "verified_tape_count": len(tape_proofs), "verified_receipt_count": len(tape_proofs),
        "member_file_inventory_sha256": canonical_fingerprint(actual), "tape_proofs": tape_proofs,
        "selected_records_normalized_again": sum(s["selected_record_count"] for s in selections),
        "unselected_normalization_bound_by_exact_prior_verified_bytes": True}), selections


def build_bundle(root: Path, sip_zip: Path, bars_zip: Path, progress=None) -> dict[str, bytes]:
    validate_registration(root)
    resources, missing = derive_coverage(root)
    requests = source_requests(root)
    source_proofs, selections = {}, []
    for resource, path in (("sip_transactions", sip_zip), ("raw_sip_1m_bars", bars_zip)):
        proof, picked = _verify_archive(path, source_spec(root, resource), requests[resource],
            [r for r in resources if r["resource"] == resource], progress)
        source_proofs[resource] = proof; selections.extend(picked)
    index = {s["coverage_id"]: s for s in selections}
    if len(index) != len(resources) or set(index) != {r["coverage_id"] for r in resources}:
        raise ValueError("incomplete reuse selection evidence")
    coverage = [{**r, "selection_evidence": index[r["coverage_id"]]} for r in resources]
    management = frozen(root / accounts.OUTPUT_PATH / "management-request-manifest.json")
    unavailable = frozen(root / accounts.OUTPUT_PATH / "readiness-report.json")["unavailable_opportunities"]
    partial_ids = {r["management_request_id"] for r in resources if r["missing_intervals"]}
    payloads = {
        "source-verification.json": seal({"contract_id": CONTRACT_ID, "sources": source_proofs, **BOUNDARY}),
        "reuse-coverage.json": seal({"contract_id": CONTRACT_ID, "resources": coverage,
            "management_request_manifest_content_sha256": management["content_sha256"],
            "request_envelopes_verified": True, "runtime_readiness_inferred_from_record_count": False, **BOUNDARY}),
        "missing-input-requests.json": missing_contract(root),
        "readiness-report.json": seal({"contract_id": CONTRACT_ID, "source_reuse_verification_passed": True,
            "merged_window_count": len(management["requests"]), "full_envelope_window_count": len(management["requests"]) - len(partial_ids),
            "partial_envelope_window_count": len(partial_ids), "logical_resource_count": len(resources),
            "fully_covered_resource_count": sum(not r["missing_intervals"] for r in resources),
            "partially_covered_resource_count": sum(bool(r["missing_intervals"]) for r in resources),
            "missing_logical_request_count": len(missing), "unavailable_entry_opportunities": unavailable,
            "selected_record_counts": {key: value["selected_records_normalized_again"] for key, value in source_proofs.items()},
            "all_management_sources_complete": not missing, "missing_capture_executed": False,
            "next_gate": NEXT_GATE, **BOUNDARY}),
    }
    files = {name: accounts._bytes(payload) for name, payload in payloads.items()}
    manifest = seal({"contract_id": CONTRACT_ID, "parent_commit_sha": PARENT_COMMIT, "parent_tree_sha": PARENT_TREE,
        "contract_content_sha256": contract(root)["content_sha256"],
        "implementation_file_sha256": {name: file_sha(root / name) for name in (MODULE_PATH, SCRIPT_PATH, WORKFLOW_PATH, CONTRACT_PATH, MISSING_PATH)},
        "file_inventory": {name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in files.items()},
        "document_content_sha256": {name: payload["content_sha256"] for name, payload in payloads.items()},
        "next_gate": NEXT_GATE, **BOUNDARY})
    files["freeze-manifest.json"] = accounts._bytes(manifest)
    return files


def verify_bundle(root: Path, output: Path, *, sip_zip: Path, bars_zip: Path, progress=None) -> dict:
    _output(root, output)
    expected = build_bundle(root, sip_zip, bars_zip, progress)
    actual = accounts.availability._inventory(output)
    if set(actual) != set(expected):
        raise ValueError("reuse output population differs")
    for name, raw in expected.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("reuse output differs from source reconstruction: " + name)
    return seal({"verification_passed": True, "file_inventory": actual,
        "freeze_manifest_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"],
        "readiness": frozen(output / "readiness-report.json"), **BOUNDARY})


def _output(root: Path, output: Path) -> None:
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("symlink output rejected")
    if output.resolve().is_relative_to(root.resolve()) and output.resolve() != (root / OUTPUT_PATH).resolve():
        raise ValueError("cannot overwrite frozen repository inputs")


def write_bundle(root: Path, output: Path, *, sip_zip: Path, bars_zip: Path, progress=None) -> dict:
    _output(root, output)
    if output.exists():
        raise FileExistsError("reuse result is write-once")
    files = build_bundle(root, sip_zip, bars_zip, progress)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (output / name).open("xb") as handle:
            handle.write(raw)
    actual = accounts.availability._inventory(output)
    require_exact(actual, {name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in files.items()}, "written reuse bytes")
    return seal({"verification_passed": True, "file_inventory": actual,
        "freeze_manifest_content_sha256": frozen(output / "freeze-manifest.json")["content_sha256"],
        "readiness": frozen(output / "readiness-report.json"), **BOUNDARY})
