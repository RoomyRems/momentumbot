# Historical Micro raw minute supplement v0.2

The v0.13 Snapshot and the 192 scanner activations are frozen. The independently
registered SIP-print/warmup acquisition runs once as `34053730042`, attempt 1,
at execution commit `5cab2eb3aa2b73a2cbf1d57575519a7b99961e24`. Its code parent is
`46e5bd28bf852402faf0e5092d1ca253ca6cc7d0`; its consumption receipt was durably
uploaded before the provider step. That capture and its original ledger remain
unchanged by this supplement.

## Additional input dependency

The canonical v0.13 `candidate_raw_bar` record retains `raw_close` and
`raw_volume`, as shown by `scanner_source_inputs_v03.py`. It does not retain
minute opens, highs, or lows. Micro's unchanged `session_vwap` uses typical
price `(high + low + close) / 3`, so close/volume alone cannot provide its
registered support input. The earlier reference to raw minute scanner inputs
must not be interpreted as a complete OHLCV source for Micro.

This separate child captures raw SIP one-minute OHLCV for exactly the existing
170 symbol/date pairs, from 04:00 inclusive to 10:00 exclusive New York time.
It requests no trades, prior warmup, candidate expansion, or additional dates.
The request list commitment is
`ff4c2db2946885b842d986ed128a9abde3e10f8f3baa8715f938dfd9c9958306`.
The contract commitment is
`d2660aaa38585cab675d1dedbda0947c28c69951e95339da5cc50317c04005e8`.

The existing Alpaca subscription supplies this zero-incremental-cost input.
Limits are 170 logical requests, 680 actual HTTP attempts including bounded
transient retries, and 100 MB of normalized compressed data. Only GET requests
to the stock bars endpoint are implemented, with raw adjustment, SIP feed,
explicit session `asof`, ascending pagination, and an exclusive end encoded as
one nanosecond before 10:00. Redirects and unrequested identities fail closed.

The dormant workflow requires a sole added execution record binding its exact
tested code parent and workflow hash. It verifies all final Snapshot bytes,
atomically creates a new consumption ref, and durably uploads that receipt
before the only provider step. The installed `main` source dispatcher and all
consumed parent files are preserved. The user's 2026-09-06 continuing
development and operational authorization covers this bounded dependency;
no strategy or account policy changes are introduced.

## Required checks before Micro

Both input captures must first pass independent artifact and per-tape hash
verification. The raw session supplement must match every frozen close and
volume at the exact frozen timestamps for each selected symbol/date. Added,
missing, duplicated, or revised minute records fail; they cannot rewrite the
Snapshot or be treated as zero triggers.

The separately captured prior split-adjusted warmup still requires conversion
to the raw session price basis using only frozen raw/split pairs available
before activation. That conversion must be validated before Micro. Warmup
cannot contribute to session VWAP. Ten-second bars are derived from captured
SIP prints by the existing aggregator, and the unchanged Micro-v0.1 policy
consumes only completed causal bars and support values.

This acquisition emits input evidence only. Micro, execution/status acquisition,
account simulation, retrospective comparison, and policy promotion retain their
registered order and validation requirements. No label or transcript is opened.
