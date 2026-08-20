# Corpus audit — 2026-08-14

This audit describes the eight metadata-enriched Warrior Trading JSONL files supplied for MomentumBot research. Raw transcript text is not committed to this repository.

## Integrity summary

| Metric | Result |
|---|---:|
| Records | 2,292 |
| Unique video IDs | 2,292 |
| Duplicate video IDs | 0 |
| Records with captions | 2,278 |
| Records without captions | 14 |
| Records with explicit publication date | 2,163 |
| Records without publication date | 129 |
| Earliest explicit date | 2013-12-20 |
| Latest explicit date | 2026-08-14 |
| Approximate normalized caption words | 9,139,448 |
| Channel IDs represented | 1 |

The 129 undated records are useful for non-chronological discovery but remain quarantined from walk-forward experiments until publication dates are resolved.

## Explicit-date distribution

| Year | Videos |
|---|---:|
| 2013 | 1 |
| 2014 | 1 |
| 2015 | 6 |
| 2016 | 5 |
| 2017 | 46 |
| 2018 | 215 |
| 2019 | 246 |
| 2020 | 180 |
| 2021 | 194 |
| 2022 | 157 |
| 2023 | 164 |
| 2024 | 359 |
| 2025 | 365 |
| 2026 | 224 |

## Chronology smoke test

Freezing strategy knowledge at 2025-01-01 produces:

- 1,575 eligible videos;
- 588 future videos that must remain hidden;
- 129 undated/quarantined videos.

At 2026-01-01 the split becomes 1,940 eligible, 223 future, and the same 129 quarantined records.

## Coarse strategy-topic coverage

Keyword/phrase discovery found broad coverage across the corpus: stock selection, pullbacks, catalysts, Level 2/tape, risk, market regime, daily chart, exits, halts/slippage, psychology, and reverse-split/dilution topics all appear in hundreds of videos. These are discovery counts, not rule votes; a mention may be teaching, a successful trade, an exception, or a mistake.

## Consequences for the project

1. Strategy knowledge must be versioned by era.
2. Normative teaching, observed behavior, and self-critique are separate evidence modes.
3. Raw recap transcripts can never be live RAG for historical replay.
4. Unknown publication dates fail closed.
5. Missing captions remain missing rather than being silently inferred.
