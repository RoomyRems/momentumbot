# Historical execution input availability v0.1

This provider-free child composes an explicit input classification and quote
window for every one of the 109 frozen Micro opportunities. Its parent is
`24aaa19c50a39bce43ef9491f7630e2a81e330f8`, tree
`fe4e82282cf50eeb855937f27a6222e80fd2aec6`: the independently verified execution
acquisition v0.3 checkpoint. The hypothesis is that the exact retained evidence
can be composed without replacing inputs or changing policy. Ross actions,
fills, recap labels, transcript contents and later price outcomes are prohibited
inputs. The attached corpus remains sealed.

## Frozen sources and mechanics

The registration pins both original GitHub artifact ZIPs from run 34084113393,
the independent audit, execution parent, input manifests and all directly used
capture and decision-reference mechanics. The loader verifies both archives,
all 161 outer files, the embedded parents and the original acquisition verifier's
exact confirmation before admitting any records. The source population is 89
complete tapes and one confirmed unavailable JVA quote request. No provider
request, re-quote, source replay or Micro execution is part of this operation.

Every opportunity retains its original identity, date, decision time, source
commitments and profile eligibility. Each window uses the existing record-order
adapter unchanged: inclusive decision minus 100 ms through decision plus
550 ms, backed by the original exclusive request end. The quote request's
original record ordinal, receive timestamp, sequence and native values survive
filtering. Quotes tied in receive time to a status event remain ambiguous;
unknown initial or subsequent window status fails closed.

The decision reference uses the unchanged daily-account helper: the last usable
quote in the inclusive 100 ms before the decision, never a post-decision quote.
A known halted reference remains a distinct `halted` state. This stage reports
quote-associated status exactly as the frozen adapter does; it introduces no
additional status inference or order eligibility rule.

Each opportunity receives one explicit reason: causal reference/window
available, known halted reference, missing exact quote request, missing exact
status request, unknown causal status, or no fresh decision quote. Complete
request evidence does not establish that every opportunity has usable inputs.
JVA remains unavailable without inventing an empty normalized tape, a resting
quote, a zero-trigger result or a no-trade result.

## Operation and verification

`research/strategy/sealed-historical-execution-input-availability-v0.1.json`
registers the contract. The entry point denies network and subprocess I/O and
requires both exact retained ZIPs:

```bash
PYTHONPATH=src:scripts python scripts/compose_sealed_historical_execution_availability_v01.py --validate-registration
PYTHONPATH=src:scripts python scripts/compose_sealed_historical_execution_availability_v01.py --compose --result-zip /exact/result.zip --consumption-zip /exact/consumption.zip --output-root research/runtime/sealed-historical-execution-availability-v0.1
PYTHONPATH=src:scripts python scripts/compose_sealed_historical_execution_availability_v01.py --verify --result-zip /exact/result.zip --consumption-zip /exact/consumption.zip --output-root research/runtime/sealed-historical-execution-availability-v0.1
```

Composition is write-once. It emits 30 deterministic compressed date documents
and one manifest with source evidence and logical/physical hashes. All five
no-decision dates remain explicit. Verification independently reconstructs every
window from the original archives and requires identical output bytes; changing
and rehashing the report cannot pass. Synthetic integration tests cover all
109 identities before the real composition. The dedicated workflow validates
registration and focused mechanics under pinned CPython 3.12.14 without secrets.

Preparation validation passed 81 focused tests normally and optimized, all
1,610 repository tests with zero skips, offline registration rederivation, and
undefined-global checks. No actual opportunity availability outcomes were
computed before publication of this registration.

## Remaining boundary

Availability is an input fact, not approval to submit or simulate an order. All
acquisition, historical execution, management and account gates remain false.
No sizing, fills, account state or P&L is computed. The 550 ms windows do not
provide minute-level trade management or exits.

The next dependency is separately registered historical account and management
input resolution, preserving every unavailable opportunity. Any later account
runtime must carry state across the full 30 dates for each frozen account,
horizon and scenario; it cannot reset accounts daily or infer unavailable trades.

## Independently verified result — 2026-09-07

Code registration `d0c5c993973f7e04e9e97bca98795fb576a94799`, tree
`12b5294f1f063d9da12942bfd398ddf4b824e533`, passed
[CI 34090713573](https://github.com/RoomyRems/momentumbot/actions/runs/34090713573)
and [pinned validation 34090713599](https://github.com/RoomyRems/momentumbot/actions/runs/34090713599)
before the single local offline composition. Both hosted runs completed on push
attempt 1. Dedicated validation passed 81 tests in each mode with zero skips;
the broad hosted CI passed 1,610 tests with 51 optional SDK skips. The full local
suite passed all 1,610 tests with zero skips.

The output retains every frozen opportunity:

| Input classification | Opportunities |
|---|---:|
| Usable causal reference and window | 86 |
| No usable quote in the inclusive 100 ms before the decision | 22 |
| Confirmed missing exact JVA quote request | 1 |
| Known halted reference | 0 |
| Unknown causal status | 0 |

The general profile has 78 available and 21 unavailable decisions; the small
account profile has 19 available and six unavailable decisions. Profile counts
overlap because 15 opportunities belong to both profiles. No missing reference
was filled from a later quote or an older resting quote. These classifications
describe input availability and are not trade or performance results.

All 108 composed windows have known status coverage. There are 7,623 retained
quote occurrences, preserving original request ordinals, across 30 compressed
date files. The five no-decision dates remain June 3, 5, 16, 17 and 20, 2025.
The 31 output files total 360,499 bytes. Manifest content SHA-256:
`9fd935aa16caef6a823ab6a44c4f7e864e47231cf7189b7feb4069ac179bb6d4`.

Full reconstruction from the original ZIPs reproduced every output byte. A
separate stdlib verifier imported no runtime code and independently checked
source tape bytes, quote selection, causal status, decision references, all
identities, summary counts and the entire physical inventory. Its source and
results are retained in
`research/data-audits/sealed-historical-execution-input-availability-v0.1-independent-verification.json`.
The local operation used CPython 3.12.13, zlib 1.3.2 and all 29 hash-locked
package versions; hosted preparation used CPython 3.12.14. Both local verification
processes denied network and subprocess I/O.

The nine protected parent refs, original 30,522-request source ledger and all
retained acquisition artifacts remain unchanged. The monitor was not changed.
All 23 unavailable inputs are explicitly listed in the audit for the next
registered input-resolution stage. Acquisition, historical execution, account,
management and trading gates remain false. No Micro replay, order/fill simulation,
account execution, retrospective access or backtest ran.
