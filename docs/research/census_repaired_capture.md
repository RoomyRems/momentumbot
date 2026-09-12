# Integrated repaired census capture

The parent is `b0eb4cdd926edee99974d81040fd6b968b7d71a2`, preserving the
verified provider-order repair and its successful 2,779-test CI. This change tests
one hypothesis: the repaired protocol can exhaust the fixed 30-date census and
independently reproduce every original page with unchanged identity and cursor
rules. No recap labels, Ross actions/fills, transcripts or later price outcomes
enter this work. Historical replay and policy promotion remain closed.

## Integrated flow

1. Full GitHub CI must pass for the exact new code commit. The first-attempt push
   then creates a new permanent consumption ref and preserves independent
   preflight evidence before any provider credential is read.
2. `census_capture.py` uses the frozen repaired projection and state for one
   bounded capture. It writes request intents before transport and retains safe
   raw JSON before validation, including rejected responses. Credential echoes
   and uninspectable bodies produce hashes/receipts only. Any failure stops the
   pass, with no automatic retry, alternate credential or provider fallback.
3. A separate job downloads the original capture and launch ZIPs. Without a
   provider credential, it checks GitHub artifact digests, same-code CI and job
   provenance, permanent consumption, independent inventory commitments, every
   raw/normalized page, request order, pacing and all 30 terminal date states.
   The workflow finishes successfully only after this independent replay passes.

The old collector, verifier, launchers and consumed refs are unchanged. The new
collector and verifier share the repaired pure protocol, while raw-byte replay
still recomputes projections and transitions independently of saved results.
There is no execution-only commit, repeat approval checkpoint or duplicate local
full-suite prerequisite. Safe failure retention prevents another blind payload
diagnostic cycle.

## Fixed authorization and limits

The owner's current “You may continue” follows the recorded authorization for
reasonable charges and the explicit collector/verifier/census next step. Scope:
one pass over the same 30 dates, at most 601 requests, 20 pages per date, 1,000
rows per page, 12.5 seconds minimum between requests, 16 MB per response and
1.5 GB total retained data. Complete pagination is mandatory; reaching a budget
or page ceiling is a failure, not a truncated successful census.

The September 12 public reference-endpoint pricing observation remains the basis
for an estimated USD 0 incremental API cost. The selected ceiling is USD 10;
actual billing, subscription entitlement and the provider of the owner's credits
remain unverified. No metered purchase or subscription change is enabled. The
authorization expires September 19, 2026 at 00:00 UTC.

At the full 601-request ceiling, minimum request pacing alone takes about 125
minutes. Capture has a 160-minute job timeout and archive verification has 30
minutes. These jobs continue on GitHub independently of the chat. No unattended
retry or unbounded continuation is configured.

## Verification

All 66 focused tests passed normally (6.276 seconds) and optimized (6.655 seconds),
including 37 new integration/gate tests and 29 existing order-repair tests.
Compilation passed. Cases include the exact quarantined provider page, synthetic
complete 30-date captures, independent hosted archive replay, the exact
601-request maximum, malformed/secret-bearing responses, raw-order and inventory
tampering, missing/skipped CI evidence, wrong artifact/ref/runtime and output
reuse. The saved provider page is used only as an offline parser fixture; the
synthetic archive is not historical market evidence.

Published code `03856c714ab8a819439808622483dc7294da46e2` passed
[full CI 34718443340](https://github.com/RoomyRems/momentumbot/actions/runs/34718443340):
2,816 tests in 426.973 seconds, 73 SDK skips, all 37 new integration tests passed,
and successful compilation. No duplicate local full suite ran.

[Capture run 34718443422](https://github.com/RoomyRems/momentumbot/actions/runs/34718443422)
is in progress, attempt 1, on that exact code. The permanent consumption ref
points to the code commit. Original preflight artifact `10305017350` is 6,320
bytes, ZIP SHA-256 `08b3e8b0138ee7672b8985ffd0c0addb3248fe17cf2ec3e1a13785c491afda38`.
Its original ZIP, file commitments, CI/ref/runtime and creation-before-capture
chronology were independently verified. The capture step is active; request and
completed-date totals remain unreported until retained results are available.

The separate verification job follows successful capture automatically. This
checkpoint records an active launch, not a completed census. Check this existing
run and its artifacts on continuation; do not rerun, dispatch or reuse its ref.
The evidence-only follow-up skips duplicate CI and changes no executable files.
Original artifacts and any failures must be preserved.
Successful census verification proves this capture protocol and its provenance;
it does not resolve all historical identities or establish financial performance.
Discretionary integration remains an essential unfinished part of the hybrid.
