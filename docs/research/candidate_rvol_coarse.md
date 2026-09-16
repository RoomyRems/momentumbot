# Candidate source integration and bounded RVOL history

Parent `17f8561b5dd147029d4c4810dc6b8592a7139f5b` passed full CI
`35163240503`: 3,015 tests in 314.632 seconds, 73 optional skips and
successful compilation. Daily capture `35163240481` and its independent
verifier completed successfully: 318,519 daily bars, 4,018 candidate/date
cases and 45 requests. There are 114 cases with fewer than 50 prior sessions.
The original proof and consumption archives and terminal metadata are retained
under `early-pullback-candidate-daily-history-v0.1`. The original capture is
artifact `10473823241`, 8,054,137 bytes, SHA-256
`9dd8f4f8a3deea55f865ff7117f6da86c7a165f51c354648600ec23e01389fbf`.
Its recorded retention expires December 15, 2026.

## Candidate source reader and basis diagnostic

`CandidateMinuteArchive` verifies the fixed original hosted proof and capture
bytes before projecting every requested candidate into raw OHLCV frames,
including explicit empty frames. The reader verifies source members, exact
root/summary populations and page replay. Source lineage is retained; bar
labels remain starts, usable only after the minute completes. The source
reader opens no scanner, financial evaluation or order authority.

`audit_candidate_price_basis.py` compares raw candidate closes with selected
closes from the independently accepted full-membership split archives. The
selection does not change the full ranking population. It also compares
observed price scales with the old saved daily raw/split high ratio. Those
full-day values are confined to this offline source diagnostic, never runtime
features or acquisition priority.

All 30 dates completed under optimized Python: 3,892 nonempty pairs have
identical timestamps and 126 cases are empty in both sources. At a strict
relative arithmetic tolerance of 1e-9, 175 cases contain 5,907 price residuals;
the maximum relative residual is 0.000779144698301204 (about 0.078%). This is
not a certified common adjustment basis. Rounding or adjustment differences
must be explained, and noncandidate ranking members still require coverage.
No tolerance was changed to make these cases pass. The original diagnostic
seal is `fc6179cb78130c313e99c498d58097d1304cbdde251aa243b45601eadd630c4e`;
the JSON is retained with lossless gzip compression in the candidate-source
audit directory. Initial set-serialization failure is preserved; canonical
comparison now receives sorted symbol lists. Six reader/diagnostic tests pass
normally and optimized, including missing/invalid source evidence and tampering.

## RVOL acquisition

The new stage uses the already frozen completed-15-minute-volume upper-bound
filter to reduce later exact-minute downloads. Its input plan is derived from
the accepted daily proof and raw proof, not new discovery or retrospective
outcomes. It retains 3,778 candidate/date cases with 50 observed prior sessions
and nonempty raw minutes. All 240 excluded cases retain explicit reasons:
114 insufficient histories and 126 exhausted empty raw sources.

There are 1,530 roots and 192,678 symbol/session observations: each eligible
case's exact 50 prior sessions plus its target morning. Target 15-minute bars
are included for a separate overlapping-volume basis comparison. Each batch
has at most 250 symbols (actual maximum 192), retains the target date's `asof`
mapping and original membership hash, and requests split-adjusted SIP 15Min
bars from 04:00 through 09:45 ET. The last bucket completes at 10:00. No
unneeded afternoon bars or unobserved history dates are requested.

The parser preserves the accepted per-symbol ordering and strict OHLC/cursor
checks and enforces the 15-minute grid and exact observation date. Limits
remain 20 pages per root, with a tighter aggregate ceiling of 9,000 attempts,
no retries, existing byte/pacing/duration ceilings, exact-code CI before
credentials, and permanent one-use consumption. Independent original-archive
verification runs automatically. Seven focused capture tests pass normally
and optimized, covering exact sessions, exclusions, grid/cutoff, archive replay,
original proofs and preflight size. Existing capture implementations are frozen.

The captured coarse volumes remain acquisition-only. No new RVOL threshold,
policy, date, account setting, identity mapping or strategy is introduced.
Exact one-minute same-time RVOL and explicit share-unit consistency are still
required before scanner integration, followed by float/news and the additive
scanner-v0.3 discretionary-shadow adapter. AI and live-order authority remain
unchanged.
