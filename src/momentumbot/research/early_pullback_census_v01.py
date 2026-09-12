"""Unarmed census capture mechanics and byte-bound, provider-free verification.

No launcher, credential discovery, hosted consumption, or market-runtime gate is
provided here. A complete capture proves the declared protocol/bytes, not origin.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import time
import zipfile

from momentumbot.providers.massive import normalize_reference_tickers, normalize_ticker_types, reference_membership_identity
from momentumbot.research import early_pullback_capture_plan_v01 as parent

ID = "early-pullback-census-adapter-v0.1"
PARENT = "a1bdf9711183937cb55d539a3514606c77db07d6"
PARENT_TREE = "a51a8fad2133270187229c18dca7957bb0bc84a5"
PARENT_SHA = "a8111ed4eb7a64c76dbeceae51f580680c0e0ecce627402e89db10b94a452ff1"
CONTRACT_PATH = f"research/strategy/{ID}.json"
BASE = f"research/data-audits/{ID}"
OWN_FILES = ("src/momentumbot/research/early_pullback_census_v01.py",
             "src/momentumbot/research/early_pullback_census_http_v01.py",
             "scripts/validate_early_pullback_census_v01.py",
             "tests/test_early_pullback_census_v01.py")
DATES = parent.DATES
MAX_ATTEMPTS = parent.MAX_CENSUS_ATTEMPTS
MAX_BODY = 16_000_000
MAX_TOTAL = 1_500_000_000
METADATA_RESERVE = 4_000_000
MAX_PAYLOAD = MAX_TOTAL - METADATA_RESERVE
INTERVAL_NS = 12_500_000_000
REASONS = {"transport_error", "http_error", "incomplete_body", "response_too_large", "content_encoding",
           "credential_echo", "invalid_payload", "invalid_census_chain", "retention_limit", "interrupted"}
BOUNDARY = {"provider_calls_authorized_now": 0, "incremental_spend_authorized_usd": "0.00",
    "provider_origin_authenticated": False, "hosted_execution_authorized": False,
    "historical_identity_resolved": False, "historical_replay_enabled": False,
    "financial_evaluation_enabled": False, "paid_capture_enabled": False,
    "brokerage_orders_enabled": False, "discretionary_strategy_integrated": False,
    "transcript_records_read": False, "policy_promotion_eligible": False}
require, seal, fingerprint, exact = parent.require, parent.seal, parent.fingerprint, parent.exact
sha = parent.parent.sha
parse_json = parent.parent.json_object


def render(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def type_request():
    return parent.capture_plan(parent.calendar_observation())["initial_requests"][0]


def validate_request(request):
    require(type(request) is dict, "request object required")
    if request.get("kind") == "current_type_dictionary":
        exact(request, type_request(), "type request differs")
    else:
        require(request.get("kind") == "pit_membership_page", "unknown census request kind")
        require(type(request.get("params")) is dict, "request parameters required")
        expected = parent.census_request(request.get("trading_date"), page=request.get("page"),
            cursor=request.get("params", {}).get("cursor"),
            predecessor_response_sha256=request.get("predecessor_response_sha256"))
        exact(request, expected, "census request differs")


def _text(value, *, required=False):
    require(value is None or type(value) is str, "metadata strings cannot be coerced")
    if value is not None:
        require(len(value) <= 2048 and not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value), "invalid metadata text")
    if required:
        require(type(value) is str and bool(value.strip()), "required metadata string missing")


def project_body(request, raw):
    """Strict bounded schema; retain all members, including ambiguous tickers."""
    validate_request(request)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, "bounded complete body required")
    value = parse_json(raw)
    require(set(value) <= {"status", "request_id", "count", "results", "next_url"}
            and value.get("status") == "OK", "provider response schema/status differs")
    if "request_id" in value:
        _text(value["request_id"], required=True)
    rows = value.get("results")
    require(type(rows) is list and len(rows) <= parent.PAGE_LIMIT and all(type(r) is dict for r in rows), "bounded result list required")
    if "count" in value:
        require(type(value["count"]) is int and value["count"] == len(rows), "reported count differs")
    next_url = value.get("next_url")
    if request["kind"] == "current_type_dictionary":
        require(rows and next_url is None, "type dictionary must be nonempty and unpaginated")
        for row in rows:
            require(set(row) <= {"code", "description", "asset_class", "locale"}, "unknown type metadata field")
            for key, item in row.items():
                _text(item, required=key in {"code", "asset_class", "locale"})
            require(row.get("asset_class") == "stocks" and row.get("locale") == "us", "type filter mismatch")
            _text(row.get("code"), required=True)
        normalized = list(normalize_ticker_types(rows))
    else:
        fields = {"ticker", "active", "market", "locale", "name", "primary_exchange", "type", "cik",
                  "composite_figi", "share_class_figi", "currency_name", "delisted_utc", "last_updated_utc",
                  "base_currency_name", "base_currency_symbol", "currency_symbol"}
        for row in rows:
            require(set(row) <= fields, "unknown ticker metadata field")
            require(row.get("active") is True and row.get("market") == "stocks" and row.get("locale") == "us", "membership filter mismatch")
            _text(row.get("ticker"), required=True)
            for key, item in row.items():
                if key != "active":
                    _text(item)
        tickers = [r["ticker"].strip().upper() for r in rows]
        require(tickers == sorted(tickers), "provider page order regressed")
        if next_url is not None:
            parent._cursor(next_url, request["trading_date"])
        normalized = list(normalize_reference_tickers(rows))
    return {"rows": normalized, "raw_row_count": len(rows), "next_url": next_url}


class CensusState:
    """Shared pure transition checks, independently re-run by the archive reader."""
    def __init__(self):
        self.types = None
        self.pages = {d: [] for d in DATES}
        self.identities = {d: set() for d in DATES}
        self.tickers = {d: Counter() for d in DATES}
        self.missing = {d: Counter() for d in DATES}
        self.unknown = {d: set() for d in DATES}
        self.chains = {d: None for d in DATES}
        self.exhausted = set()

    def next_request(self):
        if self.types is None:
            return type_request()
        for day in DATES:
            if day not in self.exhausted:
                return parent.next_census_request(day, self.pages[day])
        return None

    def accept(self, request, raw_sha, projection):
        exact(request, self.next_request(), "request sequence differs")
        if request["kind"] == "current_type_dictionary":
            self.types = {r["code"] for r in projection["rows"]}
            return
        day = request["trading_date"]
        rows = projection["rows"]
        identities = [reference_membership_identity(r) for r in rows]
        require(len(set(identities)) == len(identities) and not self.identities[day].intersection(identities), "duplicate membership identity")
        tickers = [r["ticker"] for r in rows]
        if tickers and self.tickers[day]:
            require(tickers[0] >= max(self.tickers[day]), "cross-page ordering regression")
        page = {"request": request, "response_sha256": raw_sha, "row_count": projection["raw_row_count"], "next_url": projection["next_url"]}
        proposed = [*self.pages[day], page]
        following = parent.next_census_request(day, proposed)
        # All checks precede mutation; invalid pages never become accepted data.
        self.pages[day] = proposed
        self.identities[day].update(identities)
        self.tickers[day].update(tickers)
        for row in rows:
            for key in ("cik", "composite_figi", "share_class_figi", "primary_exchange", "type"):
                if not row[key]:
                    self.missing[day][key] += 1
            if row["type"] not in self.types:
                self.unknown[day].add(row["type"])
        self.chains[day] = fingerprint({"previous": self.chains[day], "page": projection, "response_sha256": raw_sha})
        if following is None:
            self.exhausted.add(day)

    def summary(self):
        return [{"date": d, "state": "exhausted" if d in self.exhausted else "partial" if self.pages[d] else "not_started",
                 "accepted_pages": len(self.pages[d]), "accepted_rows": sum(self.tickers[d].values()),
                 "ticker_collision_groups": sum(n > 1 for n in self.tickers[d].values()),
                 "missing_metadata_counts": dict(sorted(self.missing[d].items())),
                 "unknown_current_type_codes": sorted(self.unknown[d]), "source_chain_sha256": self.chains[d]}
                for d in DATES]


class RetainedFiles:
    def __init__(self, path):
        self.path = Path(path)
        require(not any(p.is_symlink() for p in (self.path, *self.path.parents)), "symbolic output path rejected")
        self.path.mkdir(parents=True, exist_ok=False)
        self.payload_bytes = self.metadata_bytes = 0

    def write(self, name, raw, *, payload=False):
        import os
        require(re.fullmatch(r"[A-Za-z0-9.-]+", name) and type(raw) is bytes, "flat byte file required")
        used, ceiling = (self.payload_bytes, MAX_PAYLOAD) if payload else (self.metadata_bytes, METADATA_RESERVE)
        require(used + len(raw) <= ceiling, "retention ceiling exceeded")
        with (self.path / name).open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if payload:
            self.payload_bytes += len(raw)
        else:
            self.metadata_bytes += len(raw)

    def inventory(self):
        files = {}
        for path in sorted(self.path.iterdir()):
            require(path.is_file() and not path.is_symlink(), "only regular capture files allowed")
            raw = path.read_bytes()
            files[path.name] = {"bytes": len(raw), "sha256": sha(raw)}
        return seal({"contract_id": ID, "files": files})


def report(state, attempts, failure):
    return seal({"contract_id": ID, "artifact_type": "unattributed_census_capture_report",
        "protocol_complete": state.next_request() is None and failure is None,
        "attempt_count": attempts, "failure": failure, "dates": state.summary(),
        "current_type_dictionary_captured": state.types is not None,
        "current_taxonomy_is_historical_identity_proof": False, **BOUNDARY})


class CaptureSession:
    """One-pass adapter; caller MUST separately establish capture authority.

    Transport is mandatory/injected. The only shipped command is offline-only.
    Local files do not implement hosted durable consumption or prove origin.
    """
    def __init__(self, contract, *, output, transport, credential, clock_ns=time.monotonic_ns,
                 sleeper=time.sleep, utc_now=lambda: datetime.now(timezone.utc).isoformat()):
        require(callable(transport), "explicit transport required; no default network access")
        require(type(credential) is str and 8 <= len(credential) <= 1024 and credential.isascii()
                and all(32 < ord(c) < 127 for c in credential), "bounded credential format required")
        require(type(contract) is dict and contract.get("contract_id") == ID, "adapter registration required")
        parent.parent.verify_seal(contract)
        exact(contract.get("limits"), limits(), "registered limits differ")
        self.store = RetainedFiles(output)
        self.store.write("contract.json", render(contract))
        self.contract, self.transport, self.credential = contract, transport, credential
        self.clock_ns, self.sleeper, self.utc_now = clock_ns, sleeper, utc_now
        self.state, self.attempts, self.finished = CensusState(), 0, False
        self.last_start = None

    def _once(self, request):
        from urllib.parse import quote, quote_plus
        require(self.attempts < MAX_ATTEMPTS, "HTTP attempt ceiling exceeded")
        validate_request(request)
        if self.last_start is not None:
            remaining = self.last_start + INTERVAL_NS - self.clock_ns()
            if remaining > 0:
                self.sleeper(remaining / 1_000_000_000)
        started = self.clock_ns()
        require(type(started) is int and started >= 0 and (self.last_start is None or started - self.last_start >= INTERVAL_NS), "request pacing failed")
        ordinal = self.attempts
        intent = seal({"contract_id": ID, "ordinal": ordinal, "request": request,
                       "started_at": self.utc_now(), "started_monotonic_ns": started})
        self.store.write(f"{ordinal:04d}.intent.json", render(intent))
        self.last_start = started
        self.attempts += 1
        body, status, complete, error, normalized = None, None, False, None, None
        retained = False
        try:
            reply = self.transport(request, self.credential)
            require(type(reply) is dict and set(reply) == {"status", "body", "complete", "encoding"}, "transport reply shape")
            status, body, complete = reply["status"], reply["body"], reply["complete"]
            require(type(status) is int and 100 <= status <= 599 and type(body) is bytes
                    and len(body) <= MAX_BODY + 1 and type(complete) is bool, "invalid transport observation")
            if len(body) > MAX_BODY:
                error = "response_too_large"
            elif not complete:
                error = "incomplete_body"
            elif reply["encoding"] not in ("", "identity"):
                error = "content_encoding"
            elif status != 200:
                error = "http_error"
            elif any(s.encode() in body for s in {self.credential, quote(self.credential, safe=""),
                                                quote_plus(self.credential), json.dumps(self.credential)[1:-1]}):
                error = "credential_echo"
            else:
                try:
                    normalized = project_body(request, body)
                    # Inspect decoded JSON as well: a provider echo may use
                    # Unicode escapes, including in metadata not projected.
                    decoded = render(parse_json(body))
                    if any(s.encode() in decoded for s in {self.credential, quote(self.credential, safe=""),
                                                           quote_plus(self.credential), json.dumps(self.credential)[1:-1]}):
                        error = "credential_echo"
                except (ValueError, TypeError, KeyError, UnicodeError, RuntimeError):
                    error = "invalid_payload"
                if error is None:
                    normalized_raw = render(normalized)
                    if self.store.payload_bytes + len(body) + len(normalized_raw) > MAX_PAYLOAD:
                        error = "retention_limit"
                    else:
                        self.store.write(f"{ordinal:04d}.body.json", body, payload=True)
                        self.store.write(f"{ordinal:04d}.normalized.json", normalized_raw, payload=True)
                        retained = True
                        try:
                            self.state.accept(request, sha(body), normalized)
                        except (ValueError, TypeError, KeyError, RuntimeError):
                            error = "invalid_census_chain"
        except Exception:
            error = "transport_error"
            # Only bounded, correctly typed observations may reach a receipt.
            if type(body) is not bytes or len(body) > MAX_BODY + 1:
                body = None
            if type(status) is not int or not 100 <= status <= 599:
                status = None
            complete = False
        receipt = seal({"contract_id": ID, "ordinal": ordinal, "intent_sha256": intent["content_sha256"],
            "request_sha256": request["content_sha256"], "finished_at": self.utc_now(),
            "status": status, "body_complete": complete, "body_bytes": None if body is None else len(body),
            "body_sha256": None if body is None else sha(body), "body_retained": retained,
            "normalized_sha256": fingerprint(normalized) if retained else None, "error": error})
        self.store.write(f"{ordinal:04d}.receipt.json", render(receipt))
        return error

    def run(self):
        require(not self.finished and self.attempts == 0, "capture cannot restart or resume")
        failure = None
        try:
            while (request := self.state.next_request()) is not None:
                error = self._once(request)
                if error is not None:
                    failure = {"ordinal": self.attempts - 1, "reason": error}
                    break
        except BaseException:
            failure = {"ordinal": self.attempts - 1 if self.attempts else None, "reason": "interrupted"}
            raise
        finally:
            self.finished = True
            result = report(self.state, self.attempts, failure)
            self.store.write("report.json", render(result))
            self.store.write("inventory.json", render(self.store.inventory()))
        return result


def limits():
    return {"maximum_http_attempts": MAX_ATTEMPTS, "maximum_pages_per_date": parent.MAX_PAGES,
        "maximum_rows_per_page": parent.PAGE_LIMIT, "minimum_request_interval_ns": INTERVAL_NS,
        "maximum_response_bytes": MAX_BODY, "oversize_detection_bytes": 1,
        "maximum_total_retained_bytes": MAX_TOTAL, "metadata_reserve_bytes": METADATA_RESERVE,
        "maximum_combined_raw_normalized_bytes": MAX_PAYLOAD, "automatic_retries": False,
        "redirects": False, "runtime_provider_fallback": False}


def registration(root):
    inherited = parent.validate_registration(root)
    require(inherited["content_sha256"] == PARENT_SHA, "frozen planner differs")
    files = set(inherited["file_bindings"]) | set(OWN_FILES) | {parent.CONTRACT_PATH, parent.PLAN_PATH,
        parent.BASE + "/hosted-ci-verification.json", "src/momentumbot/providers/massive.py"}
    bindings = {}
    for name in sorted(files):
        path = root / name
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), "regular bound file required")
        raw = path.read_bytes()
        bindings[name] = {"bytes": len(raw), "sha256": sha(raw)}
    return seal({"contract_id": ID, "artifact_type": "unarmed_census_adapter_registration",
        "parent_commit": PARENT, "parent_tree": PARENT_TREE, "parent_registration_sha256": PARENT_SHA,
        "selected_dates": list(DATES), "limits": limits(), "file_bindings": bindings,
        "hypothesis": "bounded one-pass census mechanics and byte replay distinguish complete protocol capture from missing, invalid and exhausted inputs",
        "entrypoint": "offline validation only; no credential discovery or hosted capture launcher",
        "next_gate": "separate tested exact-parent hosted launcher, durable single-use consumption and subscription entitlement; verify external archive commitment and origin before historical identity work",
        **BOUNDARY})


def validate_registration(root):
    saved = parent.parent.frozen(root / CONTRACT_PATH)
    exact(saved, registration(root), "census adapter registration differs")
    return saved


def verify_archive(path, *, expected_bytes, expected_sha256, expected_inventory_sha256, contract):
    """Reparse a complete capture; partial captures remain retained, never pass.

    Outer pins must come from independently verified provenance. This reader
    does not supply that provenance or activate any historical runtime gate.
    """
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)) and type(expected_bytes) is int
            and 0 < expected_bytes <= MAX_TOTAL and path.stat().st_size == expected_bytes, "archive size differs")
    for pin in (expected_sha256, expected_inventory_sha256):
        parent.parent.hash_value(pin)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    require(digest.hexdigest() == expected_sha256, "external archive hash differs")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        require(len(names) == len(set(names)) and 3 <= len(names) <= 4 * MAX_ATTEMPTS + 3, "archive member population differs")
        require(sum(i.file_size for i in infos) <= MAX_TOTAL, "uncompressed retention ceiling")
        payload_size = sum(i.file_size for i in infos if i.filename.endswith((".body.json", ".normalized.json")))
        require(payload_size <= MAX_PAYLOAD and sum(i.file_size for i in infos) - payload_size <= METADATA_RESERVE,
                "separate payload/metadata retention ceiling")
        for item in infos:
            require(re.fullmatch(r"(?:contract|report|inventory)\.json|[0-9]{4}\.(?:intent|receipt|body|normalized)\.json", item.filename)
                    and not item.is_dir() and stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG)
                    and item.file_size <= (MAX_BODY if item.filename.endswith(".body.json") else
                                          MAX_PAYLOAD if item.filename.endswith(".normalized.json") else METADATA_RESERVE),
                    "unsafe or oversized member")
        raw_inventory = archive.read("inventory.json")
        require(sha(raw_inventory) == expected_inventory_sha256, "independent inventory hash differs")
        inventory = parse_json(raw_inventory)
        parent.parent.verify_seal(inventory)
        require(set(inventory) == {"contract_id", "files", "content_sha256"} and inventory["contract_id"] == ID
                and set(inventory["files"]) == set(names) - {"inventory.json"}, "inventory population differs")
        for name, spec in inventory["files"].items():
            raw = archive.read(name)
            exact(spec, {"bytes": len(raw), "sha256": sha(raw)}, "member byte commitment differs")
        exact(parse_json(archive.read("contract.json")), contract, "independent contract differs")
        state, count, previous_ns = CensusState(), 0, None
        expected_names = {"contract.json", "report.json", "inventory.json"}
        while (request := state.next_request()) is not None:
            require(count < MAX_ATTEMPTS, "archive attempt ceiling")
            prefix = f"{count:04d}"
            required = {prefix + "." + suffix + ".json" for suffix in ("intent", "receipt", "body", "normalized")}
            require(required <= set(names), "complete page evidence missing")
            expected_names.update(required)
            intent, receipt = (parse_json(archive.read(prefix + "." + suffix + ".json")) for suffix in ("intent", "receipt"))
            for doc in (intent, receipt):
                parent.parent.verify_seal(doc)
            started_ns = intent.get("started_monotonic_ns")
            require(type(started_ns) is int and started_ns >= 0 and (previous_ns is None or started_ns - previous_ns >= INTERVAL_NS), "capture pacing differs")
            previous_ns = started_ns
            started_at, finished_at = datetime.fromisoformat(intent["started_at"]), datetime.fromisoformat(receipt["finished_at"])
            require(started_at.tzinfo is not None and finished_at.tzinfo is not None and finished_at >= started_at, "invalid capture clock")
            exact(intent, seal({"contract_id": ID, "ordinal": count, "request": request,
                               "started_at": intent["started_at"], "started_monotonic_ns": started_ns}), "intent differs")
            raw = archive.read(prefix + ".body.json")
            projection = project_body(request, raw)
            require(archive.read(prefix + ".normalized.json") == render(projection), "raw/normalized projection differs")
            exact(receipt, seal({"contract_id": ID, "ordinal": count, "intent_sha256": intent["content_sha256"],
                "request_sha256": request["content_sha256"], "finished_at": receipt["finished_at"],
                "status": 200, "body_complete": True, "body_bytes": len(raw), "body_sha256": sha(raw),
                "body_retained": True, "normalized_sha256": fingerprint(projection), "error": None}), "receipt differs")
            state.accept(request, sha(raw), projection)
            count += 1
        require(set(names) == expected_names, "extra evidence or requests after exhaustion")
        exact(parse_json(archive.read("report.json")), report(state, count, None), "terminal census report differs")
        return seal({"contract_id": ID, "archive_bytes": expected_bytes, "archive_sha256": expected_sha256,
            "inventory_file_sha256": expected_inventory_sha256, "attempt_count": count,
            "verified_member_count": len(names), "protocol_complete": True, "dates": state.summary(), **BOUNDARY})
