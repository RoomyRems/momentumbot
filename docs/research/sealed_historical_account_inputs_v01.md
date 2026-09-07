# Historical account and management inputs v0.1

The user approved hypothetical starting equity and equal buying power of
$30,000 for main and $2,000 for small, with profits, losses and positions carried
through the exact 30 registered sessions. This child records that decision and
builds its deterministic input plan against availability checkpoint
`1f7c83b11d6fa26f600cbe37c16c9eed14fb7bb2`, tree
`dcf71e6bc1df1f7c10f2c38b2a9a4258c1f5431f`.

The hypothesis is that these once-only seeds and the existing management-window
rules can define the historical inputs without resetting accounts or replacing
unavailable opportunities. No source market outcome, Ross action, transcript,
recap label or P&L is used to choose balances, dates, windows or policies.

## Approved account inputs

| Account | Initial equity | Initial buying power | Frozen campaign risk cap | Frozen notional cap | Frozen daily loss limit |
|---|---:|---:|---:|---:|---:|
| Main | $30,000 | $30,000 | $75 | $15,000 | $300 |
| Small | $2,000 | $2,000 | $5 | $1,000 | $20 |

These first-session limits come directly from the unchanged paper-account
policy: 0.25% open risk, 50% position notional, 1% daily loss, one open position,
at most two accepted campaign entries and 50% profit giveback. The seeds are
explicit research inputs, not historical broker snapshots. No account endpoint
or real account identifier is needed.

There are 12 independent paths: two accounts, three behavioral horizons and two
execution scenarios. Each path contains all 30 dates, giving 360 session-input
slots. Exactly 12 slots use an initial seed; the other 348 require the preceding
registered session's close for the same path. The plan retains all 744
profile/cell opportunity references and all 162 unavailable references, which
represent the original 23 unique unavailable opportunities. Every no-decision
date remains present in each path.

## State handoff

`account_state_input` verifies the target slot, exact previous session identity,
same account/horizon/scenario, original close commitment and source-runtime
commitment. It copies the complete supplied account state: equity, buying power,
cumulative realized result, cumulative fees, positions, pending orders, campaigns
and unresolved inputs. Missing fields or prior closes fail closed. Unknown and
insolvent balances remain explicit; they cannot become the starting seed again.
The returned state does not share mutable collections with the prior evidence.

This function verifies transport and chronology. It does not establish that a
supplied close is an executed account result. A later registered runtime must
validate that close's producer and its execution evidence. It must also establish
causal session-start valuations, apply the existing daily risk policy, and carry
open positions and unresolved state without inventing prices or resetting
capital. The planner supplies no later-date equity, buying power, risk limits,
account results or fabricated flat state.

## Management input plan

The unchanged management merger projects all 109 opportunities, including all
23 unavailable entry inputs, into 56 merged symbol/date windows. Each window
requires two logical resources: raw SIP one-minute bars and SIP transactions,
giving 112 logical resource requests before pagination or source reuse.

For every opportunity, the source window begins at the UTC minute containing
its exact decision timestamp. The signal window ends 900 seconds after the
decision, with a 60-second observation tail. The request end remains exclusive.
All nanoseconds stay exact integers. Overlapping or touching requests for the
same symbol/date are merged with the frozen helper; disjoint windows remain
separate. Every opportunity retains its individual bounds and original
availability reason, even when multiple windows share one provider request.

The plan does not establish missing source coverage or authorize 112 HTTP calls.
The next stage must verify the retained SIP/minute artifacts and their exact
normalization and coverage for reuse, then register any remaining bounded
capture. Provider pagination, call budgets and actual acquisition remain outside
this provider-free child. No date, symbol or opportunity may be substituted.

The existing `half-2r-breakeven-first-red-1m` projection remains descriptive SIP
transaction evidence. It cannot book executable sell fills, close account
positions, calculate portfolio returns or invent a liquidation at the window
end. Exit execution and causal next-session valuation therefore remain separate
requirements after the management inputs are verified.

## Verification and operation

The entry point installs the existing network/subprocess audit guard before
importing the planner. It only reads registered local parents. Composition is
write-once; verification reconstructs all five files from those parents and
rejects changed bytes even if a modified document has been rehashed.

```bash
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_inputs_v01.py --validate-registration
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_inputs_v01.py --build
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_inputs_v01.py --verify
```

The committed plan lives in
`research/runtime/sealed-historical-account-management-inputs-v0.1/`:
`account-seeds.json`, `account-session-input-plan.json`,
`management-request-manifest.json`, `readiness-report.json` and
`freeze-manifest.json`. The registration is
`research/strategy/sealed-historical-account-management-inputs-v0.1.json`.

Synthetic tests exercise complete 30-session handoffs, profit/loss and open-state
preservation, missing parents, path swaps, resets, changed commitments, currency
validation and unavailable inputs. Actual-input tests verify all frozen
opportunity identities, exact management bounds, profile membership and file
reconstruction. Dedicated CI reconstructs the committed plan under CPython
3.12.14 with the existing 29 hash-locked packages and runs the focused tests
normally and optimized.

No account or fill simulation, management projection, retrospective access or
backtest is executed by this stage. Acquisition, account-runtime, management,
historical-execution and portfolio-metric gates remain false.

## Independently verified input plan — 2026-09-07

The write-once build and full reconstruction produced identical verification
reports. An independent stdlib checker, with no runtime imports and with network
and subprocess access blocked, verified every file and content commitment,
the approved seeds, all session dependencies and every individual and merged
management-window bound.

| Verified input | Result |
|---|---:|
| Frozen files / total bytes | 5 / 857,974 |
| Account paths / session-input slots | 12 / 360 |
| Initial seed slots / prior-close dependencies | 12 / 348 |
| Profile and scenario opportunity references | 744 |
| Unavailable references / unique opportunities | 162 / 23 |
| Global no-decision session slots | 60 |
| Merged management windows / logical resources | 56 / 112 |

The freeze-manifest content commitment is
`9c72aa77268795153ec12ebf5d3b3d2d11defada69325e867f3af814ad8e75f3`.
The [permanent audit](../../research/data-audits/sealed-historical-account-management-inputs-v0.1-independent-verification.json)
retains both verification reports, the independent checker source, all five
file hashes, the implementation hashes and the checked parent references.

All 1,632 repository tests passed locally with zero skips under CPython 3.12.13
and the existing 29 hash-locked packages. The 72 focused tests passed both
normally and with Python optimization enabled. The entry-point undefined-global
check also passed. GitHub Actions records validation against the publishing
commit separately.

The next registered dependency is
`verify_retained_management_source_reuse_and_register_bounded_missing_input_capture`.
The account-state function remains input transport; no historical close,
executable exit, next-session valuation or portfolio result has been produced.
