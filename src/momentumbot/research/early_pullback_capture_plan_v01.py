"""Provider-free calendar, dependency graph and bounded census request planner.

Page-chain checks prove request mechanics only, not vendor origin or membership
completeness. There is deliberately no network transport or execution authority.
"""
from datetime import date, datetime, time, timezone
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

from momentumbot.research import early_pullback_provider_check_v01 as parent

ID = "early-pullback-capture-plan-v0.1"
PARENT = "cc59ca3f98861e98ae5b81335e76c10e5d2cca87"
PARENT_TREE = "4fd733ee57664651ce61519562d0f97862660ff6"
PARENT_SHA = "976149812906907f86bc5f6a8b46c8590ed87c4476c210f557b081f056e29a5b"
REPORT_SHA = "652617e5539103ad984243d00afb9297d4c794bf20fa31720788ced4c6056429"
VERIFICATION_SHA = "f317d377651a217fe38c846fd8dbc47e4a07148dc90b2fcac91a903fa4919e06"
CONTRACT_PATH = f"research/strategy/{ID}.json"
BASE = f"research/data-audits/{ID}"
CALENDAR_PATH = BASE + "/official-calendar-observation.json"
PLAN_PATH = BASE + "/capture-plan.json"
OWN_FILES = ("src/momentumbot/research/early_pullback_capture_plan_v01.py",
             "scripts/build_early_pullback_capture_plan_v01.py",
             "tests/test_early_pullback_capture_plan_v01.py", CALENDAR_PATH)
DATES = parent.DATES
NY = ZoneInfo("America/New_York")
HOLIDAYS = ("2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
            "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25")
EARLY_CLOSES = ("2026-11-27", "2026-12-24")
CENSUS_ROUTE = "https://api.massive.com/v3/reference/tickers"
MAX_PAGES = 20
PAGE_LIMIT = 1000
MAX_CENSUS_ATTEMPTS = len(DATES) * MAX_PAGES + 1
require, seal, fingerprint, exact = parent.require, parent.seal, parent.fingerprint, parent.exact
BOUNDARY = {"provider_calls_authorized_now": 0, "incremental_spend_authorized_usd": "0.00",
    "provider_transport_implemented": False, "complete_capture_inventory_materialized": False,
    "point_in_time_universe_authenticated": False, "historical_replay_enabled": False,
    "financial_evaluation_enabled": False, "paid_capture_enabled": False,
    "brokerage_orders_enabled": False, "discretionary_strategy_integrated": False,
    "transcript_records_read": False, "policy_promotion_eligible": False}


def calendar_observation():
    """Manually checked public schedules, not a raw HTTP archive or halt history."""
    facts = {"year": 2026, "timezone": "America/New_York", "weekdays": [0, 1, 2, 3, 4],
             "regular_open": "09:30", "regular_close": "16:00",
             "closed_dates": list(HOLIDAYS), "early_close_dates": list(EARLY_CLOSES),
             "early_close_time": "13:00"}
    return seal({"artifact_type": "manually_verified_official_schedule_projection",
        "observed_on_utc_date": "2026-09-12", "sources": [
            {"publisher": "NYSE", "url": "https://www.nyse.com/trade/hours-calendars",
             "facts": facts},
            {"publisher": "Nasdaq", "url": "https://www.nasdaq.com/market-activity/stock-market-holiday-schedule",
             "facts": facts}],
        "raw_http_bodies_retained": False, "raw_http_body_hashes": None,
        "provenance_limit": "human-checked public schedule facts; local hash binds this transcription, not independently downloaded website bytes",
        "unscheduled_closures_or_security_halts_verified": False,
        "historical_provider_calendar_captured": False})


def scheduled_sessions(observation):
    exact(observation, calendar_observation(), "official schedule projection differs")
    rows = []
    for value in DATES:
        day = date.fromisoformat(value)
        require(day.weekday() < 5 and value not in HOLIDAYS and value not in EARLY_CLOSES,
                "selected date is not a scheduled full session; never substitute dates")
        opened = datetime.combine(day, time(9, 30), NY)
        closed = datetime.combine(day, time(16), NY)
        rows.append({"date": value, "open": opened.isoformat(), "close": closed.isoformat(),
                     "open_utc": opened.astimezone(timezone.utc).isoformat(),
                     "close_utc": closed.astimezone(timezone.utc).isoformat(),
                     "scheduled_minutes": int((closed - opened).total_seconds() // 60)})
    return rows


def census_request(day, *, page=1, cursor=None, predecessor_response_sha256=None):
    require(type(day) is str and day in DATES, "exact selected census date required")
    require(type(page) is int and 1 <= page <= MAX_PAGES, "census page ceiling exceeded")
    fixed = {"market": "stocks", "locale": "us", "active": "true", "date": day,
             "order": "asc", "sort": "ticker", "limit": PAGE_LIMIT}
    if page == 1:
        require(cursor is None and predecessor_response_sha256 is None, "first page cannot have a cursor")
        params = fixed
    else:
        require(type(cursor) is str and re.fullmatch(r"[A-Za-z0-9_+=/.-]{1,2048}", cursor),
                "bounded opaque cursor required")
        parent.hash_value(predecessor_response_sha256)
        params = {"cursor": cursor}
    return seal({"kind": "pit_membership_page", "method": "GET", "url": CENSUS_ROUTE,
        "trading_date": day, "page": page, "params": params, "root_query": fixed,
        "predecessor_response_sha256": predecessor_response_sha256})


def _cursor(next_url, day):
    require(type(next_url) is str and len(next_url) <= 4096
            and next_url.isascii() and all(32 < ord(c) < 127 for c in next_url),
            "invalid bounded next URL")
    url = urlsplit(next_url)
    require(url.scheme == "https" and url.netloc == "api.massive.com"
            and url.path == "/v3/reference/tickers" and not url.fragment,
            "pagination origin or path differs")
    pairs = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
    require(len(pairs) == len(dict(pairs)), "duplicate pagination parameter")
    params = dict(pairs)
    fixed = census_request(day)["root_query"]
    require("cursor" in params and set(params) <= set(fixed) | {"cursor"},
            "unregistered pagination parameter or embedded credential")
    for key, value in params.items():
        if key != "cursor":
            require(value == str(fixed[key]), "pagination changed root query")
    cursor = params["cursor"]
    require(re.fullmatch(r"[A-Za-z0-9_+=/.-]{1,2048}", cursor), "invalid opaque cursor")
    return cursor


def next_census_request(day, pages):
    """Pure chain check; caller receipts are NOT authenticated provider evidence.

    A failed/partial HTTP attempt must be retained by a future durable runner and
    must never be presented here as a successful page. None means exhausted page
    syntax only; it does not prove a usable historical universe.
    """
    require(type(pages) is list and len(pages) <= MAX_PAGES, "bounded page chain required")
    request = census_request(day)
    seen, total_rows = set(), 0
    for index, page in enumerate(pages):
        require(type(page) is dict and set(page) == {
            "request", "response_sha256", "row_count", "next_url"}, "exact page receipt fields required")
        exact(page["request"], request, "page request order or identity differs")
        parent.hash_value(page["response_sha256"])
        count = page["row_count"]
        require(type(count) is int and 0 <= count <= PAGE_LIMIT, "invalid census row count")
        total_rows += count
        if page["next_url"] is None:
            require(index == len(pages) - 1, "page after terminal exhaustion")
            require(total_rows > 0, "empty complete census is unavailable, not a no-opportunity day")
            return None
        cursor = _cursor(page["next_url"], day)
        require(cursor not in seen, "repeated cursor")
        seen.add(cursor)
        request = census_request(day, page=index + 2, cursor=cursor,
                                 predecessor_response_sha256=page["response_sha256"])
    return request


def dependency_graph():
    """Every unresolved node stays explicit; this is not an exact HTTP inventory."""
    specifications = [
        ("calendar", [], "scheduled_sessions_confirmed_only", "official-calendar-observation.json",
         "scheduled hours do not prove realized hours or security halt state"),
        ("membership", ["calendar"], "bounded_initial_requests_prepared", "scripts/build_massive_historical_census.py",
         "all 30 PIT censuses; exhausted pages; preserved security identities; type dictionary is current taxonomy, not historical membership"),
        ("identity_actions", ["membership"], "blocked_on_membership", "scripts/audit_historical_identity_continuity.py",
         "historical identities, ticker-change and split evidence; original 120-day history and causal share-unit resolution; no current asset-master substitution"),
        ("discovery", ["identity_actions"], "blocked_on_identity", "scripts/build_identity_resolved_market_discovery_v04.py",
         "full membership cross-section and frozen general/small profile union; split/split gain, raw price/volume, exact RVOL; no selected ticker list"),
        ("float_news", ["discovery"], "blocked_on_candidates", "docs/research/sealed_historical_source_acquisition_v13.md",
         "exact candidate CIK/FIGI lineage; SEC acceptance and news publication times; explicit missing/ambiguous enrichment; preserve verified v0.13 fixes"),
        ("scanner", ["discovery", "float_news"], "blocked_on_causal_sources", "src/momentumbot/research/early_pullback_panel_sources_v01.py",
         "complete candidate-minute dispositions and original first qualifying profile-union activations, reconstructed not declared"),
        ("micro_sources", ["scanner"], "blocked_on_activations", "src/momentumbot/research/sealed_historical_micro_inputs_v01.py",
         "shared SIP trades earliest activation to 10:00 New York; seven-day split warmup before 04:00; verified raw-minute reuse and causal normalization"),
        ("micro", ["micro_sources"], "blocked_on_verified_capture", "src/momentumbot/research/early_pullback_panel_sources_v01.py",
         "all original triggers and prefixes before first-two gate; verified empty and unavailable remain different"),
        ("execution_plan", ["micro"], "blocked_on_triggers", "docs/research/sealed_historical_execution_inputs_v01.md",
         "exact common XNAS.ITCH mbp-1/status requests from all original triggers; nanosecond bounds; raw_symbol and ts_recv; no consolidated NBBO claim"),
        ("management_plan", ["micro", "micro_sources"], "blocked_on_triggers_and_reuse", "docs/research/sealed_historical_account_inputs_v01.md",
         "minute-floor trigger through decision+900s+60s; original per-opportunity bounds and merged shared SIP/minute windows; verify reuse before tails"),
        ("exit_plan", ["management_plan", "execution_plan"], "blocked_on_exact_windows", "docs/research/sealed_historical_management_runner_v01.md",
         "all original management execution windows for both arms; exact quote/status union before any arm performance; preserve unresolved terminal state"),
        ("paid_quote", ["execution_plan", "exit_plan"], "blocked_on_exact_requests", "docs/research/sealed_historical_execution_quote_v01.md",
         "exact manifests first; get_billable_size plus get_cost once per request; finite per-request and aggregate quotes; metadata-only separate authority"),
        ("capture", ["paid_quote", "management_plan"], "blocked_on_verified_quotes_and_authority", "docs/research/sealed_historical_execution_acquisition_v02.md",
         "independent quote verification; frozen per-request and aggregate hard ceilings; separate one-shot consumption; bounded re-quote and download; retain partial evidence"),
        ("paired_accounts", ["capture", "micro"], "blocked_on_authenticated_sources", "src/momentumbot/research/early_pullback_panel_accounts_v01.py",
         "all 24 independent paths/720 slots; full prior-close chain; no reseeding, fabricated fills, omitted late triggers or retrospective policy tuning"),
    ]
    return [{"id": identity, "depends_on": parents, "state": state, "mechanics_reference": reference,
             "requirement": requirement, "exact_http_request_count": None,
             "quoted_cost_usd": None, "capture_authorized": False}
            for identity, parents, state, reference, requirement in specifications]


def capture_plan(observation):
    sessions = scheduled_sessions(observation)
    roots = [seal({"kind": "current_type_dictionary", "method": "GET",
                   "url": CENSUS_ROUTE + "/types", "params": {"asset_class": "stocks", "locale": "us"}})]
    roots.extend(census_request(day) for day in DATES)
    return seal({"contract_id": ID, "artifact_type": "unarmed_staged_capture_plan",
        "parent_commit": PARENT, "calendar_projection_sha256": observation["content_sha256"],
        "selected_dates": list(DATES), "scheduled_sessions": sessions,
        "scheduled_full_session_count": len(sessions), "realized_full_sessions_verified": False,
        "initial_requests": roots, "initial_request_count": len(roots),
        "initial_request_manifest_sha256": fingerprint(roots),
        "census_limits": {"maximum_pages_per_date": MAX_PAGES, "maximum_rows_per_page": PAGE_LIMIT,
            "maximum_total_http_attempts_if_separately_armed": MAX_CENSUS_ATTEMPTS,
            "ticker_type_calls": 1, "minimum_request_interval_seconds": "12.5",
            "automatic_retries": False, "redirects": False, "runtime_provider_fallback": False,
            "budget_exhaustion_is_failure_not_truncation": True,
            "maximum_response_bytes_proposed": 16_000_000,
            "maximum_normalized_retained_bytes_proposed": 1_500_000_000},
        "dependency_graph": dependency_graph(),
        "unmaterialized_request_parameters": ["pagination cursors", "PIT identities and symbol batches",
            "candidate CIKs", "scanner activations", "Micro trigger timestamps", "verified source reuse gaps",
            "management/exit request union"],
        "complete_capture_http_ceiling": None, "paid_per_request_cost_ceilings_usd": None,
        "paid_aggregate_cost_ceiling_usd": None, "actual_incremental_billing_known": False,
        "consumed_provider_check_may_be_reused": False,
        "next_gate": "new tested census transport and full byte/identity/exhaustion verifier; independent durable single-use execution authority; existing subscription entitlement with zero incremental spend",
        **BOUNDARY})


def registration(root):
    inherited = parent.validate_registration(root)
    require(inherited["content_sha256"] == PARENT_SHA, "frozen provider parent differs")
    evidence = {parent.BASE + "/hosted-report.json": REPORT_SHA,
                parent.BASE + "/hosted-verification.json": VERIFICATION_SHA}
    for path, expected in evidence.items():
        require(parent.frozen(root / path)["content_sha256"] == expected, "verified availability evidence differs")
    observation = parent.frozen(root / CALENDAR_PATH)
    plan = capture_plan(observation)
    references = {node["mechanics_reference"] for node in dependency_graph() if node["id"] != "calendar"}
    files = set(inherited["file_bindings"]) | set(OWN_FILES) | set(evidence) | references | {parent.CONTRACT_PATH}
    bindings = {}
    for name in sorted(files):
        path = root / name
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), "regular bound file required")
        raw = path.read_bytes()
        bindings[name] = {"bytes": len(raw), "sha256": parent.sha(raw)}
    return seal({"contract_id": ID, "artifact_type": "unarmed_capture_planning_registration",
        "parent_commit": PARENT, "parent_tree": PARENT_TREE, "parent_registration_sha256": PARENT_SHA,
        "capture_plan_sha256": plan["content_sha256"], "file_bindings": bindings,
        "hypothesis": "official schedules and bounded census pagination can prepare causal source dependencies without granting capture authority or manufacturing completeness",
        **BOUNDARY})


def validate_registration(root):
    expected = registration(root)
    exact(parent.frozen(root / CONTRACT_PATH), expected, "capture registration differs")
    exact(parent.frozen(root / PLAN_PATH), capture_plan(parent.frozen(root / CALENDAR_PATH)), "capture plan differs")
    return expected
