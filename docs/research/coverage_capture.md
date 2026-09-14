# Integrated daily coverage and identity source capture

## Observed hosted outcome — September 14

Code [`af48e9f`](https://github.com/RoomyRems/momentumbot/commit/af48e9f7761d80684683da02c5ef5b9bcdd800d8)
passed [full CI](https://github.com/RoomyRems/momentumbot/actions/runs/34799137938):
2,903 tests in 450.045 seconds, 73 optional SDK skips, compilation and every
job/step successful, attempt 1. The six supporting validation workflows passed.

[Capture 34799137954](https://github.com/RoomyRems/momentumbot/actions/runs/34799137954)
consumed its authorization and completed all 46 daily roots for March 4, covering
5,520 metadata candidates, of which 5,518 satisfy the frozen coverage booleans.
The first corporate-action request then returned complete HTTP 200 with 1,000
unique IDs and a next cursor. Every populated group has process-date regressions,
contrary to the ordering assumption enforced by this version. The code rejected
the page as `action date regression`. No retry or subsequent provider request ran.
This is a provider ordering/adapter mismatch, not an authentication failure.

All 47 raw bodies were retained. Offline failure verification checked the exact
original ZIPs, independent preflight/CI/ref bindings, all 144 capture members,
every intent/receipt, all 46 daily responses through the frozen replay, and the
same final rejection/report. The observed process-date range remains within
November 4, 2025–March 4, 2026. The safe rejected body is 217,339 bytes, SHA-256
`5134b32e21dc1de6f02d4872e025331440638fe2dcf150284a79ffbb8124e09a`.
The original capture ZIP is GitHub artifact `10330669089`, 3,493,487 bytes,
SHA-256 `1d7edc9a9458b290320b5cd2963d911037d3c2b8d60bd86e01ef001a6528861a`.
Machine verification, metadata, CI/capture logs and the rejected action body are
in `research/data-audits/early-pullback-coverage-capture-v0.1/`.

The run is terminal and permanently consumed. Automatic successful-capture
verification was correctly skipped. The later offline check authenticates and
reproduces a partial failure; it does not accept a complete historical source.
Next create an additive ordering repair and continuation that reuses the retained
successful prefix and action page, then fetches only the remaining suffix after
same-code CI. This failed contract/code stays immutable. No new policy or risk
authority follows from the diagnosis. Actual billing remains unverified.

## Original implementation checkpoint

Child of `e23fbe16432e863c1c8b6b9c6778129ac60bf3f6`, whose full CI
[34794323593](https://github.com/RoomyRems/momentumbot/actions/runs/34794323593)
completed successfully on attempt 1, including tests and compilation.

This batch connects the frozen daily coverage replay to bounded HTTPS transport,
raw-response retention, corporate-action validation, and automatic independent
original-ZIP replay. No strategy threshold, risk rule, transcript input, account
evaluation or historical scanner runtime changes. The hypothesis is that the
fixed reference panel can acquire and reproduce complete dated source evidence.

## Fixed scope and limits

The exact byte-pinned 30-date panel supplies 1,380 unchanged daily request roots.
Each uses raw or split daily SIP bars, target-date `asof`, a 250-symbol batch and
the inherited 14-day window. The 60 identity roots use the previously defined
120-day Alpaca corporate-action and Massive stock-split queries. Dates, candidate
selection and query populations are unchanged.

| Limit | Value |
|---|---:|
| Daily pages per root | 10 |
| Identity pages per root | 20 |
| Total HTTP attempts | 15,000 |
| Response body | 16 MiB |
| Payload retention | 1,500,000,000 bytes |
| Metadata retention | 80,000,000 bytes |
| Reserved final report space | 200,000,000 bytes |
| Alpaca minimum start interval | 0.35 seconds |
| Massive minimum start interval | 12.5 seconds |
| Internal capture deadline | 150 minutes |
| Hosted capture job timeout | 180 minutes |

These are ceilings, not expected request totals. Pagination follows only returned
cursors; duplicate cursors, empty nonterminal pages, changed scope and exhaustion
beyond the limits are failures. There are no retries, redirects, proxies,
credential fallbacks, symbol-removal retries, subscription changes or brokerage
endpoints. The operational cost ceiling is $10, estimated incremental API cost
$0; billing enforcement, account entitlement and credit balance are unverified.
No metered purchase is implemented or authorized by this contract.

## Retention and independent verification

An intent is fsynced before each HTTP attempt. Every credential is checked against
raw and decoded JSON strings before retention, including overwritten duplicate
keys. Safe JSON is saved before schema validation, including safe HTTP-error and
incomplete JSON responses. Uninspectable or credential-bearing bodies are withheld;
sanitized receipts retain hashes and bounded status information. Exceptions never
print credentials, provider messages or URLs containing credentials. A failed run
stops once and preserves its report/inventory; it cannot resume or restart.

Alpaca actions require known requested groups, unique IDs and ordered process
dates within each group and the fixed query window. Optional future payment fields
are preserved as source data, without granting historical availability authority.
Massive splits require unique IDs, positive factors, bounded execution dates,
date/ticker ordering, and exact safe continuation origin/path/query parameters.
Action rows stay in original responses; the report commits their normalized count
and hash. An action-source capture does not itself establish security continuity.

The workflow has three jobs. `consume` requires full CI on its exact new code
commit, creates a new permanent consumption ref, and uploads an independent
preflight artifact. `capture` verifies its independent artifact ID/inventory,
current consumption ref, code, runtime and panel before reading credentials.
`verify` has no provider credentials; it fetches original preflight/capture ZIPs,
checks GitHub artifact/job identities and independent hashes, replays every raw
response and reproduces the complete report. Failed captures retain evidence but
cannot receive successful verification. The original census consumption is untouched.

Registration: `research/strategy/early-pullback-coverage-capture-v0.1.json`.
Workflow: `.github/workflows/coverage-capture.yml`. Publishing that new registration
on the active branch starts the gated workflow under the owner's continuation
authorization; credentials remain blocked until same-code CI succeeds. Artifacts
request 90-day retention. No longer retention is claimed.

## Validation and remaining work

Focused tests cover a synthetic complete 30-date capture and original archive
replay, the full hosted preflight/capture/verifier path, immutable query scope,
cursor/date/ID/ratio validation, exact 1,380-root published panel, preserved failures,
credential echoes, tampering despite regenerated hashes, HTTP failures, deadlines,
credential-read gates, and workflow permissions. Run normally and under `python -O`.
The full local suite is not duplicated; hosted CI is authoritative for the code.

All 87 focused tests passed normally (9.688 seconds) and optimized (10.713
seconds), including 28 new tests. Compilation and whitespace checks passed.
The local verification record is retained in the capture audit directory.

Provider schema references: [Alpaca models](https://github.com/alpacahq/alpaca-py/blob/master/alpaca/data/models/corporate_actions.py),
[Alpaca corporate actions](https://docs.alpaca.markets/us/reference/corporateactions-1),
[Massive splits](https://massive.com/docs/rest/stocks/corporate-actions/splits).
Current historical corporate-action records are not an as-known announcement feed.
The Massive cumulative historical adjustment factor is retained as evidence, not
applied to historical runtime prices by this step.

After successful capture and independent verification: resolve the dated identity
and corporate-action evidence, feed complete coverage into the existing bridge,
then construct the remaining cross-sectional scanner inputs. The full hybrid's
discretionary/context integration remains unfinished; this stage makes no profit claim.
