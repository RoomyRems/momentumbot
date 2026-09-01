"""Strict, provider-free validation for sealed source acquisition v0.4.

This module deliberately contains no authorization body or frozen authorization
hash.  It validates an already materialized source tree and constructs a
strictly typed acquisition report.  Provider access, workflow dispatch, and
one-shot consumption remain workflow concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable, Iterable, Mapping

from momentumbot.models import StrategyProfile
from momentumbot.providers.massive import (
    reference_membership_fingerprint,
    reference_ticker_fingerprint,
)
from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.research.sealed_historical_source_acquisition import (
    ALLOWED_REQUEST_HOSTS,
    MAX_CENSUS_PAGES_PER_DATE,
    MAX_RETAINED_BYTES,
)
from momentumbot.research.sealed_historical_source_acquisition_v02 import (
    MAX_HTTP_ATTEMPTS,
)


SCHEMA_VERSION = 1
ARTIFACT_TYPE = "sealed_historical_source_acquisition_v0_4_result"
EXPECTED_REPOSITORY = "RoomyRems/momentumbot"
EXPECTED_AUTHORIZATION_ID = "sealed-historical-source-acquisition-v0.4"
EXPECTED_DATES = tuple(SELECTED_DATES)
MAX_CANDIDATES_PER_DATE_V04 = 100
EXPECTED_CHECKPOINT_ARTIFACT_ID = "sealed-historical-source-checkpoint-v0.1"
EXPECTED_CHECKPOINT_BINDING_TYPE = (
    "sealed_historical_source_checkpoint_post_scanner_binding_v0.1"
)
EXPECTED_IDENTITY_ID = "identity-resolved-universe-v0.1"
EXPECTED_MARKET_ID = "causal-market-discovery-v0.3"
EXPECTED_FLOAT_ID = "causal-sec-float-v0.2"
EXPECTED_NEWS_ID = "causal-alpaca-news-v0.2"
EXPECTED_SCANNER_ADDITION_ID = "causal-scanner-snapshot-v0.3"
EXPECTED_SOURCE_INPUT_ID = "causal-scanner-source-inputs-v0.2"
EXPECTED_PRE_SCANNER_FILE_COUNT = 706
EXPECTED_COMPLETED_SOURCE_FILE_COUNT = 767
EXPECTED_ENVIRONMENT_PATHS = {
    "freeze_path": "environment/pip-freeze.txt",
    "requirements_path": "environment/requirements-sealed-source-v04.txt",
}
AUXILIARY_MANIFEST_ROOTS = (
    "identity-continuity-v0.1",
    "instrument-metadata-audit",
    "market-data-coverage",
    "provisional-universe-v0.1",
)
BLOCKED_ATTEMPT_CATEGORIES = (
    "hostname",
    "https_transport",
    "redirect",
    "request_budget",
    "socket",
    "subprocess",
)

EXPECTED_SOURCE_INPUT_BASIS = {
    "displayed_price": "raw_candidate_close",
    "cumulative_volume": "raw_candidate_volume",
    "percent_gain": "split_target_close_over_split_previous_close",
    "cross_sectional_rank": "split_target_close_over_split_previous_close",
    "raw_split_candidate_timestamp_coverage_required_equal": True,
}

_LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LOWER_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")
_WORKFLOW_REF = re.compile(
    r"^RoomyRems/momentumbot/\.github/workflows/"
    r"sealed-historical-source-acquisition-v04\.ya?ml@refs/heads/main$"
)

GATE_KEYS = frozenset(
    {
        "census_complete",
        "identity_complete",
        "market_discovery_complete",
        "float_complete",
        "news_complete",
        "scanner_snapshot_complete",
        "canonical_scanner_inputs_complete",
        "present_day_asset_master_skipped",
        "provider_free_snapshot_replay_exact",
        "historical_profile_union_exact",
    }
)
SOURCE_HASH_KEYS = frozenset(
    {
        "census_file",
        "identity",
        "market",
        "float",
        "news",
        "scanner",
        "source_inputs",
    }
)
DATE_HASH_KEYS = frozenset(
    {
        "market_manifest_file",
        "market_candidates",
        "float_target_basis",
        "float_manifest_file",
        "float_records",
        "news_manifest_file",
        "source_input_manifest",
        "source_input_logical_records",
        "scanner_manifest",
        "scanner_payload",
    }
)
SOURCE_SUMMARY_KEYS = frozenset(
    {
        "dates",
        "census_page_counts",
        "census_row_counts",
        "candidate_counts",
        "canonical_source_input_compressed_bytes",
        "scanner_row_counts",
        "source_hashes",
        "date_hashes",
        "manifest_file_sha256",
        "source_tree_content_sha256",
        "source_file_count",
        "source_retained_file_bytes",
        "provider_free_replay_exact_by_date",
        "gates",
    }
)
SOURCE_CHECKPOINT_BINDING_KEYS = frozenset(
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
    }
)


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        output[key] = value
    return output


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required at {path}")
    return payload


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _LOWER_SHA256.fullmatch(value) is not None


def _strict_int(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _exact_dates(value: object, *, label: str) -> list[str]:
    expected = list(EXPECTED_DATES)
    if not isinstance(value, list) or value != expected:
        raise ValueError(f"{label} dates must exactly match the frozen 30 dates")
    return expected


def _strict_date_map(
    value: object,
    *,
    label: str,
    minimum: int = 0,
    maximum: int | None = None,
) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(EXPECTED_DATES):
        raise ValueError(f"{label} must cover exactly the frozen 30 dates")
    output: dict[str, int] = {}
    for trading_date in EXPECTED_DATES:
        number = _strict_int(value[trading_date], label=f"{label} {trading_date}", minimum=minimum)
        if maximum is not None and number > maximum:
            raise ValueError(f"{label} {trading_date} exceeds {maximum}")
        output[trading_date] = number
    return output


def _strict_sha_map(
    value: object,
    *,
    label: str,
    exact_keys: Iterable[str] | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{label} must be a nonempty SHA-256 map")
    if exact_keys is not None and set(value) != set(exact_keys):
        raise ValueError(f"{label} keys changed")
    output: dict[str, str] = {}
    for key, digest in value.items():
        if not isinstance(key, str) or not key or not _is_sha256(digest):
            raise ValueError(f"{label} contains an invalid SHA-256 entry")
        output[key] = str(digest)
    return dict(sorted(output.items()))


def _frozen_authorization_content_sha256() -> str:
    """Resolve the exact authority lazily without duplicating its body here."""

    from momentumbot.research.sealed_historical_source_authorization_v04 import (
        AUTHORIZATION_CONTENT_SHA256,
    )

    if not _is_sha256(AUTHORIZATION_CONTENT_SHA256):
        raise ValueError("frozen v0.4 authorization hash is invalid")
    return AUTHORIZATION_CONTENT_SHA256


def expected_manifest_paths_v04(
    *,
    identity_policy_id: str = EXPECTED_IDENTITY_ID,
    market_policy_id: str = EXPECTED_MARKET_ID,
    float_policy_id: str = EXPECTED_FLOAT_ID,
    news_policy_id: str = EXPECTED_NEWS_ID,
    scanner_artifact_id: str = EXPECTED_SCANNER_ADDITION_ID,
    source_input_artifact_id: str = EXPECTED_SOURCE_INPUT_ID,
) -> frozenset[str]:
    """Return the exact 191-manifest census for one completed source tree."""

    dated_roots = (
        market_policy_id,
        float_policy_id,
        news_policy_id,
        scanner_artifact_id,
        source_input_artifact_id,
    )
    file_only_roots = (identity_policy_id, *AUXILIARY_MANIFEST_ROOTS)
    return frozenset(
        {
            "manifest.json",
            *(f"{value}/manifest.json" for value in EXPECTED_DATES),
            *(f"{name}/manifest.json" for name in file_only_roots),
            *(f"{name}/manifest.json" for name in dated_roots),
            *(
                f"{name}/{value}/manifest.json"
                for name in dated_roots
                for value in EXPECTED_DATES
            ),
        }
    )


def expected_source_file_paths_v04() -> frozenset[str]:
    """Return the exact completed v0.4 source-file layout (767 files)."""

    paths: set[str] = {"manifest.json", "massive-ticker-types.json"}
    for trading_date in EXPECTED_DATES:
        paths.update(
            {
                f"{trading_date}/manifest.json",
                f"{trading_date}/tickers.json",
                f"{trading_date}/alpaca-current-reconciliation.csv",
                f"{EXPECTED_IDENTITY_ID}/{trading_date}-included.json",
            }
        )
    paths.add(f"{EXPECTED_IDENTITY_ID}/manifest.json")
    for root in ("instrument-metadata-audit", "market-data-coverage"):
        paths.add(f"{root}/manifest.json")
        for trading_date in EXPECTED_DATES:
            paths.update(
                {f"{root}/{trading_date}.csv", f"{root}/{trading_date}.json"}
            )
    provisional = "provisional-universe-v0.1"
    paths.add(f"{provisional}/manifest.json")
    for trading_date in EXPECTED_DATES:
        paths.update(
            {
                f"{provisional}/{trading_date}.csv",
                f"{provisional}/{trading_date}.json",
                f"{provisional}/{trading_date}-included.json",
            }
        )
    identity_continuity = "identity-continuity-v0.1"
    paths.update(
        {
            f"{identity_continuity}/{name}"
            for name in (
                "manifest.json",
                "identity-bridge.json",
                "alias-validation.json",
                "transition-name-change-resolution.json",
                "corporate-action-windows.json",
                "massive-ticker-event-sample.json",
            )
        }
    )
    dated_files = {
        EXPECTED_MARKET_ID: (
            "manifest.json",
            "discovery.csv",
            "acquisition-audit.csv",
            "identity-resolved-membership.json",
            "market-candidates.json",
            "float-target-basis.json",
        ),
        EXPECTED_FLOAT_ID: ("manifest.json", "float-records.json"),
        EXPECTED_NEWS_ID: ("manifest.json", "news-records.json"),
        EXPECTED_SOURCE_INPUT_ID: ("manifest.json", "market-inputs.jsonl.gz"),
        EXPECTED_SCANNER_ADDITION_ID: (
            "manifest.json",
            "scanner-snapshot.json",
        ),
    }
    for root, names in dated_files.items():
        paths.add(f"{root}/manifest.json")
        for trading_date in EXPECTED_DATES:
            paths.update(f"{root}/{trading_date}/{name}" for name in names)
    if len(paths) != EXPECTED_COMPLETED_SOURCE_FILE_COUNT:
        raise ValueError("internal v0.4 source-file census changed")
    return frozenset(paths)


def validate_source_checkpoint_binding_v04(
    value: Mapping[str, object],
) -> dict[str, object]:
    """Validate the provider/source checkpoint's post-scanner binding."""

    binding = dict(value)
    if set(binding) != SOURCE_CHECKPOINT_BINDING_KEYS:
        raise ValueError("source checkpoint binding fields changed")
    if (
        type(binding.get("schema_version")) is not int
        or binding.get("schema_version") != 1
        or binding.get("binding_type") != EXPECTED_CHECKPOINT_BINDING_TYPE
        or binding.get("checkpoint_artifact_id")
        != EXPECTED_CHECKPOINT_ARTIFACT_ID
        or binding.get("sole_permitted_addition_id")
        != EXPECTED_SCANNER_ADDITION_ID
    ):
        raise ValueError("source checkpoint binding identity changed")
    claimed = binding.get("content_sha256")
    if not _is_sha256(claimed):
        raise ValueError("source checkpoint binding content hash is invalid")
    unsigned = {
        key: item for key, item in binding.items() if key != "content_sha256"
    }
    if claimed != _fingerprint(unsigned):
        raise ValueError("source checkpoint binding content hash mismatch")
    for key in (
        "checkpoint_content_sha256",
        "checkpoint_file_sha256",
        "pre_scanner_tree_content_sha256",
        "post_scanner_tree_content_sha256",
    ):
        if not _is_sha256(binding.get(key)):
            raise ValueError(f"source checkpoint {key} is invalid")
    pre_count = _strict_int(
        binding.get("pre_scanner_file_count"),
        label="pre-scanner checkpoint file count",
        minimum=1,
    )
    post_count = _strict_int(
        binding.get("post_scanner_file_count"),
        label="post-scanner checkpoint file count",
        minimum=1,
    )
    # The real v0.2/v0.3 layout is 706 pre-scanner files; v0.4 adds exactly
    # one scanner root manifest plus a manifest and snapshot for every date.
    if (
        pre_count != EXPECTED_PRE_SCANNER_FILE_COUNT
        or post_count != EXPECTED_COMPLETED_SOURCE_FILE_COUNT
        or post_count != pre_count + 1 + (2 * len(EXPECTED_DATES))
    ):
        raise ValueError("source checkpoint scanner file addition count changed")
    pre_bytes = _strict_int(
        binding.get("pre_scanner_retained_file_bytes"),
        label="pre-scanner checkpoint retained bytes",
        minimum=1,
    )
    post_bytes = _strict_int(
        binding.get("post_scanner_retained_file_bytes"),
        label="post-scanner checkpoint retained bytes",
        minimum=1,
    )
    if post_bytes <= pre_bytes:
        raise ValueError("source checkpoint scanner addition retained no bytes")

    environment = binding.get("environment")
    environment_keys = {
        "freeze_path",
        "freeze_size_bytes",
        "freeze_sha256",
        "requirements_path",
        "requirements_size_bytes",
        "requirements_sha256",
    }
    if not isinstance(environment, Mapping) or set(environment) != environment_keys:
        raise ValueError("source checkpoint environment binding is invalid")
    for key, expected in EXPECTED_ENVIRONMENT_PATHS.items():
        if environment.get(key) != expected:
            raise ValueError("source checkpoint environment path changed")
    for key in ("freeze_sha256", "requirements_sha256"):
        if not _is_sha256(environment.get(key)):
            raise ValueError("source checkpoint environment hash is invalid")
    for key in ("freeze_size_bytes", "requirements_size_bytes"):
        _strict_int(
            environment.get(key),
            label=f"source checkpoint environment {key}",
            minimum=1,
        )

    request_budget = binding.get("request_budget")
    if not isinstance(request_budget, Mapping) or set(request_budget) != {
        "schema_version",
        "allowed_hosts",
        "maximum_total_http_attempts",
        "total_attempts",
        "by_host",
    }:
        raise ValueError("source checkpoint request-budget binding is invalid")
    if (
        type(request_budget.get("schema_version")) is not int
        or request_budget.get("schema_version") != 1
        or request_budget.get("allowed_hosts") != sorted(ALLOWED_REQUEST_HOSTS)
        or type(request_budget.get("maximum_total_http_attempts")) is not int
        or request_budget.get("maximum_total_http_attempts") != MAX_HTTP_ATTEMPTS
    ):
        raise ValueError("source checkpoint request authority changed")
    total = _strict_int(
        request_budget.get("total_attempts"),
        label="source checkpoint total attempts",
        minimum=1,
    )
    by_host = request_budget.get("by_host")
    if not isinstance(by_host, Mapping) or list(by_host) != sorted(by_host):
        raise ValueError("source checkpoint request hosts are not canonical")
    observed_counts: dict[str, int] = {}
    for host, count in by_host.items():
        if not isinstance(host, str) or host not in ALLOWED_REQUEST_HOSTS:
            raise ValueError("source checkpoint includes an unauthorized host")
        observed_counts[host] = _strict_int(
            count,
            label=f"source checkpoint requests for {host}",
        )
    if sum(observed_counts.values()) != total or total > MAX_HTTP_ATTEMPTS:
        raise ValueError("source checkpoint request counts are inconsistent")

    blocked = binding.get("blocked_attempts")
    if not isinstance(blocked, Mapping) or set(blocked) != {
        "schema_version",
        "total_blocked_attempts",
        "by_category",
        "by_host",
    }:
        raise ValueError("source checkpoint blocked-attempt binding is invalid")
    categories = blocked.get("by_category")
    hosts = blocked.get("by_host")
    if (
        type(blocked.get("schema_version")) is not int
        or blocked.get("schema_version") != 1
        or type(blocked.get("total_blocked_attempts")) is not int
        or blocked.get("total_blocked_attempts") != 0
        or not isinstance(categories, Mapping)
        or tuple(sorted(categories)) != tuple(sorted(BLOCKED_ATTEMPT_CATEGORIES))
        or any(type(categories[key]) is not int or categories[key] != 0 for key in categories)
        or hosts != {}
    ):
        raise ValueError("successful checkpoint contains a blocked provider attempt")

    authorization = binding.get("authorization")
    if not isinstance(authorization, Mapping) or set(authorization) != {
        "authorization_id",
        "authorization_content_sha256",
    }:
        raise ValueError("source checkpoint authorization binding is invalid")
    if (
        authorization.get("authorization_id") != EXPECTED_AUTHORIZATION_ID
        or authorization.get("authorization_content_sha256")
        != _frozen_authorization_content_sha256()
    ):
        raise ValueError("source checkpoint authorization changed")

    provenance = binding.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("source checkpoint provenance binding is invalid")
    normalized_provenance = _workflow_provenance(
        repository=str(provenance.get("repository") or ""),
        authorization_commit_sha=str(
            provenance.get("authorization_commit_sha") or ""
        ),
        authorization_tree_sha=str(provenance.get("authorization_tree_sha") or ""),
        dispatcher_workflow_sha=str(
            provenance.get("dispatcher_workflow_sha") or ""
        ),
        dispatcher_workflow_ref=str(
            provenance.get("dispatcher_workflow_ref") or ""
        ),
        workflow_run_id=provenance.get("workflow_run_id", ""),
        workflow_run_attempt=provenance.get("workflow_run_attempt"),  # type: ignore[arg-type]
    )
    if dict(provenance) != normalized_provenance:
        raise ValueError("source checkpoint provenance is not canonical")
    return binding


def _date_manifest_map(
    manifest: Mapping[str, object],
    *,
    label: str,
    date_field: str = "trading_date",
) -> dict[str, dict[str, object]]:
    rows = manifest.get("date_manifests")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_DATES):
        raise ValueError(f"{label} date manifests are incomplete")
    output: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label} date manifest must be an object")
        trading_date = row.get(date_field)
        if not isinstance(trading_date, str) or trading_date in output:
            raise ValueError(f"{label} date manifests repeat or omit a date")
        date.fromisoformat(trading_date)
        output[trading_date] = row
    if set(output) != set(EXPECTED_DATES):
        raise ValueError(f"{label} date manifests must cover exactly 30 dates")
    return output


def _validate_projected_root(
    root: Path,
    manifest: dict[str, object],
    *,
    label: str,
    artifact_id: str,
    projection_keys: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    if manifest.get("artifact_id") != artifact_id:
        raise ValueError(f"{label} root artifact ID changed")
    _exact_dates(manifest.get("dates"), label=label)
    children = _date_manifest_map(manifest, label=label)
    projection = {key: manifest.get(key) for key in projection_keys}
    if manifest.get("content_sha256") != _fingerprint(projection):
        raise ValueError(f"{label} root content hash mismatch")
    for trading_date, embedded in children.items():
        observed = _load_json_object(root / trading_date / "manifest.json")
        if observed != embedded:
            raise ValueError(f"{label} root/date manifest mismatch for {trading_date}")
    return children


def _validate_full_root(
    root: Path,
    manifest: dict[str, object],
    *,
    label: str,
    artifact_id: str,
) -> dict[str, dict[str, object]]:
    if manifest.get("artifact_id") != artifact_id:
        raise ValueError(f"{label} root artifact ID changed")
    _exact_dates(manifest.get("dates"), label=label)
    children = _date_manifest_map(manifest, label=label)
    body = {key: value for key, value in manifest.items() if key != "content_sha256"}
    if manifest.get("content_sha256") != _fingerprint(body):
        raise ValueError(f"{label} root content hash mismatch")
    for trading_date, embedded in children.items():
        observed = _load_json_object(root / trading_date / "manifest.json")
        if observed != embedded:
            raise ValueError(f"{label} root/date manifest mismatch for {trading_date}")
    return children


def _validate_census(root: Path) -> tuple[dict[str, object], dict[str, int], dict[str, int]]:
    manifest = _load_json_object(root / "manifest.json")
    _exact_dates(manifest.get("dates"), label="census")
    if manifest.get("all_fetches_complete") is not True:
        raise ValueError("census is incomplete")
    if manifest.get("current_alpaca_reconciliation_skipped") is not True:
        raise ValueError("census used the present-day Alpaca asset master")
    children = _date_manifest_map(
        manifest,
        label="census",
        date_field="requested_asof_date",
    )
    page_counts: dict[str, int] = {}
    row_counts: dict[str, int] = {}
    for trading_date, embedded in children.items():
        date_root = root / trading_date
        observed = _load_json_object(date_root / "manifest.json")
        if observed != embedded:
            raise ValueError(f"census root/date manifest mismatch for {trading_date}")
        ticker_payload = _load_json_object(date_root / "tickers.json")
        rows = ticker_payload.get("rows")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError(f"census ticker rows are invalid for {trading_date}")
        ticker_sha = reference_ticker_fingerprint(rows)  # type: ignore[arg-type]
        membership_sha = reference_membership_fingerprint(rows)  # type: ignore[arg-type]
        if (
            ticker_payload.get("requested_asof_date") != trading_date
            or ticker_payload.get("content_sha256") != ticker_sha
            or ticker_payload.get("membership_sha256") != membership_sha
            or embedded.get("census_content_sha256") != ticker_sha
            or embedded.get("membership_sha256") != membership_sha
        ):
            raise ValueError(f"census ticker hashes changed for {trading_date}")
        page_count = _strict_int(
            embedded.get("page_count"),
            label=f"census page count {trading_date}",
            minimum=1,
        )
        if page_count > MAX_CENSUS_PAGES_PER_DATE:
            raise ValueError(f"census page count exceeds ceiling for {trading_date}")
        pages = embedded.get("pages")
        if not isinstance(pages, list) or len(pages) != page_count:
            raise ValueError(f"census pages disagree with count for {trading_date}")
        page_row_sum = 0
        for page in pages:
            if not isinstance(page, Mapping):
                raise ValueError(f"census page is invalid for {trading_date}")
            page_row_sum += _strict_int(
                page.get("row_count"),
                label=f"census page row count {trading_date}",
            )
        summary = embedded.get("census_summary")
        if not isinstance(summary, Mapping):
            raise ValueError(f"census summary is missing for {trading_date}")
        row_count = _strict_int(
            summary.get("row_count"),
            label=f"census row count {trading_date}",
            minimum=1,
        )
        recorded_page_row_sum = _strict_int(
            embedded.get("page_row_sum"),
            label=f"census recorded page row sum {trading_date}",
        )
        if (
            row_count != len(rows)
            or recorded_page_row_sum != page_row_sum
            or page_row_sum != len(rows)
            or embedded.get("pagination_exhausted") is not True
            or embedded.get("fetch_complete") is not True
        ):
            raise ValueError(f"census completeness accounting changed for {trading_date}")
        page_counts[trading_date] = page_count
        row_counts[trading_date] = row_count
    return manifest, page_counts, row_counts


@dataclass(frozen=True)
class DeepValidationAPIs:
    identity_policy_id: str
    market_policy_id: str
    float_policy_id: str
    news_policy_id: str
    scanner_artifact_id: str
    source_input_artifact_id: str
    load_identity: Callable[
        ..., tuple[list[dict[str, object]], dict[str, object], dict[str, object]]
    ]
    load_market: Callable[
        ..., tuple[list[dict[str, object]], dict[str, object], dict[str, object]]
    ]
    load_target_basis: Callable[..., tuple[list[dict[str, object]], dict[str, object]]]
    load_float_root: Callable[..., dict[str, object]]
    load_float: Callable[..., tuple[list[dict[str, object]], dict[str, object]]]
    load_news: Callable[
        ...,
        tuple[
            list[dict[str, object]],
            list[dict[str, object]],
            dict[str, object],
        ],
    ]
    load_source_inputs: Callable[..., tuple[object, dict[str, object]]]
    load_scanner: Callable[
        ..., tuple[list[dict[str, object]], dict[str, object], dict[str, object]]
    ]
    replay_rows: Callable[..., list[dict[str, object]]]
    profile_manifest: Callable[[StrategyProfile], dict[str, object]]
    profile_union_manifest: Callable[[], dict[str, object]]
    validate_profile: Callable[[StrategyProfile], None]


def _default_validation_apis() -> DeepValidationAPIs:
    """Resolve additive v0.4 APIs only when deep validation is invoked."""

    from momentumbot.causal_market_discovery_v03 import (
        CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
        load_market_candidate_payload,
        strategy_profile_manifest,
    )
    from momentumbot.causal_scanner_snapshot_v03 import (
        CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
        build_scanner_snapshot_rows,
        load_causal_scanner_snapshot,
    )
    from momentumbot.historical_float_v04 import (
        CAUSAL_FLOAT_POLICY_ID,
        load_causal_float_records,
        load_causal_float_root,
        load_float_target_basis,
    )
    from momentumbot.historical_news import (
        CAUSAL_NEWS_POLICY_ID,
        load_publication_timed_news,
    )
    from momentumbot.historical_profile_union_v01 import (
        historical_profile_union_v0_1_manifest,
        validate_historical_profile_union_v0_1,
    )
    from momentumbot.identity_resolved_universe import (
        IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        load_identity_resolved_universe,
    )
    from momentumbot.scanner_source_inputs_v03 import (
        ARTIFACT_ID as SOURCE_INPUT_ARTIFACT_ID,
        load_scanner_source_input_bundle,
    )

    return DeepValidationAPIs(
        identity_policy_id=IDENTITY_RESOLVED_UNIVERSE_POLICY_ID,
        market_policy_id=CAUSAL_MARKET_DISCOVERY_V0_3_POLICY_ID,
        float_policy_id=CAUSAL_FLOAT_POLICY_ID,
        news_policy_id=CAUSAL_NEWS_POLICY_ID,
        scanner_artifact_id=CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
        source_input_artifact_id=SOURCE_INPUT_ARTIFACT_ID,
        load_identity=load_identity_resolved_universe,
        load_market=load_market_candidate_payload,
        load_target_basis=load_float_target_basis,
        load_float_root=load_causal_float_root,
        load_float=load_causal_float_records,
        load_news=load_publication_timed_news,
        load_source_inputs=load_scanner_source_input_bundle,
        load_scanner=load_causal_scanner_snapshot,
        replay_rows=build_scanner_snapshot_rows,
        profile_manifest=strategy_profile_manifest,
        profile_union_manifest=historical_profile_union_v0_1_manifest,
        validate_profile=validate_historical_profile_union_v0_1,
    )


def _validate_source_tree_shape(
    source_root: Path,
    *,
    apis: DeepValidationAPIs,
) -> frozenset[str]:
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("historical source root must be a real directory")
    dated_roots = (
        apis.market_policy_id,
        apis.float_policy_id,
        apis.news_policy_id,
        apis.scanner_artifact_id,
        apis.source_input_artifact_id,
    )
    file_only_roots = (apis.identity_policy_id, *AUXILIARY_MANIFEST_ROOTS)
    expected_top_directories = {
        *EXPECTED_DATES,
        *dated_roots,
        *file_only_roots,
    }
    observed_top_directories = {
        path.name for path in source_root.iterdir() if path.is_dir()
    }
    if observed_top_directories != expected_top_directories:
        raise ValueError("historical source top-level directories changed")
    for name in dated_roots:
        observed_dates = {
            path.name for path in (source_root / name).iterdir() if path.is_dir()
        }
        if observed_dates != set(EXPECTED_DATES):
            raise ValueError(f"historical source {name} date directories changed")
    for name in file_only_roots:
        if any(path.is_dir() for path in (source_root / name).iterdir()):
            raise ValueError(f"historical source {name} gained a directory")

    expected_manifests = expected_manifest_paths_v04(
        identity_policy_id=apis.identity_policy_id,
        market_policy_id=apis.market_policy_id,
        float_policy_id=apis.float_policy_id,
        news_policy_id=apis.news_policy_id,
        scanner_artifact_id=apis.scanner_artifact_id,
        source_input_artifact_id=apis.source_input_artifact_id,
    )
    observed_manifests = {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("manifest.json")
    }
    if observed_manifests != expected_manifests:
        raise ValueError("historical source manifest paths changed")
    observed_files: set[str] = set()
    for path in source_root.rglob("*"):
        relative = path.relative_to(source_root).as_posix()
        if path.is_symlink():
            raise ValueError(f"historical source contains a symlink: {relative}")
        mode = path.lstat().st_mode
        if stat.S_ISREG(mode):
            observed_files.add(relative)
        elif not stat.S_ISDIR(mode):
            raise ValueError(f"historical source contains a special file: {relative}")
    for relative in sorted(observed_files):
        if relative.endswith(".json"):
            _load_json_object(source_root / relative)
    fixed_ids = (
        apis.identity_policy_id,
        apis.market_policy_id,
        apis.float_policy_id,
        apis.news_policy_id,
        apis.scanner_artifact_id,
        apis.source_input_artifact_id,
    )
    if fixed_ids == (
        EXPECTED_IDENTITY_ID,
        EXPECTED_MARKET_ID,
        EXPECTED_FLOAT_ID,
        EXPECTED_NEWS_ID,
        EXPECTED_SCANNER_ADDITION_ID,
        EXPECTED_SOURCE_INPUT_ID,
    ) and observed_files != expected_source_file_paths_v04():
        raise ValueError("historical source completed file paths changed")
    return expected_manifests


def _source_tree_commitment(source_root: Path) -> dict[str, object]:
    """Recompute the checkpoint-compatible tree commitment without following links."""

    directories: list[str] = []
    files: list[dict[str, object]] = []
    for directory, names, filenames in os.walk(source_root, followlinks=False):
        names.sort()
        filenames.sort()
        parent = Path(directory)
        for name in names:
            path = parent / name
            relative = path.relative_to(source_root).as_posix()
            if path.is_symlink() or not stat.S_ISDIR(path.lstat().st_mode):
                raise ValueError(f"historical source directory is unsafe: {relative}")
            directories.append(relative)
        for name in filenames:
            path = parent / name
            relative = path.relative_to(source_root).as_posix()
            if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError(f"historical source file is unsafe: {relative}")
            files.append(
                {
                    "path": relative,
                    "size_bytes": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
    directories.sort()
    files.sort(key=lambda row: str(row["path"]))
    unsigned: dict[str, object] = {
        "directory_count": len(directories),
        "directories": directories,
        "file_count": len(files),
        "files": files,
    }
    return {
        **unsigned,
        "tree_content_sha256": _fingerprint(unsigned),
        "retained_file_bytes": sum(int(row["size_bytes"]) for row in files),
    }


def _manifest_file_hashes(
    source_root: Path,
    *,
    expected_paths: Iterable[str],
) -> dict[str, str]:
    output: dict[str, str] = {}
    for relative in sorted(expected_paths):
        path = source_root / relative
        _load_json_object(path)
        output[relative] = _file_sha256(path)
    if not output:
        raise ValueError("historical source tree contains no manifests")
    return output


def summarize_source_root_v04(
    root: str | Path,
    *,
    profile: StrategyProfile,
    _apis: DeepValidationAPIs | None = None,
) -> dict[str, object]:
    """Deep-validate every frozen date and replay scanner rows provider-free."""

    source_root = Path(root)
    apis = _apis or _default_validation_apis()
    apis.validate_profile(profile)
    expected_profile = apis.profile_manifest(profile)
    expected_profile_union = apis.profile_union_manifest()
    if expected_profile_union.get("profile_union_id") != (
        "historical-profile-union-v0.1"
    ):
        raise ValueError("historical acquisition profile union ID changed")

    census, page_counts, row_counts = _validate_census(source_root)
    identity_root = source_root / apis.identity_policy_id
    market_root = source_root / apis.market_policy_id
    float_root = source_root / apis.float_policy_id
    news_root = source_root / apis.news_policy_id
    scanner_root = source_root / apis.scanner_artifact_id
    source_input_root = source_root / apis.source_input_artifact_id
    expected_manifest_paths = _validate_source_tree_shape(
        source_root,
        apis=apis,
    )

    identity_manifest = _load_json_object(identity_root / "manifest.json")
    _exact_dates(identity_manifest.get("dates"), label="identity")
    if not _is_sha256(identity_manifest.get("content_sha256")):
        raise ValueError("identity root content hash is invalid")
    market_manifest = _load_json_object(market_root / "manifest.json")
    market_children = _validate_projected_root(
        market_root,
        market_manifest,
        label="market",
        artifact_id=apis.market_policy_id,
        projection_keys=(
            "discovery_policy",
            "source_membership_bundle_sha256",
            "date_manifests",
        ),
    )
    if market_manifest.get("acquisition_profile_union") != expected_profile_union:
        raise ValueError("market root acquisition profile union changed")
    if market_manifest.get("source_membership_bundle_sha256") != (
        identity_manifest.get("content_sha256")
    ):
        raise ValueError("market root identity lineage changed")
    float_manifest = apis.load_float_root(
        float_root,
        expected_dates=EXPECTED_DATES,
        expected_source_market_discovery_bundle_sha256=market_manifest.get(
            "content_sha256"
        ),
    )
    if _load_json_object(float_root / "manifest.json") != float_manifest:
        raise ValueError("float root changed while loading")
    if float_manifest.get("artifact_id") != apis.float_policy_id:
        raise ValueError("float root artifact ID changed")
    float_children = _date_manifest_map(float_manifest, label="float")
    news_manifest = _load_json_object(news_root / "manifest.json")
    news_children = _validate_projected_root(
        news_root,
        news_manifest,
        label="news",
        artifact_id=apis.news_policy_id,
        projection_keys=(
            "news_policy",
            "temporal_boundary",
            "source_market_discovery_bundle_sha256",
            "source_float_bundle_sha256",
            "date_manifests",
        ),
    )
    if (
        news_manifest.get("acquisition_profile_union") != expected_profile_union
        or news_manifest.get("strategy_profiles_modified") is not False
    ):
        raise ValueError("news root acquisition profile union changed")
    if (
        news_manifest.get("source_market_discovery_bundle_sha256")
        != market_manifest.get("content_sha256")
        or news_manifest.get("source_float_bundle_sha256")
        != float_manifest.get("content_sha256")
    ):
        raise ValueError("news root source lineage changed")
    if news_manifest.get("fatal_provider_errors") != []:
        raise ValueError("news root retains fatal provider errors")
    source_input_manifest = _load_json_object(source_input_root / "manifest.json")
    source_input_children = _validate_full_root(
        source_input_root,
        source_input_manifest,
        label="canonical source input",
        artifact_id=apis.source_input_artifact_id,
    )
    scanner_manifest = _load_json_object(scanner_root / "manifest.json")
    scanner_children = _validate_full_root(
        scanner_root,
        scanner_manifest,
        label="scanner",
        artifact_id=apis.scanner_artifact_id,
    )
    expected_source_bundle_hashes = {
        "membership": str(identity_manifest["content_sha256"]),
        "market": str(market_manifest["content_sha256"]),
        "float": str(float_manifest["content_sha256"]),
        "news": str(news_manifest["content_sha256"]),
    }
    for label, manifest in (
        ("canonical source input", source_input_manifest),
        ("scanner", scanner_manifest),
    ):
        if (
            manifest.get("acquisition_profile_union") != expected_profile_union
            or manifest.get("strategy_profiles_modified") is not False
        ):
            raise ValueError(f"{label} root acquisition profile union changed")
        if manifest.get("source_bundle_hashes") != expected_source_bundle_hashes:
            raise ValueError(f"{label} root source lineage changed")
    if scanner_manifest.get("source_input_bundle_sha256") != (
        source_input_manifest.get("content_sha256")
    ):
        raise ValueError("scanner root canonical-input lineage changed")

    candidate_counts: dict[str, int] = {}
    compressed_bytes: dict[str, int] = {}
    scanner_row_counts: dict[str, int] = {}
    date_hashes: dict[str, dict[str, str]] = {}
    replay_exact: dict[str, bool] = {}

    for trading_date in EXPECTED_DATES:
        membership_rows, membership_payload, loaded_identity_root = apis.load_identity(
            identity_root,
            trading_date=trading_date,
        )
        if loaded_identity_root != identity_manifest:
            raise ValueError(f"identity root changed while loading {trading_date}")
        candidate_rows, candidate_payload, market_date_manifest = apis.load_market(
            market_root / trading_date
        )
        if market_date_manifest != market_children[trading_date]:
            raise ValueError(f"market date manifest changed for {trading_date}")
        if market_date_manifest.get("strategy_profile") != expected_profile:
            raise ValueError(f"market strategy profile changed for {trading_date}")
        if (
            market_date_manifest.get("acquisition_profile_union")
            != expected_profile_union
        ):
            raise ValueError(
                f"market acquisition profile union changed for {trading_date}"
            )
        membership_sha = membership_payload.get("summary", {}).get(
            "membership_sha256"
        )
        market_membership = market_date_manifest.get("source_membership")
        if (
            not _is_sha256(membership_sha)
            or not isinstance(market_membership, Mapping)
            or market_membership.get("membership_sha256") != membership_sha
            or market_membership.get("membership_bundle_sha256")
            != identity_manifest.get("content_sha256")
            or market_membership.get("membership_payload_sha256")
            != _fingerprint(membership_payload)
        ):
            raise ValueError(f"market identity lineage changed for {trading_date}")
        target_relative = market_date_manifest.get("files", {}).get(
            "float_target_basis"
        )
        if not isinstance(target_relative, str) or not target_relative:
            raise ValueError(f"market float target basis is missing for {trading_date}")
        target_path = Path(target_relative)
        if target_path.is_absolute() or ".." in target_path.parts:
            raise ValueError(f"market float target basis escapes for {trading_date}")
        _target_pairs, target_basis_payload = apis.load_target_basis(
            market_root / trading_date / target_path,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
            expected_trading_date=trading_date,
        )
        target_basis_sha = target_basis_payload.get("content_sha256")
        if not _is_sha256(target_basis_sha):
            raise ValueError(f"float target-basis hash is invalid for {trading_date}")
        float_records, float_date_manifest = apis.load_float(
            float_root / trading_date,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
            expected_trading_date=trading_date,
            expected_source_market_discovery_manifest_sha256=(
                _fingerprint(market_date_manifest)
            ),
            expected_source_float_target_basis_sha256=target_basis_sha,
        )
        float_commitment = float_children[trading_date]
        if (
            float_date_manifest.get("content_sha256")
            != float_commitment.get("manifest_content_sha256")
            or _file_sha256(float_root / trading_date / "manifest.json")
            != float_commitment.get("manifest_file_sha256")
        ):
            raise ValueError(f"float date commitment changed for {trading_date}")
        market_date_sha = _fingerprint(market_date_manifest)
        if (
            float_date_manifest.get("source_market_candidates_sha256")
            != candidate_payload.get("content_sha256")
            or float_date_manifest.get(
                "source_market_discovery_manifest_sha256"
            )
            != market_date_sha
            or float_date_manifest.get("source_float_target_basis_sha256")
            != target_basis_sha
        ):
            raise ValueError(f"float market lineage changed for {trading_date}")
        float_records_sha = float_date_manifest.get("summary", {}).get("records_sha256")
        if not _is_sha256(float_records_sha):
            raise ValueError(f"float record hash is invalid for {trading_date}")
        news_events, news_statuses, news_date_manifest = apis.load_news(
            news_root / trading_date,
            candidate_rows=candidate_rows,
            candidate_payload=candidate_payload,
            source_float_records_sha256=float_records_sha,
        )
        if news_date_manifest != news_children[trading_date]:
            raise ValueError(f"news date manifest changed for {trading_date}")
        if (
            news_date_manifest.get("acquisition_profile_union")
            != expected_profile_union
            or news_date_manifest.get("strategy_profiles_modified") is not False
        ):
            raise ValueError(
                f"news acquisition profile union changed for {trading_date}"
            )
        if (
            news_date_manifest.get("source_market_candidates_sha256")
            != candidate_payload.get("content_sha256")
            or news_date_manifest.get(
                "source_market_discovery_manifest_sha256"
            )
            != market_date_sha
            or news_date_manifest.get("source_float_records_sha256")
            != float_records_sha
            or news_date_manifest.get("source_float_manifest_sha256")
            != float_date_manifest.get("content_sha256")
            or news_date_manifest.get("source_float_target_basis_sha256")
            != target_basis_sha
        ):
            raise ValueError(f"news source lineage changed for {trading_date}")
        source_inputs, source_date_manifest = apis.load_source_inputs(
            source_input_root / trading_date,
            profile=profile,
        )
        if source_date_manifest != source_input_children[trading_date]:
            raise ValueError(f"canonical input manifest changed for {trading_date}")
        if source_date_manifest.get("basis") != EXPECTED_SOURCE_INPUT_BASIS:
            raise ValueError(
                f"canonical input normalized rank basis changed for {trading_date}"
            )
        if (
            source_date_manifest.get("acquisition_profile_union")
            != expected_profile_union
            or source_date_manifest.get("strategy_profiles_modified") is not False
        ):
            raise ValueError(
                f"canonical input acquisition profile union changed for {trading_date}"
            )
        if getattr(source_inputs, "trading_date", None) != date.fromisoformat(trading_date):
            raise ValueError(f"canonical input date changed for {trading_date}")
        if set(getattr(source_inputs, "candidate_symbols", ())) != {
            str(row.get("symbol") or "") for row in candidate_rows
        }:
            raise ValueError(f"canonical input candidates changed for {trading_date}")
        snapshot_rows, snapshot_payload, snapshot_date_manifest = apis.load_scanner(
            scanner_root / trading_date,
            candidate_rows=candidate_rows,
            profile=profile,
            source_inputs=source_inputs,
        )
        if snapshot_date_manifest != scanner_children[trading_date]:
            raise ValueError(f"scanner date manifest changed for {trading_date}")
        if snapshot_date_manifest.get("strategy_profile") != expected_profile:
            raise ValueError(f"scanner profile union changed for {trading_date}")
        if (
            snapshot_date_manifest.get("acquisition_profile_union")
            != expected_profile_union
            or snapshot_date_manifest.get("strategy_profiles_modified") is not False
        ):
            raise ValueError(
                f"scanner acquisition profile union changed for {trading_date}"
            )
        replayed_rows = apis.replay_rows(
            trading_date=date.fromisoformat(trading_date),
            profile=profile,
            candidate_rows=candidate_rows,
            float_records=float_records,
            news_events=news_events,
            news_statuses=news_statuses,
            membership_symbols=getattr(source_inputs, "membership_symbols"),
            previous_close_by_symbol=getattr(source_inputs, "previous_close_by_symbol"),
            rank_split_minute_bars_by_symbol=getattr(
                source_inputs, "rank_split_minute_bars_by_symbol"
            ),
            candidate_raw_minute_bars_by_symbol=getattr(
                source_inputs, "candidate_raw_minute_bars_by_symbol"
            ),
            candidate_exact_rvol_by_symbol=getattr(
                source_inputs, "candidate_exact_rvol_by_symbol"
            ),
        )
        if replayed_rows != snapshot_rows:
            raise ValueError(f"provider-free scanner replay differs for {trading_date}")

        candidate_count = _strict_int(
            len(candidate_rows), label=f"candidate count {trading_date}"
        )
        if candidate_count > MAX_CANDIDATES_PER_DATE_V04:
            raise ValueError(f"candidate ceiling exceeded for {trading_date}")
        source_summary = source_date_manifest.get("summary")
        if not isinstance(source_summary, Mapping):
            raise ValueError(f"canonical input summary is missing for {trading_date}")
        compressed = _strict_int(
            source_summary.get("compressed_size_bytes"),
            label=f"canonical input compressed bytes {trading_date}",
            minimum=1,
        )
        logical_sha = source_summary.get("logical_records_sha256")
        if not _is_sha256(logical_sha):
            raise ValueError(f"canonical input logical hash is invalid for {trading_date}")
        expected_input_hashes = {
            "identity_resolved_membership": str(membership_sha),
            "market_candidates": str(candidate_payload["content_sha256"]),
            "market_discovery_manifest": market_date_sha,
            "causal_float_records": str(float_records_sha),
            "causal_float_manifest": _fingerprint(float_date_manifest),
            "publication_timed_news_events": _fingerprint(news_events),
            "publication_timed_news_statuses": _fingerprint(news_statuses),
            "publication_timed_news_manifest": _fingerprint(news_date_manifest),
            "reacquired_market_inputs": str(logical_sha),
        }
        if getattr(source_inputs, "source_hashes", None) != expected_input_hashes:
            raise ValueError(
                f"canonical input upstream lineage changed for {trading_date}"
            )
        snapshot_sha = snapshot_payload.get("content_sha256")
        if not _is_sha256(snapshot_sha):
            raise ValueError(f"scanner payload hash is invalid for {trading_date}")
        candidate_sha = candidate_payload.get("content_sha256")
        if not _is_sha256(candidate_sha):
            raise ValueError(f"market candidate hash is invalid for {trading_date}")

        candidate_counts[trading_date] = candidate_count
        compressed_bytes[trading_date] = compressed
        scanner_row_counts[trading_date] = len(snapshot_rows)
        replay_exact[trading_date] = True
        date_hashes[trading_date] = {
            "market_manifest_file": _file_sha256(
                market_root / trading_date / "manifest.json"
            ),
            "market_candidates": str(candidate_sha),
            "float_target_basis": str(target_basis_sha),
            "float_manifest_file": _file_sha256(
                float_root / trading_date / "manifest.json"
            ),
            "float_records": str(float_records_sha),
            "news_manifest_file": _file_sha256(
                news_root / trading_date / "manifest.json"
            ),
            "source_input_manifest": str(source_date_manifest["content_sha256"]),
            "source_input_logical_records": str(logical_sha),
            "scanner_manifest": str(snapshot_date_manifest["content_sha256"]),
            "scanner_payload": str(snapshot_sha),
        }
        _strict_sha_map(
            date_hashes[trading_date],
            label=f"date hashes {trading_date}",
            exact_keys=DATE_HASH_KEYS,
        )
        if membership_payload.get("trading_date") != trading_date:
            raise ValueError(f"identity payload date changed for {trading_date}")
        if not isinstance(membership_rows, list):
            raise ValueError(f"identity rows are invalid for {trading_date}")

    source_hashes = {
        "census_file": _file_sha256(source_root / "manifest.json"),
        "identity": str(identity_manifest["content_sha256"]),
        "market": str(market_manifest["content_sha256"]),
        "float": str(float_manifest["content_sha256"]),
        "news": str(news_manifest["content_sha256"]),
        "scanner": str(scanner_manifest["content_sha256"]),
        "source_inputs": str(source_input_manifest["content_sha256"]),
    }
    _strict_sha_map(source_hashes, label="source hashes", exact_keys=SOURCE_HASH_KEYS)
    gates = {
        "census_complete": census.get("all_fetches_complete") is True,
        "identity_complete": identity_manifest.get("eligibility", {}).get(
            "complete_relative_to_provisional_membership"
        )
        is True,
        "market_discovery_complete": market_manifest.get("eligibility", {}).get(
            "causal_market_discovery_complete"
        )
        is True,
        "float_complete": float_manifest.get("eligibility", {}).get(
            "point_in_time_float_decisions_frozen"
        )
        is True,
        "news_complete": news_manifest.get("eligibility", {}).get(
            "publication_timed_news_frozen"
        )
        is True,
        "scanner_snapshot_complete": scanner_manifest.get("eligibility", {}).get(
            "candidate_minute_dispositions_frozen"
        )
        is True,
        "canonical_scanner_inputs_complete": source_input_manifest.get(
            "replay_boundary", {}
        ).get("canonical_runtime_inputs_persisted")
        is True,
        "present_day_asset_master_skipped": census.get(
            "current_alpaca_reconciliation_skipped"
        )
        is True,
        "provider_free_snapshot_replay_exact": all(
            replay_exact.get(value) is True for value in EXPECTED_DATES
        ),
        "historical_profile_union_exact": True,
    }
    if set(gates) != GATE_KEYS or any(value is not True for value in gates.values()):
        raise ValueError("historical source v0.4 completeness gate failed")

    tree = _source_tree_commitment(source_root)
    summary = {
        "dates": list(EXPECTED_DATES),
        "census_page_counts": page_counts,
        "census_row_counts": row_counts,
        "candidate_counts": candidate_counts,
        "canonical_source_input_compressed_bytes": compressed_bytes,
        "scanner_row_counts": scanner_row_counts,
        "source_hashes": dict(sorted(source_hashes.items())),
        "date_hashes": date_hashes,
        "manifest_file_sha256": _manifest_file_hashes(
            source_root,
            expected_paths=expected_manifest_paths,
        ),
        "source_tree_content_sha256": tree["tree_content_sha256"],
        "source_file_count": tree["file_count"],
        "source_retained_file_bytes": tree["retained_file_bytes"],
        "provider_free_replay_exact_by_date": replay_exact,
        "gates": gates,
    }
    validate_source_summary_v04(
        summary,
        expected_manifest_paths=expected_manifest_paths,
        expected_source_file_count=int(tree["file_count"]),
    )
    return summary


def validate_source_summary_v04(
    summary: Mapping[str, object],
    *,
    expected_manifest_paths: Iterable[str] | None = None,
    expected_source_file_count: int = EXPECTED_COMPLETED_SOURCE_FILE_COUNT,
) -> None:
    if set(summary) != SOURCE_SUMMARY_KEYS:
        raise ValueError("historical source v0.4 summary fields changed")
    _exact_dates(summary.get("dates"), label="source summary")
    _strict_date_map(
        summary.get("census_page_counts"),
        label="census page counts",
        minimum=1,
        maximum=MAX_CENSUS_PAGES_PER_DATE,
    )
    _strict_date_map(summary.get("census_row_counts"), label="census row counts", minimum=1)
    _strict_date_map(
        summary.get("candidate_counts"),
        label="candidate counts",
        maximum=MAX_CANDIDATES_PER_DATE_V04,
    )
    _strict_date_map(
        summary.get("canonical_source_input_compressed_bytes"),
        label="canonical source-input compressed bytes",
        minimum=1,
    )
    _strict_date_map(summary.get("scanner_row_counts"), label="scanner row counts")
    source_hashes = _strict_sha_map(
        summary.get("source_hashes"),
        label="source hashes",
        exact_keys=SOURCE_HASH_KEYS,
    )
    date_hashes = summary.get("date_hashes")
    if not isinstance(date_hashes, Mapping) or set(date_hashes) != set(EXPECTED_DATES):
        raise ValueError("date hashes must cover exactly the frozen 30 dates")
    normalized_date_hashes: dict[str, dict[str, str]] = {}
    for trading_date in EXPECTED_DATES:
        normalized_date_hashes[trading_date] = _strict_sha_map(
            date_hashes[trading_date],
            label=f"date hashes {trading_date}",
            exact_keys=DATE_HASH_KEYS,
        )
    manifest_hashes = _strict_sha_map(
        summary.get("manifest_file_sha256"),
        label="manifest file hashes",
        exact_keys=(
            expected_manifest_paths
            if expected_manifest_paths is not None
            else expected_manifest_paths_v04()
        ),
    )
    if not _is_sha256(summary.get("source_tree_content_sha256")):
        raise ValueError("source tree content hash is invalid")
    file_count = _strict_int(
        summary.get("source_file_count"),
        label="source file count",
        minimum=1,
    )
    if file_count != expected_source_file_count:
        raise ValueError("source file count differs from the completed v0.4 layout")
    _strict_int(
        summary.get("source_retained_file_bytes"),
        label="source retained file bytes",
        minimum=1,
    )
    if source_hashes["census_file"] != manifest_hashes["manifest.json"]:
        raise ValueError("census source hash differs from its manifest file hash")
    if set(manifest_hashes) == set(expected_manifest_paths_v04()):
        for trading_date in EXPECTED_DATES:
            row = normalized_date_hashes[trading_date]
            expected_file_hashes = {
                "market_manifest_file": manifest_hashes[
                    f"{EXPECTED_MARKET_ID}/{trading_date}/manifest.json"
                ],
                "float_manifest_file": manifest_hashes[
                    f"{EXPECTED_FLOAT_ID}/{trading_date}/manifest.json"
                ],
                "news_manifest_file": manifest_hashes[
                    f"{EXPECTED_NEWS_ID}/{trading_date}/manifest.json"
                ],
            }
            if any(row[key] != digest for key, digest in expected_file_hashes.items()):
                raise ValueError(
                    f"date manifest file hashes disagree for {trading_date}"
                )
    replay = summary.get("provider_free_replay_exact_by_date")
    if (
        not isinstance(replay, Mapping)
        or set(replay) != set(EXPECTED_DATES)
        or any(replay[value] is not True for value in EXPECTED_DATES)
    ):
        raise ValueError("provider-free replay must pass on exactly 30 dates")
    gates = summary.get("gates")
    if (
        not isinstance(gates, Mapping)
        or set(gates) != GATE_KEYS
        or any(gates[key] is not True for key in GATE_KEYS)
    ):
        raise ValueError("historical source v0.4 gates must be real booleans true")


def _strict_request_budget(value: Mapping[str, object]) -> tuple[int, dict[str, int]]:
    if set(value) != {"schema_version", "total_attempts", "by_host"}:
        raise ValueError("provider request budget fields changed")
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
    ):
        raise ValueError("provider request budget schema changed")
    total = _strict_int(
        value.get("total_attempts"),
        label="provider total attempts",
        minimum=1,
    )
    if total > MAX_HTTP_ATTEMPTS:
        raise ValueError("provider request budget exceeded")
    by_host = value.get("by_host")
    if not isinstance(by_host, Mapping) or set(by_host) != set(ALLOWED_REQUEST_HOSTS):
        raise ValueError("provider request hosts must exactly match the allowlist")
    counts = {
        host: _strict_int(
            by_host[host],
            label=f"provider attempts for {host}",
            minimum=1,
        )
        for host in sorted(ALLOWED_REQUEST_HOSTS)
    }
    if sum(counts.values()) != total:
        raise ValueError("provider request host counts do not sum to total")
    return total, counts


def _workflow_provenance(
    *,
    repository: str,
    authorization_commit_sha: str,
    authorization_tree_sha: str,
    dispatcher_workflow_sha: str,
    dispatcher_workflow_ref: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    if repository != EXPECTED_REPOSITORY:
        raise ValueError("historical source repository mismatch")
    for label, value in (
        ("authorization commit", authorization_commit_sha),
        ("authorization tree", authorization_tree_sha),
        ("dispatcher workflow", dispatcher_workflow_sha),
    ):
        if not isinstance(value, str) or _LOWER_GIT_SHA.fullmatch(value) is None:
            raise ValueError(f"{label} must be a full lowercase Git SHA")
    if not isinstance(dispatcher_workflow_ref, str) or _WORKFLOW_REF.fullmatch(
        dispatcher_workflow_ref
    ) is None:
        raise ValueError("dispatcher workflow ref is invalid")
    if not isinstance(workflow_run_id, str) or _RUN_ID.fullmatch(
        workflow_run_id
    ) is None:
        raise ValueError("workflow run ID must be a canonical positive decimal string")
    if _strict_int(
        workflow_run_attempt,
        label="workflow run attempt",
        minimum=1,
    ) != 1:
        raise ValueError("historical source v0.4 is attempt 1 only")
    return {
        "repository": repository,
        "authorization_commit_sha": authorization_commit_sha,
        "authorization_tree_sha": authorization_tree_sha,
        "dispatcher_workflow_sha": dispatcher_workflow_sha,
        "dispatcher_workflow_ref": dispatcher_workflow_ref,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
    }


def build_acquisition_report_v04(
    *,
    authorization_id: str,
    authorization_content_sha256: str,
    source_checkpoint_binding: Mapping[str, object],
    source_summary: Mapping[str, object],
    request_budget: Mapping[str, object],
    retained_bytes: int,
    repository: str,
    authorization_commit_sha: str,
    authorization_tree_sha: str,
    dispatcher_workflow_sha: str,
    dispatcher_workflow_ref: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> dict[str, object]:
    """Build a strict report without defining or validating an authorization body."""

    if authorization_id != EXPECTED_AUTHORIZATION_ID:
        raise ValueError("authorization ID is not the frozen v0.4 child")
    if authorization_content_sha256 != _frozen_authorization_content_sha256():
        raise ValueError("authorization content hash is not the frozen v0.4 child")
    checkpoint_binding = validate_source_checkpoint_binding_v04(
        source_checkpoint_binding
    )
    validate_source_summary_v04(source_summary)
    total, by_host = _strict_request_budget(request_budget)
    retained = _strict_int(retained_bytes, label="retained bytes", minimum=1)
    if retained > MAX_RETAINED_BYTES:
        raise ValueError("historical source retained-byte ceiling exceeded")
    provenance = _workflow_provenance(
        repository=repository,
        authorization_commit_sha=authorization_commit_sha,
        authorization_tree_sha=authorization_tree_sha,
        dispatcher_workflow_sha=dispatcher_workflow_sha,
        dispatcher_workflow_ref=dispatcher_workflow_ref,
        workflow_run_id=workflow_run_id,
        workflow_run_attempt=workflow_run_attempt,
    )
    checkpoint_authorization = checkpoint_binding["authorization"]
    checkpoint_budget = checkpoint_binding["request_budget"]
    checkpoint_provenance = checkpoint_binding["provenance"]
    assert isinstance(checkpoint_authorization, Mapping)
    assert isinstance(checkpoint_budget, Mapping)
    assert isinstance(checkpoint_provenance, Mapping)
    if checkpoint_authorization != {
        "authorization_id": authorization_id,
        "authorization_content_sha256": authorization_content_sha256,
    }:
        raise ValueError("source checkpoint is bound to another authorization")
    if (
        checkpoint_budget.get("total_attempts") != total
        or checkpoint_budget.get("by_host") != by_host
    ):
        raise ValueError("source checkpoint request accounting differs from report")
    if dict(checkpoint_provenance) != provenance:
        raise ValueError("source checkpoint provenance differs from report")
    if checkpoint_binding.get("post_scanner_retained_file_bytes") != retained:
        raise ValueError("source checkpoint retained bytes differ from report")
    if (
        checkpoint_binding.get("post_scanner_tree_content_sha256")
        != source_summary.get("source_tree_content_sha256")
        or checkpoint_binding.get("post_scanner_file_count")
        != source_summary.get("source_file_count")
        or checkpoint_binding.get("post_scanner_retained_file_bytes")
        != source_summary.get("source_retained_file_bytes")
    ):
        raise ValueError("source checkpoint final tree differs from source summary")
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "authorization_id": authorization_id,
        "authorization_content_sha256": authorization_content_sha256,
        "selected_dates": list(EXPECTED_DATES),
        "source_checkpoint": checkpoint_binding,
        "source_summary": dict(source_summary),
        "request_budget": {
            "maximum_total_http_attempts": MAX_HTTP_ATTEMPTS,
            "observed_total_http_attempts": total,
            "observed_attempts_by_host": by_host,
        },
        "retention": {
            "maximum_retained_bytes": MAX_RETAINED_BYTES,
            "observed_retained_bytes": retained,
        },
        "workflow_provenance": provenance,
        "cost": {
            "incremental_provider_cost_usd": "0",
            "databento_called": False,
        },
        "causal_attestation": {
            "transcript_record_values_read": False,
            "ross_labels_or_outcomes_read": False,
            "account_or_order_endpoint_called": False,
            "order_submitted": False,
            "strategy_micro_or_account_policy_changed": False,
        },
        "source_acquisition_gate_passed": True,
        "next_gate": "provider_free_label_blind_scanner_and_micro_runtime_freeze",
    }
    report["content_sha256"] = _fingerprint(report)
    validate_acquisition_report_v04(report)
    return report


def validate_acquisition_report_v04(report: Mapping[str, object]) -> None:
    expected_keys = {
        "schema_version",
        "artifact_type",
        "authorization_id",
        "authorization_content_sha256",
        "selected_dates",
        "source_checkpoint",
        "source_summary",
        "request_budget",
        "retention",
        "workflow_provenance",
        "cost",
        "causal_attestation",
        "source_acquisition_gate_passed",
        "next_gate",
        "content_sha256",
    }
    if set(report) != expected_keys:
        raise ValueError("historical source v0.4 report fields changed")
    body = {key: value for key, value in report.items() if key != "content_sha256"}
    if report.get("content_sha256") != _fingerprint(body):
        raise ValueError("historical source v0.4 report hash mismatch")
    if type(report.get("schema_version")) is not int or report.get(
        "schema_version"
    ) != SCHEMA_VERSION or report.get(
        "artifact_type"
    ) != ARTIFACT_TYPE:
        raise ValueError("unsupported historical source v0.4 report")
    if report.get("authorization_id") != EXPECTED_AUTHORIZATION_ID:
        raise ValueError("historical source v0.4 authorization ID is invalid")
    if report.get(
        "authorization_content_sha256"
    ) != _frozen_authorization_content_sha256():
        raise ValueError("historical source v0.4 authorization hash changed")
    _exact_dates(report.get("selected_dates"), label="report")
    checkpoint = report.get("source_checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise ValueError("historical source v0.4 checkpoint binding is invalid")
    validated_checkpoint = validate_source_checkpoint_binding_v04(checkpoint)
    checkpoint_authorization = validated_checkpoint["authorization"]
    if checkpoint_authorization != {
        "authorization_id": report.get("authorization_id"),
        "authorization_content_sha256": report.get(
            "authorization_content_sha256"
        ),
    }:
        raise ValueError("historical source v0.4 checkpoint authorization differs")
    source_summary = report.get("source_summary")
    if not isinstance(source_summary, Mapping):
        raise ValueError("historical source v0.4 source summary is invalid")
    validate_source_summary_v04(source_summary)
    budget = report.get("request_budget")
    if (
        not isinstance(budget, Mapping)
        or set(budget)
        != {
            "maximum_total_http_attempts",
            "observed_total_http_attempts",
            "observed_attempts_by_host",
        }
        or type(budget.get("maximum_total_http_attempts")) is not int
        or budget.get("maximum_total_http_attempts") != MAX_HTTP_ATTEMPTS
    ):
        raise ValueError("historical source v0.4 request ceiling changed")
    _strict_request_budget(
        {
            "schema_version": 1,
            "total_attempts": budget.get("observed_total_http_attempts"),
            "by_host": budget.get("observed_attempts_by_host"),
        }
    )
    checkpoint_budget = validated_checkpoint["request_budget"]
    assert isinstance(checkpoint_budget, Mapping)
    if (
        checkpoint_budget.get("total_attempts")
        != budget.get("observed_total_http_attempts")
        or checkpoint_budget.get("by_host")
        != budget.get("observed_attempts_by_host")
    ):
        raise ValueError("historical source v0.4 checkpoint budget differs")
    retention = report.get("retention")
    if (
        not isinstance(retention, Mapping)
        or set(retention)
        != {"maximum_retained_bytes", "observed_retained_bytes"}
        or type(retention.get("maximum_retained_bytes")) is not int
        or retention.get("maximum_retained_bytes") != MAX_RETAINED_BYTES
    ):
        raise ValueError("historical source v0.4 retention ceiling changed")
    retained = _strict_int(
        retention.get("observed_retained_bytes"),
        label="retained bytes",
        minimum=1,
    )
    if retained > MAX_RETAINED_BYTES:
        raise ValueError("historical source v0.4 retained-byte ceiling exceeded")
    if validated_checkpoint.get("post_scanner_retained_file_bytes") != retained:
        raise ValueError("historical source v0.4 checkpoint retention differs")
    if (
        validated_checkpoint.get("post_scanner_tree_content_sha256")
        != source_summary.get("source_tree_content_sha256")
        or validated_checkpoint.get("post_scanner_file_count")
        != source_summary.get("source_file_count")
        or validated_checkpoint.get("post_scanner_retained_file_bytes")
        != source_summary.get("source_retained_file_bytes")
    ):
        raise ValueError("historical source v0.4 checkpoint tree differs")
    provenance = report.get("workflow_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("historical source v0.4 provenance is invalid")
    if set(provenance) != {
        "repository",
        "authorization_commit_sha",
        "authorization_tree_sha",
        "dispatcher_workflow_sha",
        "dispatcher_workflow_ref",
        "workflow_run_id",
        "workflow_run_attempt",
    }:
        raise ValueError("historical source v0.4 provenance fields changed")
    normalized_provenance = _workflow_provenance(**provenance)  # type: ignore[arg-type]
    if validated_checkpoint.get("provenance") != normalized_provenance:
        raise ValueError("historical source v0.4 checkpoint provenance differs")
    cost = report.get("cost")
    if (
        not isinstance(cost, Mapping)
        or set(cost) != {"incremental_provider_cost_usd", "databento_called"}
        or cost.get("incremental_provider_cost_usd") != "0"
        or cost.get("databento_called") is not False
    ):
        raise ValueError("historical source v0.4 cost boundary changed")
    attestation = report.get("causal_attestation")
    attestation_keys = {
        "transcript_record_values_read",
        "ross_labels_or_outcomes_read",
        "account_or_order_endpoint_called",
        "order_submitted",
        "strategy_micro_or_account_policy_changed",
    }
    if (
        not isinstance(attestation, Mapping)
        or set(attestation) != attestation_keys
        or any(attestation[key] is not False for key in attestation_keys)
    ):
        raise ValueError("historical source v0.4 causal boundary changed")
    if report.get("source_acquisition_gate_passed") is not True:
        raise ValueError("historical source v0.4 gate did not pass")
    if report.get("next_gate") != (
        "provider_free_label_blind_scanner_and_micro_runtime_freeze"
    ):
        raise ValueError("historical source v0.4 next gate changed")


def load_acquisition_report_v04(path: str | Path) -> dict[str, object]:
    """Strictly decode and validate a serialized completed report."""

    report = _load_json_object(Path(path))
    validate_acquisition_report_v04(report)
    return report


__all__ = [
    "ARTIFACT_TYPE",
    "AUXILIARY_MANIFEST_ROOTS",
    "DATE_HASH_KEYS",
    "DeepValidationAPIs",
    "EXPECTED_DATES",
    "GATE_KEYS",
    "MAX_CANDIDATES_PER_DATE_V04",
    "SOURCE_CHECKPOINT_BINDING_KEYS",
    "SOURCE_HASH_KEYS",
    "build_acquisition_report_v04",
    "expected_manifest_paths_v04",
    "expected_source_file_paths_v04",
    "load_acquisition_report_v04",
    "summarize_source_root_v04",
    "validate_acquisition_report_v04",
    "validate_source_checkpoint_binding_v04",
    "validate_source_summary_v04",
]
