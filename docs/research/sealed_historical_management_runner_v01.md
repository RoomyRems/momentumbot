# Historical position runner and common exit inputs v0.1

This isolated child of `d9e5a04b6f9f78ba09fc87c53be2e7b9aa359b89` registers
the causal position scheduler and its exact common quote/status requirements.
The hypothesis is that orchestration preserves original source ordering and
uses only confirmed fill feedback. Tests use synthetic inputs. Historical
account-state production, fees, valuation, account reconciliation and execution
activation remain unresolved; this is not a completed account backtest.

## Exact exit-input scope

All 109 original opportunities are retained. The 86 with available entry inputs
map to 41 symbol/date groups. The 23 unavailable opportunities keep their exact
availability reasons and have no exit-input group. Availability does not imply
an accepted entry, and account size, scenario, later prices and Ross labels do
not select the request population.

Each group uses one complete `XNAS.ITCH` `mbp-1`/`status` pair with the frozen
`raw_symbol` identity and original record-order adapter. Its required quote
interval starts 100 ms before the earliest available original decision and ends
at the latest original management window's exclusive end. Status begins at
that UTC date's midnight and shares the quote end. All arithmetic uses integer
nanoseconds. Group coverage includes intervening gaps because all positions in
that symbol/date use one stable complete source and its original ordinals.

The original `2025-07-15` XAGE entry pair already spans its group's complete
required interval. It is registered as a reuse candidate with its original
request bytes and hashes. Exact retained tape verification is still required;
interval containment alone is not a verified source receipt. The other 40
groups require **80 new exact requests**. A future metadata quote has a ceiling
of 160 calls (billable size and cost per new request). No quote, purchase,
download, credit authorization or cost estimate is performed here.

The new source never replaces the original entry tapes or rescues an unavailable
entry. Each position retains its own original management bounds even when its
common source is longer. The earliest possible exit print follows the fastest
frozen entry arrival by at least one nanosecond. A sell intent must leave room
for the unchanged 550 ms capture tail plus the exclusive-end nanosecond. Later
signals remain explicit input failures; the original window is never extended.

## Causal orchestration

`run_position_mechanics` binds the existing entry evidence and consumes the two
canonical management streams through a streaming merge. It validates original
per-source order and ordinal continuity instead of sorting or deduplicating
records. Bars become eligible at their completed-minute timestamp. At equal
timestamps the order is completed bars, all original SIP prints, then feedback.

The scheduler reads no private precomputed execution outcome. It schedules
feedback using public order arrival/cancel timings and the quote source's
receive timestamps. Delayed quote fills therefore update the position at their
actual feedback clock, even if no later SIP print arrives. A print tied with a
target fill cannot use the resulting breakeven stop; a print tied with cancel
acknowledgment cannot clear that pending reservation early.

The frozen reducer still controls whole-share quantities, partial fills,
one-share handling, target/stop/red priorities, one target and one terminal
attempt, cancellation reservations and non-reusable displayed liquidity.
Unfilled terminal shares remain explicitly open. The scheduler settles through
the last nanosecond of the original window and invents no liquidation.

Each source has a row count and SHA-256 commitment over canonical lineage
envelopes, one JSON object plus newline per record. The full streams must match
before a successful result is returned, including records after share closure.
Malformed, reordered, truncated or interrupted inputs raise `RunnerInputFailure`
with the last state and any outstanding intent. Missing exit quotes retain the
confirmed entry and unresolved order intent. They are not zero-trade outcomes.

## Trust and activation boundary

`resolve_registered_context` derives the original opportunity and account slot
from verified frozen catalog bytes and compares the decision payload to the
original decision commitment. A caller's replacement context hash cannot alter
the original stop, profile membership or slot. This authenticates context only;
it does not authenticate a preceding account state or an execution producer.

The mechanics function separately requires caller-pinned streams, common scope
and full exit tape. Such pins establish input identity, not historical producer
authority. Its output explicitly disclaims account-close and financial-metric
eligibility. Historical use still requires independently verified original entry
sources, `ManagementInputBundle` lineage, common exit sources, and a registered
account producer enforcing once-only seeds, scarcity and carried state.

`require_historical_runtime_ready` rejects the unresolved registration. There is
no `authorized=True` override or CLI historical-run mode. Source verification,
historical fees, sell-ledger reconciliation, next-session valuation, continuous
account/order integration and an authorized execution child are explicit gates.
The August 2026 fee defaults cannot stand in for the 2025 fee schedule.

The four metadata documents preserve all 30 dates, 12 account paths, 360 slots,
744 opportunity references (162 unavailable), 12 initial seed applications and
348 preceding-close dependencies. The approved $30,000/$2,000 seeds, policies,
original captures, failures and consumed references remain unchanged.

## Reproduction and next gate

Registration lives at `research/strategy/sealed-historical-management-runner-v0.1.json`.
Metadata lives at `research/runtime/sealed-historical-management-runner-v0.1/`.
The CLI installs external-I/O denial before importing research code:

```bash
python scripts/build_sealed_historical_management_runner_v01.py --validate-registration
python scripts/build_sealed_historical_management_runner_v01.py --verify
```

`--build` writes only to an absent output. Verification reconstructs every byte.
Hosted validation uses the hash-locked environment, read-only permissions,
normal/optimized tests and no provider credentials.

Next: verify the exact retained XAGE common source and register the bounded
metadata quote for the 80 remaining requests. Any acquisition follows its own
successful exact quote, tested bounded transport and durable consumption gate.
The account-integration dependencies above remain explicit before replay.

## Local validation

All 1,865 tests passed in 106.660 seconds with zero skips. The 141-test focused
group passed normally (24.268 seconds) and optimized (24.022 seconds), including
45 new tests and 50 seeded synthetic share paths. Static undefined-global checks
passed for both entry points. No historical source tape or retrospective input
was loaded to define or test these mechanics.

The primary verifier reconstructs all four metadata files exactly. An independent
stdlib-only checker verifies literal ancestor hashes, complete inventories, all
original opportunity/date/account fields, integer interval algebra and every
new/reused request field. It independently checks 16 committed synthetic traces
for executable prices, fill clocks, equal-time behavior, shares and cancellations.
The [synthetic vectors](../../research/data-audits/sealed-historical-management-runner-v0.1-synthetic-vectors.json)
were also regenerated byte-for-byte. The registration freeze content commitment
is `77452867363127a9234ddbf1b27702d38b15477911454a448b680b6a9d6b1366`.

## Hosted verification and permanent audit

Code `cd6e76e42dd91455da7ef4a8bb1aa571767f13e2`, tree
`4ba7ef8bacf4e87367aa89c7911b361f9a92adf6`, passed all eight hosted workflows
on attempt 1. [Dedicated run 34167219406](https://github.com/RoomyRems/momentumbot/actions/runs/34167219406)
reconstructed the exact metadata and passed 141 tests normally and optimized
with zero skips. [CI run 34167219324](https://github.com/RoomyRems/momentumbot/actions/runs/34167219324)
passed 1,865 tests with the generic environment's 51 optional-SDK skips.
Every validation step succeeded and all provider acquisition/probe jobs remained
skipped. Main and all 14 retained historical consumed references are unchanged.

The [permanent audit](../../research/data-audits/sealed-historical-management-runner-v0.1-independent-verification.json)
records both verifiers, complete local log commitments, environment evidence,
hosted runs/jobs/log excerpts, exact interval and population checks, and embedded
reproducible checker/generator sources. XAGE reuse remains conditional on exact
retained bytes, costs remain unquoted, and historical/account activation remains
blocked by the dependencies above.
