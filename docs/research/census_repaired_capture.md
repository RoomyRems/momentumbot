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
completed successfully at **2026-09-12 22:24:37 UTC**, attempt 1, on that exact
code. All three jobs and every step passed. The consumption ref still points to
the code commit. The previous active-launch observations remain in the audit
directory alongside the new terminal observations.

| Verified result | Count |
|---|---:|
| Registered dates fully exhausted | 30 / 30 |
| Membership pages | 390 (13 per date) |
| Membership rows across dates | 373,710 |
| Requests, all complete HTTP 200 | 391 / 601 maximum |
| Current type dictionary | 1 request, 24 rows |
| Retries | 0 |
| Independently verified archive members | 1,567 |

The membership count includes repeated securities on different dates; it is not
a unique-security count. Transport took 81 minutes 15.204 seconds, with a minimum
observed request-start interval of 12.500087837 seconds. The whole workflow,
including its same-code CI wait, completed in 90 minutes 4 seconds.

The separate verifier replayed every original raw page and checked normalized
bytes, intent/receipt chains, pacing, terminal pagination, GitHub provenance and
the independently supplied inventory pin. Verification made zero provider
requests. Its sealed result is
`ce60ba0657ac1f0706afea4476f2ecbf48e08a99414dd30997e3e49ae8dbab07`.
The September 13 status check downloaded all four original artifacts, confirmed
their GitHub byte sizes/digests, verified result/link seals and independent pins,
and checked retained receipt and date totals. It reused the successful hosted
protocol replay; no duplicate full replay, CI run or provider capture was started.

| Original GitHub artifact | ID | ZIP bytes |
|---|---:|---:|
| Consumption/preflight | 10305017350 | 6,320 |
| Launch | 10307150746 | 7,915 |
| Capture | 10306971164 | 30,807,928 |
| Verification | 10306378431 | 6,445 |

The original capture ZIP SHA-256 is
`38d772b2017c159050c4cef2a678a79af1fd61f243e8131f5112d1ef25b09ded`;
its inventory file SHA-256 is
`493e15337421d777f1fa210716478d88f0ca9765d1c526719575435c6434d05b`.
The raw ZIP remains GitHub artifact `10306971164`, currently expiring
**2026-12-11 20:54:33 UTC**; it is not committed to git and longer retention is
not claimed. Preserve that exact source before expiration when integrating the
historical inputs. Small original ZIPs, logs, final GitHub metadata, capture report
and sealed completion observation are retained under
`research/data-audits/early-pullback-census-repaired-v0.3/`.

## Remaining integration work

Capture completeness is established. Historical security identity still requires
resolution before scanner/replay admission: each date has two canonical ticker
collision groups, and rows have missing CIK/FIGI fields. March 6 also has one
missing type code. These records remain explicit; they were not silently merged
or assigned identities. The current type dictionary is not historical identity
proof. Actual billing remains unverified.

Use the frozen capture for identity and scanner-input integration next. Do not
rerun, dispatch or reuse the consumed census authorization. This evidence-only
follow-up uses `[skip ci]` and changes no executable or registered files.
Successful capture does not establish financial performance or complete the
hybrid strategy; crucial discretionary integration remains unfinished.
