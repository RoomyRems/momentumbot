# Historical missing management input capture v0.1

This isolated child binds verified reuse commit
`813960e42a96edd40983bc3e414743c0bf67452d`, tree
`49b7c0d4d71d5ce2adc452bfa3d64216903556cf`. Its only hypothesis is that the
ten exact missing management resource envelopes can be exhausted and retained
without repeating any completed source capture. Ross actions, transcripts,
recap labels, later outcomes, broker accounts and orders remain excluded.

The [immutable missing-input requirements](../../research/strategy/sealed-historical-management-missing-inputs-v0.1.json)
and [verified reuse stage](sealed_historical_management_reuse_v01.md) remain
unchanged. The new acquisition contract does not itself authorize provider
access: only a separately published, sole-added execution child of tested code
can reach the one-shot workflow. Main and all existing consumption tags remain
unchanged. No source, account seed, policy, opportunity or scenario is changed.

## Scope and mechanics

The five registered tails begin at 10:00 New York: TPST on June 9, XTIA on
June 12, JVA on June 13, LIXT on July 2 and MBIO on July 7, 2025. Each has one
raw SIP one-minute bar request and one SIP transaction request. Exact nanosecond
endpoints, historical `asof`, symbol, feed and request order are copied without
floating-point conversions. Wire end is exclusive end minus one nanosecond.
There is no time-window extension or end-of-data liquidation.

The isolated transport permits only GET requests to `data.alpaca.markets`,
using `/v2/stocks/bars` or `/v2/stocks/trades`. It retains a separate attempt
ledger, flushed and fsynced before every actual request. There are at most
512 HTTP attempts, 16,000,000 response bytes per page and 10,000 rows per page,
with at least 0.35 seconds between attempts. Redirects, automatic retries,
repeated request/page pairs and workflow reruns are forbidden. The existing
Alpaca subscription is used with no incremental provider purchase.

Every compressed-file write checks the shared 100,000,000-byte ceiling before
writing. Failures preserve the bounded partial tape, completed receipts,
sanitized failure, actual attempt ledger and full provenance inventory. No
existing output directory can be reused. No credentials or provider error
bodies are retained.

The original normalizer is unchanged. Canonical records preserve source order
and exact timestamps; no sorting, deduplication, condition filtering or
execution eligibility filtering takes place. Minute bars must retain unique,
minute-aligned timestamps. Exhausted empty segments retain a valid empty gzip
and a zero-record receipt. Empty evidence never becomes a trade, exit or
account outcome. A bar timestamp does not authorize using its eventual close
before the frozen completed-bar timing rule allows it.

## Execution gate and verification

The provider-free preflight revalidates the exact committed reuse result,
its five output files, pinned implementation, all frozen parents and permanent
independent audit. It explicitly attests that the old source archives were
verified previously, not reopened by this preflight. This avoids repeating
the already completed source acquisition or claiming a new reconstruction.

The workflow requires a first-attempt push on the research branch whose only
change is the new execution JSON. Execution binds the exact tested parent
commit/tree, contract and workflow. Before market-data credentials are exposed,
the workflow atomically creates a new consumption tag and uploads its receipt
as a retained artifact. A previously consumed operation cannot be retried.

Verification is offline. It checks the exact 28-member successful archive,
all member hashes, request and provenance documents, receipt seals, every
uncompressed canonical row, chronological ordering, bounds, duplicate
detection, compressed byte totals, exhausted pages and separate ledger. The
external verification must additionally bind the exact GitHub artifact ZIP,
execution commit/tree, consumption tag, workflow attempt and successful steps.

Local adversarial tests include the complete CLI-to-archive path, empty
segments, partial failure retention, changed inputs and re-sealed metadata.
All 1,693 local repository tests passed with zero skips. The 79 focused tests
passed normally and under optimized Python, and both entrypoint/module
undefined-global checks passed. Local verification used CPython 3.12.13 and
the existing hash-locked environment; hosted checks use CPython 3.12.14.
An initial preparation test correctly rejected a lossy JSON serialization of
nanosecond integers; the registration was regenerated directly from Python's
integer-preserving output before any publication or provider access. No frozen
parent was changed.

```bash
PYTHONPATH=src:scripts python scripts/capture_sealed_historical_management_inputs_v01.py --validate-only
PYTHONPATH=src:scripts python scripts/capture_sealed_historical_management_inputs_v01.py --verify-reuse
PYTHONPATH=src:scripts python scripts/capture_sealed_historical_management_inputs_v01.py --verify-archive /path/to/capture.zip --execution-commit FULL_SHA --run-id EXACT_ID
```

Next after an independently verified capture: register and build provider-free
composition of reused prefixes and new tails. All 109 opportunities and 23
unavailable entry inputs remain preserved. Management projection, executable
exits, causal next-session valuation and account replay are separate later
dependencies. Descriptive SIP evidence cannot close account positions or make
portfolio financial metrics eligible.

## Independently verified result — 2026-09-07

Tested code `eead72443160b08291ec5016900e71b0dc64e6ef` passed all eight
hosted workflows before the sole execution child
`eeec1ea234214a9d4a449e774fe3fa29aefea025` was published. The dedicated
[capture run](https://github.com/RoomyRems/momentumbot/actions/runs/34142720577)
completed on attempt 1, with every preflight, consumption, capture and retention
step successful. Its consumption tag now permanently binds that execution.

All ten resources completed in 11 HTTP attempts, with no retries or blocked
attempts. The 28,387 normalized records comprise 28,356 SIP trades and 31 raw
minute bars, totaling 353,382 compressed bytes. No actual segment was empty;
empty-segment behavior remains covered by deterministic tests.

| Date | Symbol | Raw minute bars | SIP trades | HTTP attempts |
|---|---|---:|---:|---:|
| 2025-06-09 | TPST | 1 | 7 | 2 |
| 2025-06-12 | XTIA | 12 | 7,649 | 2 |
| 2025-06-13 | JVA | 12 | 225 | 2 |
| 2025-07-02 | LIXT | 4 | 7,344 | 2 |
| 2025-07-07 | MBIO | 2 | 13,131 | 3 |

The retained capture artifact is `10026551595` (373,515-byte ZIP), SHA-256
`dd6acf2844e69aa975a0274fe7813b3029cf7a6b6ef5d8830c322e17d436d9b6`.
The consumption artifact is `10026547607` (4,586-byte ZIP), SHA-256
`ddd88a57ed8ef12c9af3c08d7b03af0e6698dabf7bd3fdc4efc9bcd37b638e9b`.
Both are retained for 90 days, with recorded expiry December 6, 2026.

The primary offline verifier and a separate stdlib-only checker agree on
every receipt, normalized record, original ordering, request bound, byte count
and ledger total. The independent checker additionally verifies the retained
28 capture files, six consumption files, exact external artifact metadata,
execution parent/tree, first-attempt run and durable-consumption ordering.
The [permanent audit](../../research/data-audits/sealed-historical-management-missing-input-v0.1-independent-verification-34142720577.json)
embeds both results, independent checker source, source/file commitments,
hosted steps, test summaries and protected-reference evidence.

All 1,693 local tests passed without skips. Dedicated hosted preflight ran all
79 focused tests normally and optimized without skips. Generic GitHub CI also
passed 1,693 tests on both code and execution commits, with 51 optional-SDK
skips in its intentionally smaller environment. Main, all eight earlier
consumption tags, original source/capture ledgers, account seeds, policy and
the 23 unavailable entry opportunities are unchanged.

This completes missing-input capture, not management-source composition or
backtesting. The next dependency is provider-free composition of the verified
reused prefixes and these exact tails. No management projection, simulated
fill, account session or backtest ran, and no transcript was accessed.
