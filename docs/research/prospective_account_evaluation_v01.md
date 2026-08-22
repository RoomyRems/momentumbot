# Prospective account evaluation v0.1

## Purpose and registration state

This contract freezes how the August 24-September 4, 2026 prospective account
panel will be evaluated. It was registered on August 22, before the first panel
session, before any panel runtime or later price was available, and before any
Ross action label for the panel was opened.

The evaluator answers component questions rather than manufacturing one
"Ross score":

- Did the causal scanner/Micro chain acquire a documented completed trade?
- Did each account qualify it, emit a plan, and receive a modeled fill?
- On explicit trades and explicit skips, where did the modeled action agree or
  disagree?
- When entry and exit references are actually documented, how far apart were
  the modeled and reported times, prices, pullback ordinals, and reasons?
- If and only if a complete account-cell finishes flat with no unavailable
  input, what were its separately reported portfolio statistics?

It does not choose a metric, horizon, execution scenario, threshold, or policy.
It changes no runtime rule and grants no provider or broker authority.

## Frozen parents

The registration binds:

- account panel `ross-account-integration-panel-v0.1` and its ten dates;
- unchanged Micro-v0.1 fingerprint
  `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`;
- account chronological integration content SHA-256
  `64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73`;
  and
- prospective management/execution content SHA-256
  `14812b9f25b5ea7230254ed86b1e0eaa30fffe3dc13b1ee141b19770706090f9`.

The evaluation contract content SHA-256 is
`537287a04f35d81d8104f67a02cdcd352ee880cc8703fd8b8a61c68d971d5d5c`.

## Equal-report cells

Every horizon is crossed with both already frozen execution assumptions. All
six cells must retain the same candidate identity and are reported separately.

| Behavioral horizon | Conservative L1 | Stress L1 |
| ---: | --- | --- |
| 1 second | `h1s::l1-conservative-v0.1` | `h1s::l1-stress-v0.1` |
| 5 seconds | `h5s::l1-conservative-v0.1` | `h5s::l1-stress-v0.1` |
| 10 seconds | `h10s::l1-conservative-v0.1` | `h10s::l1-stress-v0.1` |

There is no winner field, best-cell rule, weighted imitation score, or
cross-cell portfolio aggregate. A favorable cell cannot be selected after the
results are known.

## Causal freeze and retrospective join

The evaluation has three distinct artifacts:

1. A label-blind runtime bundle contains all candidate/account/cell decisions
   and exactly 120 session records: six cells, two accounts, and ten dates.
   Every decision must bind the hash of its corresponding account session.
2. That complete runtime is frozen and content-hashed. Its timestamp and hash
   precede retrospective review.
3. A separate label bundle binds the exact runtime hash and freeze timestamp.
   Its label-open timestamp must be later. Only then can the deterministic
   report be built.

The runtime validator rejects human/Ross action fields, reported entry or exit
references, transcript text, and other retrospective-label keys even if the
bundle is rehashed. The label bundle persists normalized evidence hashes and
structured decisions, not raw transcript text. Neither labels nor the report
can alter runtime.

## Label meanings

Labels remain account-scoped. The allowed states are:

- `participated`: only a documented completed trade;
- `explicitly_skipped_or_rejected`: only an explicit no-trade decision;
- `discussed_but_action_unclear`: including an attempted order with no fill;
- `not_mentioned_or_unobservable`; and
- `source_unavailable`.

An unmentioned candidate is never converted to a skip. Attempted-but-unfilled
human activity is never converted to participation. Unclear, unmentioned, and
unavailable states are retained for coverage but excluded from trade/skip
agreement.

## Preregistered component outputs

Each account in each cell reports the following separately.

| Component | Descriptive outputs |
| --- | --- |
| Candidate acquisition | Observed completed trades, evaluable completed trades, acquired completed trades, acquisition fraction |
| Account participation | Qualified acquired trades, fill-evaluable acquired trades, fills on human trades, fills on explicit skips, explicit trade/skip agreement |
| Entry alignment | Every signed time delta and every signed, absolute, and percentage price difference; pullback-ordinal equality only when both are known |
| Exit alignment | Every signed time delta and every signed, absolute, and percentage price difference; exact reason equality only when both are known |
| Activity | Candidates, candidates with plans, total plan emissions, fills, closures, unresolved or unavailable cases |

If the human evidence gives multiple entry or exit times or prices, the report
retains every pairwise comparison against the modeled first fill or exit. It
does not pick the closest reference. Empty or unknown references remain empty;
zero is not inferred.

An incomplete runtime session is not treated as a negative decision. It is
removed from the relevant acquisition and trade/skip denominators. A complete
session with a documented human trade that the causal candidate chain did not
acquire remains an acquisition miss.

## Conditional portfolio outputs

Portfolio fields are released only for an individual account-cell when all ten
registered session records exist, every session runtime is complete, the final
open-position count is zero on every date, and no required input is marked
unavailable. If any condition fails, every financial interpretation field for
that account-cell is `null`; other complete account-cells remain independently
evaluable.

Eligible cells report:

- gross realized P&L and registered fees;
- net P&L after registered fees and net return on panel starting equity;
- closed-campaign count, win rate, and gross expectancy;
- gross profit factor, with no-loss cases retained as undefined rather than
  infinity; and
- gross maximum realized drawdown in chronological campaign order.

These are conditional outputs of two fixed, uncalibrated execution-assumption
scenarios. They are not broker-fill claims, profitability proof, or permission
to promote a policy.

## Deterministic use

After both source bundles exist:

```bash
PYTHONPATH=src python scripts/evaluate_prospective_account_panel.py \
  --runtime path/to/frozen-runtime.json \
  --labels path/to/frozen-labels.json \
  --output path/to/write-once-report.json
```

The command validates both parents, builds the report, independently validates
all structural identities and recomputed aggregates, and writes the output
once. It performs no network or provider call and reads no credential.

## Current status and next gate

The contract, evaluator, CLI, and deterministic adversarial tests are
implemented, but the panel has not started and no retrospective label or P&L
has been loaded. The harness is therefore preregistered and unrun.

The next gate remains operational: preserve each registered label-blind daily
source, account snapshot, opportunity freeze, and causal market-input chain.
After all ten dates finish, freeze the complete six-cell runtime first. Only
then open structured retrospective evidence and run this evaluation. A larger
representative walk-forward remains required before any promotion or
profitability interpretation.

Files:

- Contract: `research/strategy/prospective-account-evaluation-v0.1.json`
- Evaluator: `src/momentumbot/research/prospective_account_evaluation.py`
- CLI: `scripts/evaluate_prospective_account_panel.py`
- Tests: `tests/test_prospective_account_evaluation.py`
