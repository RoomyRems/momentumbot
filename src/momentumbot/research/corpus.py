"""Utilities for auditing and safely using the transcript research corpus.

The raw transcript corpus is research input, not runtime strategy context. In
particular, records published after a replay date must never be visible to a
historical experiment because daily recap videos can reveal the outcome of the
very trade being replayed.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence

_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y")
_WHITESPACE = re.compile(r"\s+")
_WORD = re.compile(r"\b\w+\b", re.UNICODE)

TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "stock_selection": (r"\bfive pillars\b", r"\brelative volume\b", r"\bfloat\b", r"\bleading gainer\b", r"\bgap scanner\b"),
    "pullbacks_entries": (r"\bfirst pullback\b", r"\bmicro pullback\b", r"\bfirst candle to make a new high\b", r"\bcandle over candle\b", r"\bbull flag\b"),
    "level2_tape": (r"\blevel 2\b", r"\blevel two\b", r"\btime and sales\b", r"\bhidden seller\b", r"\biceberg\b"),
    "risk_management": (r"\bmax loss\b", r"\bprofit to loss\b", r"\brisk[- ]to[- ]reward\b", r"\bgive back half\b", r"\bposition size\b"),
    "market_regime": (r"\bhot market\b", r"\bcold market\b", r"\bhot streak\b", r"\bcold streak\b", r"\bmomentum is hot\b"),
    "daily_chart": (r"\bdaily chart\b", r"\b200 moving average\b", r"\b200 ema\b", r"\bgap fill\b", r"\bdaily level\b"),
    "exits": (r"\bexit indicator\b", r"\btopping tail\b", r"\bfalse breakout\b", r"\bbig seller\b", r"\bburst of red\b"),
    "catalyst_theme": (r"\bbreaking news\b", r"\bcatalyst\b", r"\bprivate placement\b", r"\bhot sector\b", r"\bkeyword stuffing\b"),
    "halts_microstructure": (r"\bhalt\b", r"\bresumption\b", r"\bslippage\b", r"\bspread\b"),
    "behavior_psychology": (r"\bfomo\b", r"\brevenge\b", r"\bemotional\b", r"\bdiscipline\b", r"\bcomposure\b"),
    "reverse_split_dilution": (r"\breverse split\b", r"\boffering\b", r"\bshelf registration\b", r"\bdilution\b"),
}


@dataclass(frozen=True, slots=True)
class CorpusRecord:
    video_id: str
    title: str
    channel_name: str
    channel_id: str
    published_at: date | None
    date_text: str | None
    relative_date_text: str | None
    thumbnail_url: str | None
    captions: str
    status: str | None
    reason: str | None
    source_file: str
    source_line: int
    source_sha256: str

    @property
    def word_count(self) -> int:
        return len(_WORD.findall(self.captions))

    @property
    def has_captions(self) -> bool:
        return bool(self.captions)


@dataclass(frozen=True, slots=True)
class CorpusAudit:
    records: int
    unique_video_ids: int
    duplicate_video_ids: int
    records_with_captions: int
    records_without_captions: int
    records_with_publication_date: int
    records_without_publication_date: int
    first_publication_date: str | None
    last_publication_date: str | None
    total_caption_words: int
    year_counts: dict[str, int]
    topic_video_counts: dict[str, int]
    channel_ids: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_captions(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = " ".join(str(part) for part in value)
    text = html.unescape(str(value)).replace("\u00a0", " ")
    return _WHITESPACE.sub(" ", text).strip()


def parse_publication_date(value: object) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported publication date format: {text!r}")


def _parse_line(raw_line: str, source_file: str, line_no: int) -> CorpusRecord:
    raw = json.loads(raw_line)
    required = ("videoId", "title", "channelName", "channelID")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"Missing required fields {missing} in {source_file}:{line_no}")
    return CorpusRecord(
        video_id=str(raw["videoId"]), title=str(raw["title"]), channel_name=str(raw["channelName"]), channel_id=str(raw["channelID"]),
        published_at=parse_publication_date(raw.get("dateText")), date_text=raw.get("dateText"), relative_date_text=raw.get("relativeDateText"),
        thumbnail_url=raw.get("thumbnailUrl"), captions=normalize_captions(raw.get("captions")), status=raw.get("status"), reason=raw.get("reason"),
        source_file=source_file, source_line=line_no, source_sha256=hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
    )


def iter_jsonl(paths: Iterable[str | Path]) -> Iterator[CorpusRecord]:
    for path_like in paths:
        path = Path(path_like)
        with path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, 1):
                if raw_line.strip():
                    yield _parse_line(raw_line, path.name, line_no)


def load_jsonl(paths: Iterable[str | Path]) -> list[CorpusRecord]:
    return list(iter_jsonl(paths))


def topic_hits(record: CorpusRecord) -> set[str]:
    text = record.captions.lower()
    return {topic for topic, patterns in TOPIC_PATTERNS.items() if any(re.search(pattern, text) for pattern in patterns)}


def audit_corpus(records: Sequence[CorpusRecord]) -> CorpusAudit:
    ids = Counter(record.video_id for record in records)
    dated = [record.published_at for record in records if record.published_at]
    years = Counter(str(day.year) for day in dated)
    topics = Counter()
    for record in records:
        topics.update(topic_hits(record))
    channels = Counter(record.channel_id for record in records)
    return CorpusAudit(
        records=len(records), unique_video_ids=len(ids), duplicate_video_ids=sum(count - 1 for count in ids.values() if count > 1),
        records_with_captions=sum(record.has_captions for record in records), records_without_captions=sum(not record.has_captions for record in records),
        records_with_publication_date=len(dated), records_without_publication_date=len(records) - len(dated),
        first_publication_date=min(dated).isoformat() if dated else None, last_publication_date=max(dated).isoformat() if dated else None,
        total_caption_words=sum(record.word_count for record in records), year_counts=dict(sorted(years.items())),
        topic_video_counts=dict(sorted(topics.items())), channel_ids=dict(channels),
    )


def split_as_of(records: Iterable[CorpusRecord], as_of: date) -> tuple[list[CorpusRecord], list[CorpusRecord], list[CorpusRecord]]:
    """Split records into eligible, future/leaking, and undated/quarantined sets."""
    eligible: list[CorpusRecord] = []
    future: list[CorpusRecord] = []
    undated: list[CorpusRecord] = []
    for record in records:
        if record.published_at is None:
            undated.append(record)
        elif record.published_at <= as_of:
            eligible.append(record)
        else:
            future.append(record)
    return eligible, future, undated


def search_records(records: Iterable[CorpusRecord], query: str, *, published_on_or_after: date | None = None, published_on_or_before: date | None = None, limit: int = 20) -> list[CorpusRecord]:
    """Simple local evidence discovery helper; never used by the live trader."""
    terms = [term.lower() for term in _WORD.findall(query)]
    scored: list[tuple[int, date, CorpusRecord]] = []
    for record in records:
        if published_on_or_after and (record.published_at is None or record.published_at < published_on_or_after):
            continue
        if published_on_or_before and (record.published_at is None or record.published_at > published_on_or_before):
            continue
        haystack = f"{record.title} {record.captions}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append((score, record.published_at or date.min, record))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [record for _, _, record in scored[:limit]]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Warrior Trading transcript JSONL files.")
    parser.add_argument("paths", nargs="+", help="JSONL transcript files")
    parser.add_argument("--as-of", help="Optional YYYY-MM-DD leakage split date")
    args = parser.parse_args(argv)
    records = load_jsonl(args.paths)
    payload: dict[str, object] = {"audit": audit_corpus(records).to_dict()}
    if args.as_of:
        as_of = date.fromisoformat(args.as_of)
        eligible, future, undated = split_as_of(records, as_of)
        payload["as_of"] = {"date": as_of.isoformat(), "eligible": len(eligible), "future": len(future), "undated_quarantined": len(undated)}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
