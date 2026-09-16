# Prior daily history for scanner candidates

The raw-minute parent `54ba261fe9ed6f003f39812932d3812c0a6dd6d2` passed
full CI `35134553230`: 3,005 tests in 489.287 seconds, 73 optional skips and
successful compilation. Hosted capture `35134553351` and its independent
verifier passed all jobs and steps. They accepted 233,576 raw minute bars for
all 4,018 candidate/date cases, including 126 explicitly empty cases, using
33 requests. Original proof, consumption and terminal metadata are retained
in the candidate-raw audit directory. The original capture is artifact
`10462664282`, 4,601,420 bytes, SHA-256
`0b765e27cc96a6b7d52a0a8878b238cc1ce3d1954ec01b07184ba13bf5569f08`.
Its recorded retention expires December 15, 2026.

This additive stage supplies prior daily history for the same candidate
population. It does not rerun candidate discovery or change any policy.
Thirty fixed batches request split-adjusted SIP 1Day bars from 120 calendar
days before each target through 23:59:59 ET on the preceding date. Dated
symbol mapping and original membership hashes are preserved. Requests allow
20 pages per root, 600 attempts total, no retries and the existing transport,
byte, pacing and duration limits. The input population remains the saved
acquisition-only daily superset; full-day selection values do not enter
features, priorities or discretionary prompts.

The parser reuses the accepted per-symbol ordering and strict OHLC, cursor,
window and transport validation. It additionally rejects duplicate local
session dates and every target/future daily observation. It records the last
50 observed prior sessions per symbol, preserving explicit insufficient
history. Empty responses require successful exhaustion. Missing sessions
are never synthesized or padded. The pure source projector retains the
original daily frames and uses the existing scanner average-volume function;
less than 50 observations or nonpositive average volume remains unavailable.
The projector checks page replay against an expected summary but does not
itself authenticate provider origin.

The shared hosted lifecycle requires exact-code CI and permanent one-use
consumption before credential loading, then automatically verifies original
archive bytes, receipts and full replay. The frozen raw and split capture
implementations remain unchanged. Ten focused tests pass normally and with
assertions disabled, including DST, the prior-date boundary, last-50-session
selection, original average-volume semantics, short/zero-volume histories,
cross-page duplicates, byte tampering, credential gating and hosted imports.

This is the daily prerequisite for exact RVOL; it does not supply same-time
minute history or establish agreement between daily/minute adjustment
vintages. Alpaca documents `asof` as symbol-entity mapping and `split` as a
price/volume adjustment: https://docs.alpaca.markets/us/reference/stockbars.
The next source step must derive the exact prior-session minute requests,
retain unavailable histories, and verify share-unit consistency. Complete
rank-basis checks, point-in-time float, timed news and the additive scanner
v0.3 discretionary-shadow adapter still remain. No financial evaluation,
policy promotion or live-order authority is opened by this capture.
