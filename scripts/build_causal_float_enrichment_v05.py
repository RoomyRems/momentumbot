"""Candidate-contained float normalization repair for sealed recovery v0.5.

The consumed v0.4 implementation remains byte-for-byte immutable.  This child
adapter invokes that implementation while replacing only its candidate daily-
basis download boundary.  A provider payload that raises ``TypeError`` or
``ValueError`` while being converted to a normalized DataFrame becomes an
empty measure pair for that one candidate.  The frozen float policy already
maps an absent/malformed measure pair to ``unknown_fail_closed``.

Transport, request-budget, pagination, authorization, and artifact-integrity
errors are deliberately not caught.  Sanitized diagnostics retain only the
date, symbol, stage, and exception class; exception messages and raw provider
responses are never persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
import os
from pathlib import Path
import sys
from typing import Callable

import pandas as pd

from momentumbot.research.sealed_historical_availability import SELECTED_DATES
from momentumbot.historical_float_v04 import (
    TargetBasisObservation,
    validate_selected_float_evidence_v02,
    validate_target_basis_observation,
    validate_target_session_pair,
)
if __package__:
    from scripts import build_causal_float_enrichment_v04 as parent
else:  # Exact ``python scripts/...`` workflow invocation.
    import build_causal_float_enrichment_v04 as parent


DIAGNOSTIC_ARTIFACT_ID = "causal-float-normalization-rejections-v0.1"
DIAGNOSTIC_SCHEMA_VERSION = 1
DIAGNOSTIC_STAGE = "measure_basis_provider_data_normalization"
DIAGNOSTIC_DISPOSITION = "unknown_fail_closed_missing_measure_pair"
EXPECTED_DATES = frozenset(SELECTED_DATES)
MAX_CANDIDATE_REJECTIONS = 946


def _canonical_fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def build_sanitized_diagnostics(
    rejections: list[dict[str, str]],
) -> dict[str, object]:
    rows = sorted(
        rejections,
        key=lambda row: (
            row["trading_date"],
            row["symbol"],
            row["stage"],
            row["exception_class"],
        ),
    )
    payload: dict[str, object] = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "artifact_id": DIAGNOSTIC_ARTIFACT_ID,
        "candidate_rejection_count": len(rows),
        "candidate_rejections": rows,
        "causal_boundary": {
            "candidate_scope_only": True,
            "exception_messages_persisted": False,
            "raw_provider_http_responses_persisted": False,
            "strategy_thresholds_changed": False,
            "transcript_or_label_values_read": False,
        },
    }
    payload["content_sha256"] = _canonical_fingerprint(payload)
    validate_sanitized_diagnostics(payload)
    return payload


def _candidate_identity(*, trading_date: date, symbol: object) -> tuple[str, str]:
    rendered_symbol = str(symbol)
    if not rendered_symbol:
        raise ValueError("float candidate symbol is required")
    if trading_date.isoformat() not in EXPECTED_DATES:
        raise ValueError("float candidate date escaped the frozen panel")
    return trading_date.isoformat(), rendered_symbol


def _record_rejection_once(
    *,
    trading_date: date,
    symbol: object,
    exception: BaseException,
    rejections: list[dict[str, str]],
    failed_candidates: set[tuple[str, str]],
) -> None:
    identity = _candidate_identity(trading_date=trading_date, symbol=symbol)
    if identity in failed_candidates:
        return
    failed_candidates.add(identity)
    rejections.append(
        {
            "trading_date": identity[0],
            "symbol": identity[1],
            "stage": DIAGNOSTIC_STAGE,
            "exception_class": type(exception).__name__,
            "disposition": DIAGNOSTIC_DISPOSITION,
        }
    )


def validate_sanitized_diagnostics(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "artifact_id",
        "candidate_rejection_count",
        "candidate_rejections",
        "causal_boundary",
        "content_sha256",
    }:
        raise ValueError("float normalization diagnostics fields are invalid")
    claimed = payload.get("content_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    if claimed != _canonical_fingerprint(unsigned):
        raise ValueError("float normalization diagnostics hash mismatch")
    if (
        payload.get("schema_version") != DIAGNOSTIC_SCHEMA_VERSION
        or payload.get("artifact_id") != DIAGNOSTIC_ARTIFACT_ID
    ):
        raise ValueError("unsupported float normalization diagnostics")
    rows = payload.get("candidate_rejections")
    count = payload.get("candidate_rejection_count")
    if not isinstance(rows, list) or isinstance(count, bool) or count != len(rows):
        raise ValueError("float normalization diagnostic count is invalid")
    expected_keys = {
        "trading_date",
        "symbol",
        "stage",
        "exception_class",
        "disposition",
    }
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if count > MAX_CANDIDATE_REJECTIONS:
        raise ValueError("float normalization diagnostic count exceeds candidate census")
    for row in rows:
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise ValueError("float normalization diagnostic row is invalid")
        rendered = {key: str(row[key]) for key in expected_keys}
        date.fromisoformat(rendered["trading_date"])
        identity = (rendered["trading_date"], rendered["symbol"])
        if (
            rendered["trading_date"] not in EXPECTED_DATES
            or not rendered["symbol"]
            or rendered["stage"] != DIAGNOSTIC_STAGE
            or rendered["exception_class"] not in {"TypeError", "ValueError"}
            or rendered["disposition"] != DIAGNOSTIC_DISPOSITION
        ):
            raise ValueError("float normalization diagnostic row changed")
        if identity in seen:
            raise ValueError("float normalization diagnostics repeat a candidate")
        seen.add(identity)
        normalized.append(rendered)
    if rows != sorted(
        normalized,
        key=lambda row: (
            row["trading_date"],
            row["symbol"],
            row["stage"],
            row["exception_class"],
        ),
    ):
        raise ValueError("float normalization diagnostics are not canonical")
    if payload.get("causal_boundary") != {
        "candidate_scope_only": True,
        "exception_messages_persisted": False,
        "raw_provider_http_responses_persisted": False,
        "strategy_thresholds_changed": False,
        "transcript_or_label_values_read": False,
    }:
        raise ValueError("float normalization diagnostic boundary changed")
    return payload


def download_basis_candidate_fail_closed(
    client: object,
    symbol: str,
    requested_dates: list[date],
    *,
    trading_date: date,
    rejections: list[dict[str, str]],
    failed_candidates: set[tuple[str, str]] | None = None,
    delegate: Callable[..., tuple[pd.DataFrame, pd.DataFrame]] = parent._download_basis,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Contain only provider-data conversion errors to one float candidate."""

    try:
        return delegate(
            client,
            symbol,
            requested_dates,
            trading_date=trading_date,
        )
    except (TypeError, ValueError) as exc:
        _record_rejection_once(
            trading_date=trading_date,
            symbol=symbol,
            exception=exc,
            rejections=rejections,
            failed_candidates=(
                failed_candidates if failed_candidates is not None else set()
            ),
        )
        return pd.DataFrame(), pd.DataFrame()


def observe_basis_candidate_fail_closed(
    raw: pd.DataFrame,
    split: pd.DataFrame,
    requested: date,
    *,
    target_pair: object,
    trading_date: date,
    rejections: list[dict[str, str]],
    failed_candidates: set[tuple[str, str]],
    delegate: Callable[..., TargetBasisObservation] = parent.observe_target_basis,
) -> TargetBasisObservation:
    """Contain provider-frame normalization errors after source validation."""

    # These are recovered source/artifact invariants, not provider-frame data.
    # They deliberately execute outside the contained exception boundary.
    validate_target_session_pair(target_pair)  # type: ignore[arg-type]
    symbol = getattr(target_pair, "symbol", "")
    target_date = date.fromisoformat(str(getattr(target_pair, "target_date", "")))
    if target_date != trading_date:
        raise ValueError("float target-date lineage changed")
    identity = _candidate_identity(trading_date=trading_date, symbol=symbol)
    if identity in failed_candidates:
        return delegate(
            pd.DataFrame(),
            pd.DataFrame(),
            min(requested, trading_date),
            target_pair=target_pair,
        )
    if requested > trading_date:
        error = ValueError("provider measure date follows target")
        _record_rejection_once(
            trading_date=trading_date,
            symbol=symbol,
            exception=error,
            rejections=rejections,
            failed_candidates=failed_candidates,
        )
        return delegate(
            pd.DataFrame(),
            pd.DataFrame(),
            trading_date,
            target_pair=target_pair,
        )
    try:
        return delegate(raw, split, requested, target_pair=target_pair)
    except (TypeError, ValueError) as exc:
        _record_rejection_once(
            trading_date=trading_date,
            symbol=symbol,
            exception=exc,
            rejections=rejections,
            failed_candidates=failed_candidates,
        )
        return delegate(
            pd.DataFrame(),
            pd.DataFrame(),
            requested,
            target_pair=target_pair,
        )


def _unknown_selected(
    selected: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    return {
        "symbol": candidate["symbol"],
        "cik": str(selected.get("cik") or candidate.get("selected_cik") or ""),
        "first_market_qualified_bar_started_at": candidate[
            "first_market_qualified_bar_started_at"
        ],
        "first_market_qualified_at": candidate["first_market_qualified_at"],
        "public_float": None,
        "anchor_outstanding": None,
        "current_outstanding": None,
    }


def build_float_record_candidate_fail_closed(
    selected: dict[str, object],
    observations: dict[str, TargetBasisObservation],
    *,
    candidate: dict[str, object],
    target_date: date,
    target_basis_content_sha256: str,
    sec_status: str,
    sec_provider_error: str | None = None,
    rejections: list[dict[str, str]],
    failed_candidates: set[tuple[str, str]],
    delegate: Callable[..., dict[str, object]] = parent.build_causal_float_record,
) -> dict[str, object]:
    """Make a provider-derived normalization rejection unknown and fail closed."""

    symbol = candidate.get("symbol")
    identity = _candidate_identity(trading_date=target_date, symbol=symbol)
    call = {
        "candidate": candidate,
        "target_date": target_date,
        "target_basis_content_sha256": target_basis_content_sha256,
        "sec_status": sec_status,
        "sec_provider_error": sec_provider_error,
    }
    if identity in failed_candidates:
        return delegate(_unknown_selected(selected, candidate), {}, **call)
    try:
        validate_selected_float_evidence_v02(selected)
        for observation in observations.values():
            validate_target_basis_observation(observation)
    except (TypeError, ValueError) as exc:
        _record_rejection_once(
            trading_date=target_date,
            symbol=symbol,
            exception=exc,
            rejections=rejections,
            failed_candidates=failed_candidates,
        )
        # The second call uses only provider-free candidate identity/timestamps
        # and no provider-derived float disclosure or daily basis.  If that
        # still fails, the source/artifact error remains fatal.
        return delegate(_unknown_selected(selected, candidate), {}, **call)
    # With provider-derived evidence validated, any remaining exception is a
    # deterministic implementation/source failure and must abort the run.
    return delegate(selected, observations, **call)


def _diagnostic_path(value: Path, *, census_root: Path) -> Path:
    if value.name != "float-normalization-rejections.json":
        raise ValueError("float diagnostic output must use the frozen filename")
    if ".." in value.parts:
        raise ValueError("float diagnostic output may not traverse parents")
    absolute = Path(os.path.abspath(value))
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise ValueError("float diagnostic output path contains a symlink")
    root = census_root.resolve(strict=True)
    if absolute == root or absolute.is_relative_to(root):
        raise ValueError("float diagnostic output must stay outside the source tree")
    if absolute.exists():
        raise FileExistsError("float diagnostic output already exists")
    if not absolute.parent.is_dir() or absolute.parent.is_symlink():
        raise ValueError("float diagnostic output parent is invalid")
    return absolute


def _write_diagnostic_once(path: Path, payload: dict[str, object]) -> None:
    flags = os.O_CLOEXEC | os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    adapter = argparse.ArgumentParser(add_help=False)
    adapter.add_argument(
        "--sanitized-normalization-diagnostics",
        type=Path,
        required=True,
    )
    adapter_args, parent_arguments = adapter.parse_known_args(arguments)
    roots = argparse.ArgumentParser(add_help=False)
    roots.add_argument("--census-root", type=Path, required=True)
    root_args, _ = roots.parse_known_args(parent_arguments)
    diagnostic_path = _diagnostic_path(
        adapter_args.sanitized_normalization_diagnostics,
        census_root=root_args.census_root,
    )

    rejections: list[dict[str, str]] = []
    failed_candidates: set[tuple[str, str]] = set()
    original_download = parent._download_basis
    original_observe = parent.observe_target_basis
    original_build = parent.build_causal_float_record

    def contained_download(
        client: object,
        symbol: str,
        requested_dates: list[date],
        *,
        trading_date: date,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        return download_basis_candidate_fail_closed(
            client,
            symbol,
            requested_dates,
            trading_date=trading_date,
            rejections=rejections,
            failed_candidates=failed_candidates,
            delegate=original_download,
        )

    def contained_observe(
        raw: pd.DataFrame,
        split: pd.DataFrame,
        requested: date,
        *,
        target_pair: object,
    ) -> TargetBasisObservation:
        target_date = date.fromisoformat(str(getattr(target_pair, "target_date", "")))
        return observe_basis_candidate_fail_closed(
            raw,
            split,
            requested,
            target_pair=target_pair,
            trading_date=target_date,
            rejections=rejections,
            failed_candidates=failed_candidates,
            delegate=original_observe,
        )

    def contained_build(
        selected: dict[str, object],
        observations: dict[str, TargetBasisObservation],
        *,
        candidate: dict[str, object],
        target_date: date,
        target_basis_content_sha256: str,
        sec_status: str,
        sec_provider_error: str | None = None,
    ) -> dict[str, object]:
        return build_float_record_candidate_fail_closed(
            selected,
            observations,
            candidate=candidate,
            target_date=target_date,
            target_basis_content_sha256=target_basis_content_sha256,
            sec_status=sec_status,
            sec_provider_error=sec_provider_error,
            rejections=rejections,
            failed_candidates=failed_candidates,
            delegate=original_build,
        )

    parent._download_basis = contained_download
    parent.observe_target_basis = contained_observe
    parent.build_causal_float_record = contained_build
    try:
        result = parent.main(parent_arguments)
    finally:
        parent._download_basis = original_download
        parent.observe_target_basis = original_observe
        parent.build_causal_float_record = original_build
        payload = build_sanitized_diagnostics(rejections)
        _write_diagnostic_once(diagnostic_path, payload)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
