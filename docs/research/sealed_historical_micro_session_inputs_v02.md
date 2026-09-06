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

## Consumed operation and independent verification

The sole execution child `bf5863a7115abef9e22c4f527448cd9c20084f47` ran once as
`34054580516`, attempt 1, and completed successfully. Its tested code parent is
`e7b0b64eb61358cf3462a48026c14d1ae052d8fb`. CI and dedicated validation passed at
that exact parent. The execution used CPython 3.12.14, the frozen requirement
lock, undefined-name checks, and 19 focused tests both normally and under `-O`.
The broader prepublication suite passed 37 focused tests in both modes and all
1,430 repository tests.

Independent verification downloaded both ZIPs and checked every retained file,
receipt, canonical tape row, interval, request ID and ledger entry. Capture
artifact `9995587996` has ZIP SHA-256
`d689f493c10996bee7eddde68d62812e7850fc322caa2d530d33a97c84878e3f`;
consumption artifact `9995572398` has ZIP SHA-256
`1b16ca8d92b9f7e381e5abbc947aeebcdf755f661611f5643d4fc78b18e8c122`.
The report file/content hashes are
`ebd2f02b3df83fbc5cb45b8fee86120e278c3a41c8a1d07e87e972bef6c26b9d`
and `9fc1c5fda0942ded03cfb3a574d69802bae927dcf31f538c917cbfb33af103e0`.
All 348 capture files and 170 tapes passed; the separate ledger records exactly
170 HTTP attempts and zero blocked attempts.

The acquisition envelope includes the 09:59 minute. The pre-existing
`trim_scanner_bar_frame` rule retains only bars whose end is strictly before
10:00, as does the v0.13 source builder. The initial diagnostic comparison
included the unavailable 09:59 tail and therefore reported an extra PBM minute;
inspection traced that difference to this existing acquisition/runtime boundary.
Applying that unchanged rule verifies all 29,405 usable minute closes and
volumes exactly against v0.13 across every frozen pair and date. All 149 retained
09:59 tail rows remain in the hashed input evidence and are unavailable to the
entry runtime. No source row, price, volume, threshold, or cutoff was rewritten.

The permanent receipt is
`research/data-audits/sealed-historical-micro-session-input-v0.2-independent-verification-34054580516.json`,
content commitment
`cd501d099993ec66d69ac548d72c401d858ac5ffc2740eda69b4fe7ed45f301a`.
The remaining prerequisite is terminal verification of SIP-print/warmup run
`34053730042`, then causal price-basis validation and the provider-free Micro
runtime. This consumed workflow is never rerun.
