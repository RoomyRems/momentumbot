# Integrated daily coverage and identity source capture

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
