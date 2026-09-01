"""Canonical provider-free source tape for scanner snapshot v0.3."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable, Iterator, Mapping

import pandas as pd

from .causal_scanner_snapshot_v03 import (
    CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
    CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID,
    causal_scanner_snapshot_v0_3_manifest,
)
from .models import StrategyProfile


SCHEMA_VERSION = 2
ARTIFACT_ID = "causal-scanner-source-inputs-v0.2"
FORMAT_ID = "streamed-canonical-market-inputs-v2"
RECORD_FILE = "market-inputs.jsonl.gz"
MANIFEST_FILE = "manifest.json"
RECORD_KIND_ORDER = (
    "contract",
    "membership",
    "previous_close",
    "rank_split_close_bar",
    "candidate_raw_bar",
    "candidate_exact_rvol",
)
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
_LOWER_HEX = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class ScannerSourceInputs:
    trading_date: date
    membership_symbols: tuple[str, ...]
    candidate_symbols: tuple[str, ...]
    previous_close_by_symbol: dict[str, float | None]
    rank_split_minute_bars_by_symbol: dict[str, pd.DataFrame]
    candidate_raw_minute_bars_by_symbol: dict[str, pd.DataFrame]
    candidate_exact_rvol_by_symbol: dict[str, pd.Series]
    source_hashes: dict[str, str]

    @property
    def rank_raw_minute_bars_by_symbol(self) -> dict[str, pd.DataFrame]:
        """Compatibility name; values are explicitly split-adjusted in v0.2."""

        return self.rank_split_minute_bars_by_symbol


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
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


def _canonical_number(value: object, *, finite: bool = False) -> float | str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        raise ValueError("canonical scanner numeric value is boolean")
    number = float(value)
    if math.isnan(number):
        return None
    if math.isinf(number):
        if finite:
            raise ValueError("canonical scanner numeric value must be finite")
        return "positive_infinity" if number > 0 else "negative_infinity"
    return number


def _decode_number(value: object, *, finite: bool = False) -> float | None:
    if value is None:
        return None
    if value == "positive_infinity":
        if finite:
            raise ValueError("canonical scanner numeric value must be finite")
        return math.inf
    if value == "negative_infinity":
        if finite:
            raise ValueError("canonical scanner numeric value must be finite")
        return -math.inf
    if isinstance(value, bool):
        raise ValueError("canonical scanner numeric value is boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("canonical scanner numeric value is invalid") from error
    if math.isnan(number) or (finite and not math.isfinite(number)):
        raise ValueError("canonical scanner numeric value is invalid")
    return number


def _positive(value: object, *, label: str) -> float:
    number = _decode_number(value, finite=True)
    if number is None or number <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _source_hashes(values: Mapping[str, str]) -> dict[str, str]:
    if set(values) != set(SOURCE_HASH_NAMES):
        raise ValueError("scanner source-input lineage names mismatch")
    output = {name: str(values[name]) for name in SOURCE_HASH_NAMES}
    if any(not _is_sha256(value) for value in output.values()):
        raise ValueError("scanner source-input lineage requires lowercase SHA-256")
    return output


def _symbols(values: Iterable[str], *, label: str) -> list[str]:
    output = [str(value).strip().upper() for value in values]
    if not output or any(not value for value in output):
        raise ValueError(f"{label} must be nonblank")
    if len(output) != len(set(output)):
        raise ValueError(f"{label} repeat a symbol")
    return sorted(output)


def _validate_frame(frame: pd.DataFrame, *, label: str, columns: tuple[str, ...]) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(f"{label} must be a DataFrame")
    if set(frame.columns) != set(columns):
        raise ValueError(f"{label} fields are invalid")
    if frame.empty:
        return
    if frame.index.tz is None or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"{label} timestamps are invalid")


def _record_line(kind: str, value: Mapping[str, object]) -> bytes:
    if kind not in RECORD_KIND_ORDER:
        raise ValueError("unsupported canonical scanner record kind")
    encoded = json.dumps(
        dict(value),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return kind.encode("ascii") + b"\t" + encoded + b"\n"


def iter_market_input_records(
    *,
    trading_date: date,
    membership_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float | None],
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series],
) -> Iterator[tuple[str, dict[str, object]]]:
    members = _symbols(membership_symbols, label="membership symbols")
    member_set = set(members)
    for label, mapping in (
        ("previous closes", previous_close_by_symbol),
        ("split rank bars", rank_split_minute_bars_by_symbol),
        ("raw candidate bars", candidate_raw_minute_bars_by_symbol),
        ("candidate RVOL", candidate_exact_rvol_by_symbol),
    ):
        if set(mapping) - member_set:
            raise ValueError(f"{label} contain nonmembership symbols")
    candidates = sorted(candidate_raw_minute_bars_by_symbol)
    if set(candidate_exact_rvol_by_symbol) != set(candidates):
        raise ValueError("candidate raw-bar and RVOL symbols disagree")
    yield "contract", {
        "artifact": CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
        "trading_date": trading_date.isoformat(),
        "format": FORMAT_ID,
        "price_and_volume_adjustment": "raw",
        "gain_and_rank_adjustment": "split",
    }
    for symbol in members:
        yield "membership", {"symbol": symbol}
    for symbol in members:
        value = previous_close_by_symbol.get(symbol)
        encoded = None if value is None else _positive(value, label=f"previous close for {symbol}")
        yield "previous_close", {
            "symbol": symbol,
            "split_adjusted_previous_close": encoded,
        }
    for symbol in sorted(rank_split_minute_bars_by_symbol):
        frame = rank_split_minute_bars_by_symbol[symbol]
        _validate_frame(frame, label=f"split rank bars for {symbol}", columns=("close",))
        for timestamp, row in frame.iterrows():
            yield "rank_split_close_bar", {
                "symbol": symbol,
                "bar_started_at": timestamp.isoformat(),
                "split_adjusted_close": _positive(row["close"], label="split rank close"),
            }
    for symbol in candidates:
        frame = candidate_raw_minute_bars_by_symbol[symbol]
        _validate_frame(frame, label=f"raw candidate bars for {symbol}", columns=("close", "volume"))
        split = rank_split_minute_bars_by_symbol.get(symbol)
        if split is None or not split.index.equals(frame.index):
            raise ValueError(f"raw/split candidate timestamp coverage mismatch for {symbol}")
        for timestamp, row in frame.iterrows():
            volume = _decode_number(row["volume"], finite=True)
            if volume is None or volume < 0:
                raise ValueError("raw candidate volume must be finite and nonnegative")
            yield "candidate_raw_bar", {
                "symbol": symbol,
                "bar_started_at": timestamp.isoformat(),
                "raw_close": _positive(row["close"], label="raw candidate close"),
                "raw_volume": volume,
            }
    for symbol in candidates:
        series = candidate_exact_rvol_by_symbol[symbol]
        if not isinstance(series, pd.Series) or not series.index.equals(
            candidate_raw_minute_bars_by_symbol[symbol].index
        ):
            raise ValueError(f"candidate RVOL timestamp coverage mismatch for {symbol}")
        for timestamp, value in series.items():
            yield "candidate_exact_rvol", {
                "symbol": symbol,
                "bar_started_at": timestamp.isoformat(),
                "exact_same_time_rvol": _canonical_number(value),
            }


def market_inputs_fingerprint(**kwargs: object) -> str:
    digest = hashlib.sha256()
    for kind, value in iter_market_input_records(**kwargs):  # type: ignore[arg-type]
        digest.update(_record_line(kind, value))
    return digest.hexdigest()


def write_scanner_source_input_bundle(
    output_root: str | Path,
    *,
    trading_date: date,
    profile: StrategyProfile,
    membership_symbols: Iterable[str],
    candidate_symbols: Iterable[str],
    previous_close_by_symbol: Mapping[str, float | None],
    rank_split_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_raw_minute_bars_by_symbol: Mapping[str, pd.DataFrame],
    candidate_exact_rvol_by_symbol: Mapping[str, pd.Series],
    upstream_source_hashes: Mapping[str, str],
) -> dict[str, object]:
    del profile  # The exact time-causal frame has already been trimmed by the builder.
    root = Path(output_root)
    members = _symbols(membership_symbols, label="membership symbols")
    candidate_values = list(candidate_symbols)
    candidates = (
        _symbols(candidate_values, label="candidate symbols")
        if candidate_values
        else []
    )
    if candidates != sorted(candidate_raw_minute_bars_by_symbol):
        raise ValueError("declared candidates disagree with raw candidate frames")
    if set(upstream_source_hashes) != set(SOURCE_HASH_NAMES[:-1]):
        raise ValueError("upstream scanner lineage names mismatch")
    upstream = {name: str(upstream_source_hashes[name]) for name in SOURCE_HASH_NAMES[:-1]}
    if any(not _is_sha256(value) for value in upstream.values()):
        raise ValueError("upstream scanner lineage requires lowercase SHA-256")
    root.mkdir(parents=True, exist_ok=False)
    record_path = root / RECORD_FILE
    digest = hashlib.sha256()
    counts: Counter[str] = Counter()
    with record_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as compressed:
            for kind, value in iter_market_input_records(
                trading_date=trading_date,
                membership_symbols=members,
                previous_close_by_symbol=previous_close_by_symbol,
                rank_split_minute_bars_by_symbol=rank_split_minute_bars_by_symbol,
                candidate_raw_minute_bars_by_symbol=candidate_raw_minute_bars_by_symbol,
                candidate_exact_rvol_by_symbol=candidate_exact_rvol_by_symbol,
            ):
                line = _record_line(kind, value)
                digest.update(line)
                compressed.write(line)
                counts[kind] += 1
    logical_sha = digest.hexdigest()
    source_hashes = {**upstream, "reacquired_market_inputs": logical_sha}
    policy = causal_scanner_snapshot_v0_3_manifest()
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "trading_date": trading_date.isoformat(),
        "format": FORMAT_ID,
        "scanner_policy_id": CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID,
        "scanner_policy_fingerprint": policy["fingerprint"],
        "candidate_symbols": candidates,
        "source_hashes": source_hashes,
        "basis": {
            "displayed_price": "raw_candidate_close",
            "cumulative_volume": "raw_candidate_volume",
            "percent_gain": "split_target_close_over_split_previous_close",
            "cross_sectional_rank": "split_target_close_over_split_previous_close",
            "raw_split_candidate_timestamp_coverage_required_equal": True,
        },
        "summary": {
            "membership_symbol_count": len(members),
            "candidate_symbol_count": len(candidates),
            "logical_record_count": sum(counts.values()),
            "record_counts": {kind: counts.get(kind, 0) for kind in RECORD_KIND_ORDER},
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
        },
        "files": {"canonical_market_inputs": RECORD_FILE},
    }
    manifest["content_sha256"] = _fingerprint(manifest)
    validate_scanner_source_input_manifest(manifest, root=root)
    (root / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_scanner_source_input_manifest(
    manifest: Mapping[str, object], *, root: str | Path | None = None
) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("artifact_id") != ARTIFACT_ID:
        raise ValueError("unsupported scanner source-input v0.2 artifact")
    if manifest.get("format") != FORMAT_ID:
        raise ValueError("unsupported scanner source-input v0.2 format")
    date.fromisoformat(str(manifest.get("trading_date") or ""))
    policy = causal_scanner_snapshot_v0_3_manifest()
    if manifest.get("scanner_policy_id") != CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID or manifest.get(
        "scanner_policy_fingerprint"
    ) != policy["fingerprint"]:
        raise ValueError("scanner source-input v0.2 policy mismatch")
    candidates = manifest.get("candidate_symbols")
    if not isinstance(candidates, list) or candidates != sorted(set(candidates)) or any(
        not isinstance(value, str) or not value or value != value.upper() for value in candidates
    ):
        raise ValueError("scanner source-input candidate symbols are invalid")
    hashes = manifest.get("source_hashes")
    if not isinstance(hashes, Mapping):
        raise ValueError("scanner source-input lineage is missing")
    source_hashes = _source_hashes(hashes)  # type: ignore[arg-type]
    expected_basis = {
        "displayed_price": "raw_candidate_close",
        "cumulative_volume": "raw_candidate_volume",
        "percent_gain": "split_target_close_over_split_previous_close",
        "cross_sectional_rank": "split_target_close_over_split_previous_close",
        "raw_split_candidate_timestamp_coverage_required_equal": True,
    }
    if manifest.get("basis") != expected_basis:
        raise ValueError("scanner source-input raw/split basis is misstated")
    summary = manifest.get("summary")
    if not isinstance(summary, Mapping):
        raise ValueError("scanner source-input summary is missing")
    counts = summary.get("record_counts")
    if not isinstance(counts, Mapping) or set(counts) != set(RECORD_KIND_ORDER) or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts.values()
    ):
        raise ValueError("scanner source-input record counts are invalid")
    if summary.get("logical_record_count") != sum(counts.values()):
        raise ValueError("scanner source-input record total mismatch")
    if counts.get("contract") != 1 or counts.get("membership") != summary.get(
        "membership_symbol_count"
    ) or counts.get("previous_close") != summary.get("membership_symbol_count"):
        raise ValueError("scanner source-input required record counts mismatch")
    if len(candidates) != summary.get("candidate_symbol_count"):
        raise ValueError("scanner source-input candidate count mismatch")
    if counts.get("candidate_raw_bar") != counts.get("candidate_exact_rvol"):
        raise ValueError("scanner source-input raw-bar/RVOL count mismatch")
    if summary.get("logical_records_sha256") != source_hashes["reacquired_market_inputs"]:
        raise ValueError("scanner source-input logical hash disagrees with lineage")
    for field in ("logical_records_sha256", "compressed_file_sha256"):
        if not _is_sha256(summary.get(field)):
            raise ValueError(f"scanner source-input {field} is invalid")
    size = summary.get("compressed_size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError("scanner source-input compressed size is invalid")
    if manifest.get("files") != {"canonical_market_inputs": RECORD_FILE}:
        raise ValueError("scanner source-input file map is invalid")
    if manifest.get("knowledge_policy") != {
        "uses_benchmark_labels": False,
        "uses_retrospective_trade_outcomes": False,
        "contains_trades_setups_portfolio_or_pnl": False,
        "decision_time_market_inputs_only": True,
    }:
        raise ValueError("scanner source-input knowledge boundary is misstated")
    if manifest.get("replay_boundary") != {
        "raw_provider_responses_persisted": False,
        "canonical_runtime_inputs_persisted": True,
        "provider_independent_scanner_feature_replay_supported": True,
    }:
        raise ValueError("scanner source-input replay boundary is misstated")
    if manifest.get("content_sha256") != _fingerprint(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    ):
        raise ValueError("scanner source-input manifest content hash mismatch")
    if root is not None:
        record_path = Path(root) / RECORD_FILE
        if not record_path.is_file():
            raise ValueError("scanner source-input compressed file is missing")
        if _file_sha256(record_path) != summary["compressed_file_sha256"]:
            raise ValueError("scanner source-input compressed file hash mismatch")
        if record_path.stat().st_size != size:
            raise ValueError("scanner source-input compressed file size mismatch")


def _frame(
    rows: list[tuple[pd.Timestamp, dict[str, float | None]]], *, columns: tuple[str, ...]
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
    del profile
    path = Path(root)
    manifest = _load_json_object(path / MANIFEST_FILE)
    validate_scanner_source_input_manifest(manifest, root=path)
    membership: list[str] = []
    previous: dict[str, float | None] = {}
    rank_rows: dict[str, list[tuple[pd.Timestamp, dict[str, float | None]]]] = defaultdict(list)
    raw_rows: dict[str, list[tuple[pd.Timestamp, dict[str, float | None]]]] = defaultdict(list)
    rvol_rows: dict[str, list[tuple[pd.Timestamp, float | None]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    digest = hashlib.sha256()
    prior_kind = -1
    with gzip.open(path / RECORD_FILE, "rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            if not raw_line.endswith(b"\n") or b"\t" not in raw_line:
                raise ValueError("scanner source-input record framing is invalid")
            kind_bytes, encoded = raw_line[:-1].split(b"\t", 1)
            try:
                kind = kind_bytes.decode("ascii")
                value = json.loads(
                    encoded,
                    parse_constant=_reject_json_constant,
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
            except (UnicodeDecodeError, ValueError) as error:
                raise ValueError("scanner source-input record is invalid") from error
            if kind not in RECORD_KIND_ORDER or not isinstance(value, dict):
                raise ValueError("scanner source-input record kind is invalid")
            kind_index = RECORD_KIND_ORDER.index(kind)
            if kind_index < prior_kind:
                raise ValueError("scanner source-input record kinds are out of order")
            prior_kind = kind_index
            if _record_line(kind, value) != raw_line:
                raise ValueError("scanner source-input record is not canonical")
            counts[kind] += 1
            if kind == "contract":
                if value != {
                    "artifact": CAUSAL_SCANNER_SNAPSHOT_V0_3_ARTIFACT_ID,
                    "trading_date": manifest["trading_date"],
                    "format": FORMAT_ID,
                    "price_and_volume_adjustment": "raw",
                    "gain_and_rank_adjustment": "split",
                }:
                    raise ValueError("scanner source-input contract record mismatch")
            elif kind == "membership":
                membership.append(str(value.get("symbol") or ""))
            elif kind == "previous_close":
                symbol = str(value.get("symbol") or "")
                if symbol in previous:
                    raise ValueError("scanner source-input repeats previous close")
                raw_value = value.get("split_adjusted_previous_close")
                previous[symbol] = None if raw_value is None else _positive(raw_value, label="split previous close")
            elif kind in {"rank_split_close_bar", "candidate_raw_bar"}:
                symbol = str(value.get("symbol") or "")
                timestamp = pd.Timestamp(value.get("bar_started_at"))
                if timestamp.tzinfo is None:
                    raise ValueError("scanner source-input timestamp must be timezone-aware")
                if kind == "rank_split_close_bar":
                    values = {"close": _positive(value.get("split_adjusted_close"), label="split close")}
                    rank_rows[symbol].append((timestamp, values))
                else:
                    volume = _decode_number(value.get("raw_volume"), finite=True)
                    if volume is None or volume < 0:
                        raise ValueError("raw volume must be finite and nonnegative")
                    values = {
                        "close": _positive(value.get("raw_close"), label="raw close"),
                        "volume": volume,
                    }
                    raw_rows[symbol].append((timestamp, values))
            else:
                symbol = str(value.get("symbol") or "")
                timestamp = pd.Timestamp(value.get("bar_started_at"))
                if timestamp.tzinfo is None:
                    raise ValueError("scanner source-input timestamp must be timezone-aware")
                rvol_rows[symbol].append(
                    (timestamp, _decode_number(value.get("exact_same_time_rvol")))
                )
    summary = manifest["summary"]
    if digest.hexdigest() != summary["logical_records_sha256"]:
        raise ValueError("scanner source-input logical stream hash mismatch")
    if {kind: counts.get(kind, 0) for kind in RECORD_KIND_ORDER} != summary["record_counts"]:
        raise ValueError("scanner source-input observed record counts mismatch")
    if membership != sorted(set(membership)) or list(previous) != membership:
        raise ValueError("scanner source-input membership/previous-close order mismatch")
    candidates = tuple(str(value) for value in manifest["candidate_symbols"])
    if not set(candidates).issubset(membership):
        raise ValueError("scanner source-input candidate is absent from membership")
    rank_frames = {symbol: _frame(rows, columns=("close",)) for symbol, rows in rank_rows.items()}
    raw_frames = {
        symbol: _frame(raw_rows.get(symbol, []), columns=("close", "volume"))
        for symbol in candidates
    }
    rvol = {
        symbol: pd.Series(
            [value for _, value in rvol_rows.get(symbol, [])],
            index=pd.DatetimeIndex([timestamp for timestamp, _ in rvol_rows.get(symbol, [])]),
            dtype="float64",
        )
        for symbol in candidates
    }
    for symbol in candidates:
        split = rank_frames.get(symbol, pd.DataFrame(columns=["close"]))
        raw = raw_frames[symbol]
        if not split.index.equals(raw.index) or not raw.index.equals(rvol[symbol].index):
            raise ValueError("scanner source-input raw/split/RVOL timestamps disagree")
    logical_sha = market_inputs_fingerprint(
        trading_date=date.fromisoformat(str(manifest["trading_date"])),
        membership_symbols=membership,
        previous_close_by_symbol=previous,
        rank_split_minute_bars_by_symbol=rank_frames,
        candidate_raw_minute_bars_by_symbol=raw_frames,
        candidate_exact_rvol_by_symbol=rvol,
    )
    if logical_sha != summary["logical_records_sha256"]:
        raise ValueError("scanner source-input reconstruction changes logical hash")
    inputs = ScannerSourceInputs(
        trading_date=date.fromisoformat(str(manifest["trading_date"])),
        membership_symbols=tuple(membership),
        candidate_symbols=candidates,
        previous_close_by_symbol=previous,
        rank_split_minute_bars_by_symbol=rank_frames,
        candidate_raw_minute_bars_by_symbol=raw_frames,
        candidate_exact_rvol_by_symbol=rvol,
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
        raise ValueError("scanner source-input root contains an unexpected date artifact")
    if any(not _is_sha256(value) for value in source_bundle_hashes.values()):
        raise ValueError("scanner source-input root source hashes are invalid")
    policy = causal_scanner_snapshot_v0_3_manifest()
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "dates": dates,
        "scanner_policy_id": CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID,
        "scanner_policy_fingerprint": policy["fingerprint"],
        "source_bundle_hashes": dict(sorted(source_bundle_hashes.items())),
        "date_manifests": date_manifests,
        "replay_boundary": {
            "canonical_runtime_inputs_persisted": True,
            "provider_independent_scanner_feature_replay_supported": True,
            "upstream_artifacts_still_required": True,
            "policy_promotion_eligible": False,
        },
    }
    manifest["content_sha256"] = _fingerprint(manifest)
    validate_scanner_source_input_root_manifest(manifest)
    return manifest


def validate_scanner_source_input_root_manifest(
    manifest: Mapping[str, object],
) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get(
        "artifact_id"
    ) != ARTIFACT_ID:
        raise ValueError("unsupported scanner source-input root artifact")
    dates = manifest.get("dates")
    if (
        not isinstance(dates, list)
        or not dates
        or dates != sorted(set(dates))
        or any(not isinstance(value, str) for value in dates)
    ):
        raise ValueError("scanner source-input root dates are invalid")
    for value in dates:
        date.fromisoformat(value)
    children = manifest.get("date_manifests")
    if not isinstance(children, list) or len(children) != len(dates):
        raise ValueError("scanner source-input root date manifests are incomplete")
    if [str(row.get("trading_date") or "") for row in children if isinstance(row, Mapping)] != dates:
        raise ValueError("scanner source-input root date-manifest order mismatch")
    for row in children:
        if not isinstance(row, Mapping):
            raise ValueError("scanner source-input root date manifest is invalid")
        validate_scanner_source_input_manifest(row)
    policy = causal_scanner_snapshot_v0_3_manifest()
    if manifest.get("scanner_policy_id") != CAUSAL_SCANNER_SNAPSHOT_V0_3_POLICY_ID or manifest.get(
        "scanner_policy_fingerprint"
    ) != policy["fingerprint"]:
        raise ValueError("scanner source-input root policy mismatch")
    hashes = manifest.get("source_bundle_hashes")
    if not isinstance(hashes, Mapping) or not hashes or any(
        not _is_sha256(value) for value in hashes.values()
    ):
        raise ValueError("scanner source-input root lineage hashes are invalid")
    if manifest.get("replay_boundary") != {
        "canonical_runtime_inputs_persisted": True,
        "provider_independent_scanner_feature_replay_supported": True,
        "upstream_artifacts_still_required": True,
        "policy_promotion_eligible": False,
    }:
        raise ValueError("scanner source-input root replay boundary is misstated")
    if manifest.get("content_sha256") != _fingerprint(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    ):
        raise ValueError("scanner source-input root content hash mismatch")
