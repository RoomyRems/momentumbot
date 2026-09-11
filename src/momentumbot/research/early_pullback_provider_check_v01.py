"""Exact four-call availability provenance; no strategy or historical replay.

An unarmed registration becomes executable only in a sole-file child of the
tested code commit. The hosted workflow consumes a permanent ref before any
provider credentials are injected. Response bodies are hashed, never retained.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile
from zoneinfo import ZoneInfo

from momentumbot.research import early_pullback_panel_accounts_v01 as parent

ID = "early-pullback-provider-check-v0.1"
PARENT = "0b13bc2af53f0b40b8e9128587abc78a89d48de1"
PARENT_TREE = "049b6394ab0a897190bb4a3251c8e527052bdaf7"
PARENT_SHA = "54aacb047f96a67ec329ea3cee988595bfd447d11064ecc4d63750dc265e6b06"
PREPARATION_SHA = "dec8f9cc56a491df556bc7e2b5af36ff21fea0a796359cd2a18dca0cd7213aff"
CONTRACT_PATH = f"research/strategy/{ID}.json"
EXECUTION_PATH = f"research/strategy/{ID}-execution.json"
BASE = f"research/data-audits/{ID}"
WORKFLOW_PATH = ".github/workflows/early-pullback-provider-check-v01.yml"
CONSUMPTION_REF = f"refs/tags/{ID}-consumed"
MODULE_PATH = "src/momentumbot/research/early_pullback_provider_check_v01.py"
TRANSPORT_PATH = "src/momentumbot/research/early_pullback_provider_transport_v01.py"
SCRIPT_PATH = "scripts/check_early_pullback_providers_v01.py"
TEST_PATH = "tests/test_early_pullback_provider_check_v01.py"
REQUIREMENTS_PATH = "requirements-sealed-source-v04.txt"
OWN_FILES = (MODULE_PATH, TRANSPORT_PATH, SCRIPT_PATH, TEST_PATH, WORKFLOW_PATH,
             REQUIREMENTS_PATH, "scripts/run_offline_python_v13.py")
DATES = tuple(parent.sources.DATES)
NY = ZoneInfo("America/New_York")
MAX_RESPONSE_BYTES = 262_144
MAX_ARCHIVE_BYTES = 2_000_000
SCHEMAS = ("mbp-1", "status")
ROUTES = {"alpaca": "https://data.alpaca.markets/v2/stocks/bars",
          "massive": "https://api.massive.com/v3/reference/tickers",
          "polygon": "https://api.polygon.io/v3/reference/tickers",
          "databento": "https://hist.databento.com/v0/metadata.get_dataset_range"}
BOUNDARY = {"full_session_calendar_authenticated": False,
    "point_in_time_universe_complete": False, "historical_market_inputs_authenticated": False,
    "historical_replay_enabled": False, "financial_evaluation_enabled": False,
    "paid_capture_enabled": False, "brokerage_orders_enabled": False,
    "discretionary_strategy_integrated": False, "policy_promotion_eligible": False,
    "transcript_records_read": False, "raw_response_bodies_retained": False,
    "actual_incremental_cost_known": False}
require, seal, fingerprint = parent.require, parent.seal, parent.fingerprint
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def exact(value, expected, label):
    require(type(value) is type(expected) and fingerprint(value) == fingerprint(expected), label)


def json_object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("non-finite JSON value")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    require(type(value) is dict, "JSON object required")
    return value


def frozen(path):
    value = json_object(Path(path).read_bytes())
    verify_seal(value)
    return value


def verify_seal(value):
    require(type(value) is dict and "content_sha256" in value, "sealed object required")
    body = {k: v for k, v in value.items() if k != "content_sha256"}
    require(value["content_sha256"] == fingerprint(body), "content seal differs")


def write_once(path, value):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), "no symbolic links")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def registration(root):
    inherited = parent.validate_registration(root)
    require(inherited["content_sha256"] == PARENT_SHA, "account checkpoint differs")
    prep = parent.provider_check_preparation(root)
    require(prep["content_sha256"] == PREPARATION_SHA, "four-call preparation differs")
    files = set(inherited["file_bindings"]) | set(OWN_FILES) | {
        parent.CONTRACT_PATH, parent.BASE + "/provider-check-preparation.json"}
    for name in files:
        path = root / name
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
                "regular bound file required")
    return seal({"contract_id": ID, "artifact_type": "unarmed_exact_provider_transport_registration",
        "parent_commit": PARENT, "parent_tree": PARENT_TREE, "parent_registration_sha256": PARENT_SHA,
        "preparation_sha256": PREPARATION_SHA, "requests": prep["requests"],
        "request_manifest_sha256": fingerprint(prep["requests"]), "selected_dates": list(DATES),
        "file_bindings": {p: {"bytes": (root / p).stat().st_size, "sha256": sha((root / p).read_bytes())}
                          for p in sorted(files)},
        "routes": ROUTES, "method": "GET", "maximum_provider_attempts": 4,
        "maximum_response_bytes": MAX_RESPONSE_BYTES, "oversize_detection_extra_byte": 1,
        "timeout_seconds": 20, "automatic_retries": False, "redirects": False,
        "pagination": False, "runtime_endpoint_fallback": False,
        "credential_route": "validated ALPACA_MAIN aliases; Massive key else Polygon key chosen before transport; Databento Basic authentication",
        "durable_consumption_ref": CONSUMPTION_REF, "tested_code_execution_child_required": True,
        "authorized_calls_now": 0, "incremental_spend_authorized_usd": "0.00",
        "projection": "counts, dates, booleans and fixed status enums only; response byte hashes bind transport but cannot reproduce discarded raw bodies",
        "hypothesis": "the fixed four requests provide limited endpoint and schema-range coverage evidence without changing dates or opening strategy outcomes",
        "next_gate": "independent full-session confirmation and exhaustive causal source graph; quote exact paid requests before capture",
        **BOUNDARY})


def validate_registration(root):
    saved = frozen(root / CONTRACT_PATH)
    exact(saved, registration(root), "provider transport registration differs")
    return saved


def hash_value(value, length=64):
    require(type(value) is str and re.fullmatch(rf"[0-9a-f]{{{length}}}", value), "full hash required")
    return value


def execution_payload(contract, *, code_commit, code_tree, ci_run_id):
    hash_value(code_commit, 40)
    hash_value(code_tree, 40)
    require(type(ci_run_id) is str and re.fullmatch(r"[1-9][0-9]*", ci_run_id), "CI run identity required")
    return seal({"contract_id": ID, "artifact_type": "sole_file_bounded_probe_execution",
        "contract_sha256": contract["content_sha256"], "request_manifest_sha256": contract["request_manifest_sha256"],
        "code_commit_sha": code_commit, "code_tree_sha": code_tree, "successful_code_ci_run_id": ci_run_id,
        "workflow_sha256": contract["file_bindings"][WORKFLOW_PATH]["sha256"],
        "consumption_ref": CONSUMPTION_REF, "maximum_provider_attempts": 4,
        "authority": "user authorized proceeding with provider provenance and bounded capture after account checkpoint",
        "availability_probe_authorized": True, "incremental_spend_authorized_usd": "0.00",
        **BOUNDARY})


def validate_execution(execution, contract, env, checkout):
    expected = execution_payload(contract, code_commit=checkout["parent_commit"],
        code_tree=checkout["parent_tree"], ci_run_id=execution.get("successful_code_ci_run_id"))
    exact(execution, expected, "exact tested execution parent required")
    exact(checkout["changed_files"], ["A\t" + EXECUTION_PATH], "execution child must add only its authorization")
    exact(checkout["parents"], [checkout["parent_commit"]], "one parent required")
    require(checkout["head"] == env.get("GITHUB_SHA") and checkout["clean"] is True,
            "clean exact execution checkout required")
    hash_value(checkout["head"], 40)
    require(env.get("GITHUB_REPOSITORY") == "RoomyRems/momentumbot"
        and env.get("GITHUB_EVENT_NAME") == "push"
        and env.get("GITHUB_REF") == "refs/heads/phase-3-historical-snapshot"
        and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")), "first-attempt research push required")
    return execution


def validate_ci(receipt, execution):
    require(type(receipt) is dict and str(receipt.get("id")) == execution["successful_code_ci_run_id"]
        and receipt.get("head_sha") == execution["code_commit_sha"]
        and receipt.get("path") == ".github/workflows/ci.yml" and receipt.get("event") == "push"
        and receipt.get("status") == "completed" and receipt.get("conclusion") == "success"
        and receipt.get("repository", {}).get("full_name") == "RoomyRems/momentumbot",
        "successful exact-parent CI receipt required")


def consumption(execution, env):
    hash_value(env["GITHUB_SHA"], 40)
    require(env.get("GITHUB_RUN_ATTEMPT") == "1" and
            re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")), "first consumption attempt required")
    return seal({"contract_id": ID, "execution_sha256": execution["content_sha256"],
        "consumption_ref": CONSUMPTION_REF, "execution_commit_sha": env["GITHUB_SHA"],
        "workflow_run_id": env["GITHUB_RUN_ID"], "workflow_run_attempt": 1})


def stamp(value, *, metadata=False):
    require(type(value) is str and len(value) <= 40, "ISO timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if metadata and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    require(parsed.tzinfo is not None, "aware timestamp required")
    return parsed.astimezone(timezone.utc)


def range_projection(value):
    if type(value) is not dict or not {"start", "end"} <= set(value):
        return {"range_start": None, "range_end": None, "covers_selected_interval": False}
    start, end = stamp(value["start"], metadata=True), stamp(value["end"], metadata=True)
    require(start < end, "forward metadata interval required")
    first = stamp(DATES[0], metadata=True)
    after_last = stamp(DATES[-1], metadata=True) + timedelta(days=1)
    return {"range_start": start.isoformat(), "range_end": end.isoformat(),
            "covers_selected_interval": start <= first and end >= after_last}


def project(ordinal, payload):
    """Whitelisted summaries; no provider strings other than parsed dates survive."""
    require(type(payload) is dict, "provider object required")
    if ordinal == 0:
        bars = payload.get("bars")
        require(type(bars) is dict and set(bars) == {"SPY"}, "single requested series required")
        rows = bars["SPY"]
        require(type(rows) is list and len(rows) <= 1000, "bounded daily response required")
        dates = []
        for row in rows:
            require(type(row) is dict, "daily row required")
            at = stamp(row.get("t"))
            require(stamp("2026-03-03T00:00:00Z") <= at < stamp("2026-05-21T00:00:00Z"), "bar outside request")
            local = at.astimezone(NY)
            require((local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0), "daily opening timestamp required")
            dates.append(local.date().isoformat())
        require(dates == sorted(set(dates)), "daily rows must be unique and ordered")
        token = payload.get("next_page_token")
        require(token is None or type(token) is str, "invalid pagination status")
        observed = sorted(set(dates) & set(DATES))
        missing = sorted(set(DATES) - set(dates))
        return {"ok": not missing and not bool(token), "row_count": len(rows),
                "observed_selected_dates": observed, "missing_selected_dates": missing,
                "next_page_present": bool(token)}
    if ordinal in (1, 2):
        rows = payload.get("results")
        require(type(rows) is list and len(rows) <= 1, "one membership sample only")
        valid = len(rows) == 1 and type(rows[0]) is dict
        row = rows[0] if valid else {}
        fields = ("ticker", "primary_exchange", "type")
        matches = valid and row.get("active") is True and row.get("market") == "stocks" and row.get("locale") == "us"
        fields_present = valid and all(type(row.get(k)) is str and bool(row[k]) for k in fields)
        count_matches = type(payload.get("count")) is int and payload["count"] == len(rows)
        page = payload.get("next_url")
        require(page is None or type(page) is str, "invalid membership pagination status")
        return {"ok": bool(matches and fields_present and count_matches and page and payload.get("status") == "OK"),
                "requested_date": DATES[0] if ordinal == 1 else DATES[-1], "row_count": len(rows),
                "sample_filters_match": bool(matches), "required_fields_present": bool(fields_present),
                "response_count_matches": count_matches, "next_page_present": bool(page),
                "provider_ok_status": payload.get("status") == "OK"}
    require(ordinal == 3, "exact request ordinal required")
    dataset = range_projection(payload)
    schemas = payload.get("schema", {})
    require(type(schemas) is dict, "schema range mapping required")
    required = {s: range_projection(schemas.get(s)) for s in SCHEMAS}
    return {"ok": dataset["covers_selected_interval"] and all(r["covers_selected_interval"] for r in required.values()),
            "dataset_range": dataset, "required_schema_ranges": required}


def validate_projection(ordinal, value):
    require(type(value) is dict, "projection required")
    if set(value) == {"ok", "reason"}:
        require(value["ok"] is False and value["reason"] in {
            "http_error", "transport_error", "response_too_large", "content_encoding", "invalid_json", "invalid_payload"},
            "fixed failure projection required")
        return
    if ordinal == 0:
        observed, missing = value["observed_selected_dates"], value["missing_selected_dates"]
        require(type(observed) is list and type(missing) is list and observed == sorted(set(observed))
                and missing == sorted(set(DATES) - set(observed)) and set(observed) <= set(DATES), "exact selected-date partition required")
        require(type(value["row_count"]) is int and len(observed) <= value["row_count"] <= 1000
                and type(value["next_page_present"]) is bool, "daily counts required")
        expected = {"ok": not missing and not value["next_page_present"], "row_count": value["row_count"],
                    "observed_selected_dates": observed, "missing_selected_dates": missing,
                    "next_page_present": value["next_page_present"]}
    elif ordinal in (1, 2):
        keys = ("sample_filters_match", "required_fields_present", "response_count_matches", "next_page_present", "provider_ok_status")
        require(all(type(value[k]) is bool for k in keys) and type(value["row_count"]) is int
                and value["row_count"] in (0, 1), "sample summary shape differs")
        expected = {"ok": value["row_count"] == 1 and all(value[k] for k in keys), "requested_date": DATES[0] if ordinal == 1 else DATES[-1],
                    "row_count": value["row_count"], **{k: value[k] for k in keys}}
    else:
        def rebuild(r):
            return range_projection(None if r["range_start"] is None and r["range_end"] is None
                                    else {"start": r["range_start"], "end": r["range_end"]})
        dataset = rebuild(value["dataset_range"])
        ranges = {s: rebuild(value["required_schema_ranges"][s]) for s in SCHEMAS}
        expected = {"ok": dataset["covers_selected_interval"] and all(r["covers_selected_interval"] for r in ranges.values()),
                    "dataset_range": dataset, "required_schema_ranges": ranges}
    exact(value, expected, "projection contains invalid or unapproved fields")


def report(contract, execution, marker, receipts):
    require(len(receipts) == 4, "all four request outcomes retained")
    for i, receipt in enumerate(receipts):
        validate_receipt(receipt, contract["requests"][i], marker)
    return seal({"contract_id": ID, "artifact_type": "limited_provider_availability_report",
        "contract_sha256": contract["content_sha256"], "execution_sha256": execution["content_sha256"],
        "consumption_sha256": marker["content_sha256"], "selected_dates": list(DATES),
        "receipt_sha256": [r["content_sha256"] for r in receipts],
        "attempt_counts": {"alpaca": 1, "massive": 2, "databento": 1, "total": 4},
        "limited_availability_passed": all(r["projection"]["ok"] for r in receipts),
        "projections": [r["projection"] for r in receipts], "incremental_spend_authorized_usd": "0.00",
        "response_hash_limit": "raw bodies discarded; hosted provenance and tested projection are the witness, not independently replayable provider rows",
        **BOUNDARY})


def intent(request, marker, route, started_at):
    ordinal = request["ordinal"]
    allowed = ("massive", "polygon") if ordinal in (1, 2) else (("alpaca",) if ordinal == 0 else ("databento",))
    require(route in allowed, "fixed provider route required")
    canonical_time = stamp(started_at).isoformat()
    return seal({"contract_id": ID, "ordinal": ordinal, "request_sha256": request["request_sha256"],
        "consumption_sha256": marker["content_sha256"], "route": route, "endpoint": ROUTES[route],
        "method": "GET", "started_at": canonical_time, "attempt": 1})


def validate_receipt(value, request, marker):
    verify_seal(value)
    started = intent(request, marker, value["route"], value["started_at"])
    fields = {"contract_id", "ordinal", "request_sha256", "consumption_sha256", "route", "started_at", "finished_at",
              "intent_sha256", "status", "body_bytes_observed", "body_sha256", "body_complete", "projection", "content_sha256"}
    require(set(value) == fields, "receipt field set differs")
    for key in ("contract_id", "ordinal", "request_sha256", "consumption_sha256", "route", "started_at"):
        exact(value[key], started[key], "receipt request binding differs")
    require(value["intent_sha256"] == started["content_sha256"] and stamp(value["finished_at"]) >= stamp(value["started_at"]), "receipt time or intent differs")
    require(value["status"] is None or (type(value["status"]) is int and 100 <= value["status"] <= 599), "HTTP status required")
    require(type(value["body_bytes_observed"]) is int and 0 <= value["body_bytes_observed"] <= MAX_RESPONSE_BYTES + 1
            and type(value["body_complete"]) is bool, "bounded response observation required")
    if value["body_sha256"] is not None:
        hash_value(value["body_sha256"])
    else:
        require(value["body_bytes_observed"] == 0 and value["body_complete"] is False, "missing body commitment differs")
    if value["body_complete"]:
        require(value["body_sha256"] is not None and value["body_bytes_observed"] <= MAX_RESPONSE_BYTES, "complete body exceeds bound")
    validate_projection(request["ordinal"], value["projection"])
    if "reason" not in value["projection"]:
        require(value["status"] == 200 and value["body_complete"] is True, "successful parse requires complete HTTP 200")


def request_document(contract):
    return seal({"contract_id": ID, "request_manifest_sha256": contract["request_manifest_sha256"],
                 "requests": contract["requests"]})


def inventory(output):
    files = {}
    for path in sorted(output.iterdir()):
        require(path.is_file() and not path.is_symlink(), "regular flat evidence files required")
        if path.name != "inventory.json":
            raw = path.read_bytes()
            files[path.name] = {"bytes": len(raw), "sha256": sha(raw)}
    return seal({"contract_id": ID, "files": files, "complete": "report.json" in files})


def verify_documents(documents, contract, *, execution_commit, run_id, code_commit, code_tree, ci_run_id):
    names = {"contract.json", "execution.json", "consumption.json", "requests.json", "report.json", "inventory.json"}
    names |= {f"{kind}-{i}.json" for kind in ("intent", "receipt") for i in range(4)}
    require(set(documents) == names, "complete exact evidence inventory required")
    values = {name: json_object(raw) for name, raw in documents.items()}
    for value in values.values():
        verify_seal(value)
    exact(values["contract.json"], contract, "captured contract differs")
    execution = execution_payload(contract, code_commit=code_commit, code_tree=code_tree, ci_run_id=ci_run_id)
    exact(values["execution.json"], execution, "captured execution differs")
    marker = consumption(execution, {"GITHUB_SHA": execution_commit, "GITHUB_RUN_ID": run_id, "GITHUB_RUN_ATTEMPT": "1"})
    exact(values["consumption.json"], marker, "captured consumption differs")
    exact(values["requests.json"], request_document(contract), "captured requests differ")
    receipts = [values[f"receipt-{i}.json"] for i in range(4)]
    for i, row in enumerate(receipts):
        exact(values[f"intent-{i}.json"], intent(contract["requests"][i], marker, row["route"], row["started_at"]), "captured intent differs")
        if i:
            require(stamp(row["started_at"]) >= stamp(receipts[i-1]["finished_at"]), "request order differs")
    require(receipts[1]["route"] == receipts[2]["route"], "membership route cannot switch after a failure")
    expected = report(contract, execution, marker, receipts)
    exact(values["report.json"], expected, "availability conclusion differs")
    exact(values["inventory.json"], seal({"contract_id": ID, "complete": True,
        "files": {n: {"bytes": len(b), "sha256": sha(b)} for n, b in sorted(documents.items()) if n != "inventory.json"}}), "artifact bytes differ")
    return seal({"contract_id": ID, "verification_passed": True, "limited_availability_passed": expected["limited_availability_passed"],
        "report_sha256": expected["content_sha256"], "execution_commit_sha": execution_commit,
        "workflow_run_id": run_id, "file_count": len(names), "provider_attempts": 4,
        "raw_response_reparse_possible": False, **BOUNDARY})


def verify_archive(path, contract, *, expected_bytes, expected_sha256, **provenance):
    require(type(expected_bytes) is int and 0 < expected_bytes <= MAX_ARCHIVE_BYTES
            and Path(path).stat().st_size == expected_bytes, "bounded ZIP size required")
    raw = Path(path).read_bytes()
    require(len(raw) == expected_bytes <= MAX_ARCHIVE_BYTES and sha(raw) == expected_sha256, "external ZIP commitment differs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        require(len(infos) == len({i.filename for i in infos}) == 14 and sum(i.file_size for i in infos) <= MAX_ARCHIVE_BYTES,
                "bounded unique archive inventory required")
        for info in infos:
            require("/" not in info.filename and "\\" not in info.filename and not info.is_dir()
                    and (info.external_attr >> 16) & 0o170000 != 0o120000, "flat regular ZIP member required")
        documents = {i.filename: archive.read(i) for i in infos}
    return verify_documents(documents, contract, **provenance)
