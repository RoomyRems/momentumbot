"""Deterministic replay sidecar for causal scanner market inputs.

The sidecar persists the exact canonical byte stream already committed by the
scanner's ``reacquired_market_inputs`` source hash.  It contains no benchmark
label, trade, setup, portfolio state, or P&L.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from .causal_scanner_snapshot import (
    CAUSAL_SCANNER_SNAPSHOT_POLICY_ID,
    RANK_ACQUISITION_ASOF_RULE,
    RANK_ACQUISITION_PROVIDER,
    RANK_HISTORICAL_FEED,
    RANK_MINUTE_ADJUSTMENT,
    RANK_MINUTE_TIMEFRAME,
    RANK_PREVIOUS_CLOSE_ADJUSTMENT,
    RANK_PREVIOUS_CLOSE_TIMEFRAME,
    RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS,
    causal_scanner_snapshot_v0_1_manifest,
    encode_market_input_record,
    iter_market_input_records,
    market_inputs_fingerprint,
)
from .models import StrategyProfile


SCHEMA_VERSION = 1
ARTIFACT_ID = "causal-scanner-source-inputs-v0.1"
FORMAT_ID = "streamed-canonical-market-inputs-v1"
RECORD_FILE = "market-inputs.jsonl.gz"
MANIFEST_FILE = "manifest.json"

SOURCE_HASH_NAMES = (
    "identity_resolved_membership",
    "market_candidates",
    "market_discovery_manifest",
    "causal_float_records",
    "causal_float_manifest",
    "publication_timed_news_events",
    "publication_timed_news_statuses",
    "publication_timed_news_manifest",
    "reacquired_market_inputs",
)
RECORD_KIND_ORDER = (
    "contract",
    "membership",
    "previous_close",
    "rank_close_bar",
    "candidate_bar",
    "candidate_exact_rvol",
)
_LOWER_HEX = frozenset("0123456789abcdef")


def _json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _LOWER_HEX for character in value)
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_hashes(value: Mapping[str, str]) -> dict[str, str]:
    if set(value) != set(SOURCE_HASH_NAMES):
        raise ValueError("scanner source-input lineage names mismatch")
    output = {name: str(value[name]) for name in SOURCE_HASH_NAMES}
    if any(not _is_sha256(item) for item in output.values()):
        raise ValueError("scanner source-input lineage requires lowercase SHA-256")
    return output


def _candidate_symbols(
    values: Iterable[str], *, membership_symbols: Iterable[str]
) -> list[str]:
    candidates = sorted(str(value).strip().upper() for value in values)
    members = {str(value).strip().upper() for value in membership_symbols}
    if len(candidates) != len(set(candidates)) or any(not item for item in candidates):
        raise ValueError("scanner source-input candidate symbols must be unique")
    if not set(candidates).issubset(members):
        raise ValueError("scanner source-input candidate is absent from membership")
    return candidates


@dataclass(frozen=True)
class ScannerSourceInputs:
    trading_date: date
    membership_symbols: tuple[str, ...]
    candidate_symbols: tuple[str, ...]
    previous_close_by_symbol: dict[str, float | None]
    rank_raw_minute_bars_by_symbol: dict[str, pd.DataFrame]
    candidate_raw_minute_bars_by_symbol: dict[str, pd.DataFrame]
    candidate_exact_rvol_by_symbol: dict[str, pd.Series]
    source_hashes: dict[str, str]


def write_scanner_source_input_bundle(
    output_root: str | Path,
    *,
    trading_date: date,
    profile: StrategyProfile,
    membership_symbols: Iterable[str],
    candidate_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float],
    rank_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series],
    upstream_source_hashes: Mapping[str, str],
) -> dict[str, object]:
    """Persist one date's canonical source stream with deterministic gzip."""

    root = Path(output_root)
    members = sorted(str(value).strip().upper() for value in membership_symbols)
    candidates = _candidate_symbols(candidate_symbols, membership_symbols=members)
    if set(upstream_source_hashes) != set(SOURCE_HASH_NAMES[:-1]):
        raise ValueError("upstream scanner source-input lineage names mismatch")
    upstream = {name: str(upstream_source_hashes[name]) for name in SOURCE_HASH_NAMES[:-1]}
    if any(not _is_sha256(value) for value in upstream.values()):
        raise ValueError("upstream scanner source-input lineage requires lowercase SHA-256")

    root.mkdir(parents=True, exist_ok=False)
    record_path = root / RECORD_FILE

    logical_digest = hashlib.sha256()
    record_counts: Counter[str] = Counter()
    with record_path.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as compressed:
            for kind, value in iter_market_input_records(
                trading_date=trading_date,
                profile=profile,
                membership_symbols=members,
                previous_close_by_symbol=previous_close_by_symbol,
                rank_raw_minute_bars_by_symbol=rank_raw_minute_bars_by_symbol,
                candidate_raw_minute_bars_by_symbol=(
                    candidate_raw_minute_bars_by_symbol
                ),
                candidate_exact_rvol_by_symbol=candidate_exact_rvol_by_symbol,
            ):
                line = encode_market_input_record(kind, value)
                logical_digest.update(line)
                compressed.write(line)
                record_counts[kind] += 1

    logical_sha = logical_digest.hexdigest()
    source_hashes = {**upstream, "reacquired_market_inputs": logical_sha}
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "trading_date": trading_date.isoformat(),
        "format": FORMAT_ID,
        "scanner_policy_id": CAUSAL_SCANNER_SNAPSHOT_POLICY_ID,
        "scanner_policy_fingerprint": causal_scanner_snapshot_v0_1_manifest()[
            "fingerprint"
        ],
        "candidate_symbols": candidates,
        "source_hashes": source_hashes,
        "acquisition_basis": {
            "provider": RANK_ACQUISITION_PROVIDER,
            "feed": RANK_HISTORICAL_FEED,
            "previous_close_timeframe": RANK_PREVIOUS_CLOSE_TIMEFRAME,
            "previous_close_adjustment": RANK_PREVIOUS_CLOSE_ADJUSTMENT,
            "previous_close_lookback_calendar_days": (
                RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS
            ),
            "minute_timeframe": RANK_MINUTE_TIMEFRAME,
            "minute_adjustment": RANK_MINUTE_ADJUSTMENT,
            "asof_rule": RANK_ACQUISITION_ASOF_RULE,
        },
        "summary": {
            "membership_symbol_count": len(members),
            "candidate_symbol_count": len(candidates),
            "logical_record_count": sum(record_counts.values()),
            "record_counts": {
                kind: record_counts.get(kind, 0) for kind in RECORD_KIND_ORDER
            },
            "logical_records_sha256": logical_sha,
            "compressed_file_sha256": _file_sha256(record_path),
            "compressed_size_bytes": record_path.stat().st_size,
        },
        "knowledge_policy": {
            "uses_benchmark_labels": False,
            "uses_retrospective_trade_outcomes": False,
            "contains_trades_setups_portfolio_or_pnl": False,
            "decision_time_market_inputs_only": True,
        },
        "replay_boundary": {
            "raw_provider_responses_persisted": False,
            "canonical_runtime_inputs_persisted": True,
            "provider_independent_scanner_feature_replay_supported": True,
            "provider_independent_upstream_membership_market_float_news_replay_supported": False,
        },
        "files": {"canonical_market_inputs": RECORD_FILE},
    }
    manifest["content_sha256"] = _json_fingerprint(manifest)
    validate_scanner_source_input_manifest(manifest, root=root)
    (root / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_scanner_source_input_manifest(
    manifest: Mapping[str, object], *, root: str | Path | None = None
) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported scanner source-input schema")
    if manifest.get("artifact_id") != ARTIFACT_ID:
        raise ValueError("unexpected scanner source-input artifact ID")
    if manifest.get("format") != FORMAT_ID:
        raise ValueError("unexpected scanner source-input format")
    date.fromisoformat(str(manifest.get("trading_date") or ""))
    if manifest.get("scanner_policy_id") != CAUSAL_SCANNER_SNAPSHOT_POLICY_ID:
        raise ValueError("scanner source-input policy ID mismatch")
    if manifest.get("scanner_policy_fingerprint") != (
        causal_scanner_snapshot_v0_1_manifest()["fingerprint"]
    ):
        raise ValueError("scanner source-input policy fingerprint mismatch")
    candidates = manifest.get("candidate_symbols")
    if (
        not isinstance(candidates, list)
        or any(
            not isinstance(value, str) or not value or value != value.upper()
            for value in candidates
        )
        or candidates != sorted(set(candidates))
    ):
        raise ValueError("scanner source-input candidate symbols are not canonical")
    hashes = manifest.get("source_hashes")
    if not isinstance(hashes, Mapping):
        raise ValueError("scanner source-input source hashes are missing")
    source_hashes = _source_hashes(hashes)  # type: ignore[arg-type]
    summary = manifest.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("scanner source-input summary is missing")
    if summary.get("logical_records_sha256") != source_hashes[
        "reacquired_market_inputs"
    ]:
        raise ValueError("scanner source-input logical hash disagrees with lineage")
    for field in ("logical_records_sha256", "compressed_file_sha256"):
        if not _is_sha256(summary.get(field)):
            raise ValueError(f"scanner source-input {field} is invalid")
    counts = summary.get("record_counts")
    if not isinstance(counts, Mapping) or set(counts) != set(RECORD_KIND_ORDER):
        raise ValueError("scanner source-input record counts are not canonical")
    if any(not isinstance(counts[kind], int) or counts[kind] < 0 for kind in counts):
        raise ValueError("scanner source-input record count is invalid")
    if summary.get("logical_record_count") != sum(int(value) for value in counts.values()):
        raise ValueError("scanner source-input total record count mismatch")
    if counts.get("contract") != 1:
        raise ValueError("scanner source-input requires one contract record")
    if counts.get("membership") != summary.get("membership_symbol_count"):
        raise ValueError("scanner source-input membership record count mismatch")
    if counts.get("previous_close") != summary.get("membership_symbol_count"):
        raise ValueError("scanner source-input previous-close record count mismatch")
    if len(candidates) != summary.get("candidate_symbol_count"):
        raise ValueError("scanner source-input candidate count mismatch")
    expected_acquisition = {
        "provider": RANK_ACQUISITION_PROVIDER,
        "feed": RANK_HISTORICAL_FEED,
        "previous_close_timeframe": RANK_PREVIOUS_CLOSE_TIMEFRAME,
        "previous_close_adjustment": RANK_PREVIOUS_CLOSE_ADJUSTMENT,
        "previous_close_lookback_calendar_days": (
            RANK_PRIOR_CLOSE_LOOKBACK_CALENDAR_DAYS
        ),
        "minute_timeframe": RANK_MINUTE_TIMEFRAME,
        "minute_adjustment": RANK_MINUTE_ADJUSTMENT,
        "asof_rule": RANK_ACQUISITION_ASOF_RULE,
    }
    if manifest.get("acquisition_basis") != expected_acquisition:
        raise ValueError("scanner source-input acquisition basis is misstated")
    expected_knowledge = {
        "uses_benchmark_labels": False,
        "uses_retrospective_trade_outcomes": False,
        "contains_trades_setups_portfolio_or_pnl": False,
        "decision_time_market_inputs_only": True,
    }
    if manifest.get("knowledge_policy") != expected_knowledge:
        raise ValueError("scanner source-input knowledge boundary is misstated")
    if manifest.get("replay_boundary") != {
        "raw_provider_responses_persisted": False,
        "canonical_runtime_inputs_persisted": True,
        "provider_independent_scanner_feature_replay_supported": True,
        "provider_independent_upstream_membership_market_float_news_replay_supported": False,
    }:
        raise ValueError("scanner source-input replay boundary is misstated")
    if manifest.get("files") != {"canonical_market_inputs": RECORD_FILE}:
        raise ValueError("scanner source-input file map is invalid")
    claimed = manifest.get("content_sha256")
    expected = _json_fingerprint(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    )
    if claimed != expected:
        raise ValueError("scanner source-input manifest content hash mismatch")
    if root is not None:
        record_path = Path(root) / RECORD_FILE
        if not record_path.is_file():
            raise ValueError("scanner source-input compressed file is missing")
        if _file_sha256(record_path) != summary.get("compressed_file_sha256"):
            raise ValueError("scanner source-input compressed file hash mismatch")
        if record_path.stat().st_size != summary.get("compressed_size_bytes"):
            raise ValueError("scanner source-input compressed file size mismatch")


def _decode_number(value: object) -> float | None:
    if value is None:
        return None
    if value == "positive_infinity":
        return math.inf
    if value == "negative_infinity":
        return -math.inf
    if isinstance(value, bool):
        raise ValueError("scanner source-input numeric value is boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("scanner source-input numeric value is invalid") from exc
    if math.isnan(number):
        raise ValueError("scanner source-input numeric value is NaN")
    return number


def _frame(
    rows: list[tuple[pd.Timestamp, dict[str, float | None]]],
    *,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(columns))
    index = pd.DatetimeIndex([timestamp for timestamp, _ in rows])
    return pd.DataFrame(
        [{column: values[column] for column in columns} for _, values in rows],
        index=index,
    )


def load_scanner_source_input_bundle(
    root: str | Path, *, profile: StrategyProfile
) -> tuple[ScannerSourceInputs, dict[str, object]]:
    path = Path(root)
    manifest = json.loads((path / MANIFEST_FILE).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("scanner source-input manifest root must be an object")
    validate_scanner_source_input_manifest(manifest, root=path)

    membership: list[str] = []
    previous_close: dict[str, float | None] = {}
    rank_rows: dict[
        str, list[tuple[pd.Timestamp, dict[str, float | None]]]
    ] = defaultdict(list)
    candidate_rows: dict[
        str, list[tuple[pd.Timestamp, dict[str, float | None]]]
    ] = defaultdict(list)
    rvol_rows: dict[str, list[tuple[pd.Timestamp, float | None]]] = defaultdict(list)
    observed_counts: Counter[str] = Counter()
    digest = hashlib.sha256()
    prior_kind_index = -1

    with gzip.open(path / RECORD_FILE, "rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            if not raw_line.endswith(b"\n") or b"\t" not in raw_line:
                raise ValueError("scanner source-input record framing is invalid")
            kind_bytes, encoded = raw_line[:-1].split(b"\t", 1)
            try:
                kind = kind_bytes.decode("ascii")
                value = json.loads(encoded)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("scanner source-input record is invalid") from exc
            if kind not in RECORD_KIND_ORDER or not isinstance(value, dict):
                raise ValueError("scanner source-input record kind or value is invalid")
            kind_index = RECORD_KIND_ORDER.index(kind)
            if kind_index < prior_kind_index:
                raise ValueError("scanner source-input record kinds are out of order")
            prior_kind_index = kind_index
            if encode_market_input_record(kind, value) != raw_line:
                raise ValueError("scanner source-input record is not canonical")
            observed_counts[kind] += 1

            if kind == "contract":
                if value != {
                    "artifact": CAUSAL_SCANNER_SNAPSHOT_POLICY_ID,
                    "trading_date": manifest["trading_date"],
                    "format": FORMAT_ID,
                }:
                    raise ValueError("scanner source-input contract record mismatch")
            elif kind == "membership":
                membership.append(str(value.get("symbol") or ""))
            elif kind == "previous_close":
                symbol = str(value.get("symbol") or "")
                if symbol in previous_close:
                    raise ValueError("scanner source-input repeats previous close")
                previous_close[symbol] = _decode_number(
                    value.get("split_adjusted_previous_close")
                )
            elif kind in {"rank_close_bar", "candidate_bar"}:
                symbol = str(value.get("symbol") or "")
                timestamp = pd.Timestamp(value.get("bar_started_at"))
                values = {"close": _decode_number(value.get("close"))}
                target = rank_rows if kind == "rank_close_bar" else candidate_rows
                if kind == "candidate_bar":
                    values["volume"] = _decode_number(value.get("volume"))
                target[symbol].append((timestamp, values))
            else:
                symbol = str(value.get("symbol") or "")
                timestamp = pd.Timestamp(value.get("bar_started_at"))
                rvol_rows[symbol].append(
                    (timestamp, _decode_number(value.get("exact_same_time_rvol")))
                )

    summary = manifest["summary"]
    if digest.hexdigest() != summary["logical_records_sha256"]:
        raise ValueError("scanner source-input logical stream hash mismatch")
    if {kind: observed_counts.get(kind, 0) for kind in RECORD_KIND_ORDER} != summary[
        "record_counts"
    ]:
        raise ValueError("scanner source-input observed record counts mismatch")
    if membership != sorted(set(membership)) or any(not symbol for symbol in membership):
        raise ValueError("scanner source-input membership order is invalid")
    if list(previous_close) != membership:
        raise ValueError("scanner source-input previous closes do not match membership")
    candidates = tuple(str(value) for value in manifest["candidate_symbols"])
    if not set(candidates).issubset(membership):
        raise ValueError("scanner source-input candidate is absent from membership")

    rank_frames = {
        symbol: _frame(rows, columns=("close",))
        for symbol, rows in rank_rows.items()
    }
    candidate_frames = {
        symbol: _frame(candidate_rows.get(symbol, []), columns=("close", "volume"))
        for symbol in candidates
    }
    candidate_rvol = {
        symbol: pd.Series(
            [value for _, value in rvol_rows.get(symbol, [])],
            index=pd.DatetimeIndex(
                [timestamp for timestamp, _ in rvol_rows.get(symbol, [])]
            ),
            dtype="float64",
        )
        for symbol in candidates
    }
    for symbol in candidates:
        rank_frame = rank_frames.get(symbol, pd.DataFrame(columns=["close"]))
        candidate_frame = candidate_frames[symbol]
        if not rank_frame.index.equals(candidate_frame.index):
            raise ValueError(
                "scanner source-input candidate and rank timestamps disagree"
            )
        rank_close = pd.to_numeric(rank_frame.get("close"), errors="coerce")
        candidate_close = pd.to_numeric(
            candidate_frame.get("close"), errors="coerce"
        )
        if not rank_close.equals(candidate_close):
            raise ValueError(
                "scanner source-input candidate and rank closes disagree"
            )
        rank_frames[symbol] = candidate_frame
    trading_date = date.fromisoformat(str(manifest["trading_date"]))
    logical_sha = market_inputs_fingerprint(
        trading_date=trading_date,
        profile=profile,
        membership_symbols=membership,
        previous_close_by_symbol=previous_close,  # type: ignore[arg-type]
        rank_raw_minute_bars_by_symbol=rank_frames,
        candidate_raw_minute_bars_by_symbol=candidate_frames,
        candidate_exact_rvol_by_symbol=candidate_rvol,
    )
    if logical_sha != summary["logical_records_sha256"]:
        raise ValueError("scanner source-input reconstruction changes logical hash")
    inputs = ScannerSourceInputs(
        trading_date=trading_date,
        membership_symbols=tuple(membership),
        candidate_symbols=candidates,
        previous_close_by_symbol=previous_close,
        rank_raw_minute_bars_by_symbol=rank_frames,
        candidate_raw_minute_bars_by_symbol=candidate_frames,
        candidate_exact_rvol_by_symbol=candidate_rvol,
        source_hashes=_source_hashes(manifest["source_hashes"]),  # type: ignore[arg-type]
    )
    return inputs, manifest


def build_scanner_source_input_root_manifest(
    *,
    date_manifests: list[dict[str, object]],
    source_bundle_hashes: Mapping[str, str],
) -> dict[str, object]:
    dates = [str(row.get("trading_date") or "") for row in date_manifests]
    if not dates or dates != sorted(set(dates)):
        raise ValueError("scanner source-input root dates must be unique and ordered")
    if any(row.get("artifact_id") != ARTIFACT_ID for row in date_manifests):
        raise ValueError("scanner source-input root contains unexpected date artifact")
    if any(not _is_sha256(value) for value in source_bundle_hashes.values()):
        raise ValueError("scanner source-input root source hashes are invalid")
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "dates": dates,
        "scanner_policy_id": CAUSAL_SCANNER_SNAPSHOT_POLICY_ID,
        "scanner_policy_fingerprint": causal_scanner_snapshot_v0_1_manifest()[
            "fingerprint"
        ],
        "source_bundle_hashes": dict(sorted(source_bundle_hashes.items())),
        "date_manifests": date_manifests,
        "replay_boundary": {
            "canonical_runtime_inputs_persisted": True,
            "provider_independent_scanner_feature_replay_supported": True,
            "upstream_artifacts_still_required": True,
            "policy_promotion_eligible": False,
        },
    }
    manifest["content_sha256"] = _json_fingerprint(manifest)
    return manifest
