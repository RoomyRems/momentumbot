# Corpus audit — 2026-08-14

This audit describes the eight metadata-enriched Warrior Trading JSONL files supplied for MomentumBot research. Raw transcripts are not committed to this repository.

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

All 2,292 records identify the same Ross Cameron / Warrior Trading channel ID. The 129 undated records are useful for non-chronological discovery, but they are quarantined from walk-forward experiments until publication dates are resolved.

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

## Strategy-topic coverage

The counts below are coarse discovery counts, not claims that every mention is a rule. A video is counted when normalized captions contain at least one keyword/phrase in the corresponding topic group.

| Topic | Videos mentioning topic |
|---|---:|
| Stock selection / float / RVOL / scanners | 1,421 |
| Halts / spreads / slippage / microstructure | 1,240 |
| Catalyst / breaking news / theme | 1,048 |
| Pullbacks / micro pullbacks / bull flags | 1,086 |
| FOMO / discipline / emotional state | 1,009 |
| Daily chart / major levels | 905 |
| Exit / topping-tail / false-breakout language | 854 |
| Risk / max loss / profit-loss ratio | 766 |
| Level 2 / tape / hidden liquidity | 719 |
| Hot/cold market regime | 715 |
| Reverse splits / offerings / dilution | 674 |

These frequencies justify treating the corpus as a behavioral dataset rather than a small set of isolated lessons. They also warn against simple keyword-to-rule extraction: the same concepts appear in teaching, successful trades, failed trades and explicit self-critique.

## Research implications

1. **Chronology is mandatory.** Strategy language materially evolves across 2013-2026. Current-era rules cannot be projected backward without versioning.
2. **Normative and behavioral evidence must be separate.** A training video can state a rule; a recap can show an exception; a red-day recap can show a violation that should be labeled as a mistake rather than copied into policy.
3. **Raw transcripts cannot be live RAG.** A retrospective recap can reveal the outcome of the exact historical event being backtested.
4. **Missing dates are a leakage risk.** The 129 undated videos stay out of chronology-sensitive datasets until resolved.
5. **Missing captions are not filled by inference.** Fourteen records are metadata-only unless captions are later recovered.

The reproducible audit command is implemented by `momentumbot-corpus-audit`.
