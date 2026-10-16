---
type: object
id: object-research-evaluation
title: "Frozen research and retrospective evaluation"
cluster: research-boundaries
universe: live
status: verified
entity: src/momentumbot/research/prospective_account_evaluation.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/prospective_account_evaluation.py:1-7", "src/momentumbot/research/prospective_account_evaluation.py:1251-1284", "src/momentumbot/research/prospective_account_evaluation.py:1287-1324", "src/momentumbot/research/prospective_account_evaluation.py:1332-1412", "src/momentumbot/micro_benchmark.py:1-9"]
---

# Frozen research and retrospective evaluation

The evaluator joins separately frozen runtime and retrospective labels; it reports components without turning human hindsight into a replay input.

## Why this shape

An attractive match to Ross after the fact is not a causal trading rule. Runtime must be frozen before review begins, and the label bundle must bind that exact runtime hash and a strictly later opening time. Both sides forbid raw transcript persistence and runtime strategy effects (`prospective_account_evaluation.py:1251-1324`). These checks preserve the direction of evidence flow rather than merely naming a file “label-blind.”

## Shape

The prospective evaluator validates its contract, runtime decisions, session performance and human decisions; then joins comparisons and emits component and portfolio metrics. It requires the identical candidate set across registered evaluation cells and retains source hashes and freeze/review timestamps (`:1332-1412`). It does not select an execution cell or manufacture a weighted imitation score (`:1-7`). The smaller Micro benchmark follows the same downstream-only concept (`micro_benchmark.py:1-9`).

These implementations belong to their frozen panels. They are not automatically the authorized evaluator for the still-unintegrated new real-source panel. Historical failures and incomplete-source results remain evidence about the components actually exercised, not a verdict on an unbuilt hybrid or a promise of eventual profitability.

## Connected to

- **owns:** Comparison records, registered metrics, label timing and report provenance.
- **owned-by:** Frozen evaluation and label-policy contracts.
- **joins:** Immutable [Micro](micro-replay.md), [account](execution-account.md) and applicable [shadow](context-shadow.md) evidence after runtime freeze.
- **looks-like-but-is-not:** A training signal injected during replay, policy selector or live-performance claim.

## If you change this

- **Hits:** Metric definitions, comparison denominators, evidence interpretation and report fingerprints; comparisons need revalidation under their own versioned contracts.
- **Does not hit:** Existing runtime decisions, source capture, scanner thresholds, risk limits or order permission. Report quality cannot repair unavailable original data.

## Surfaces

| Surface | Role |
|---|---|
| Runtime bundle | Read-only causal decision/session evidence |
| Retrospective label bundle | Separately frozen comparison evidence |
| Evaluation report | Downstream output with bound sources |
| Runtime engines | No feedback channel from this evaluator |

## See

- [Owning source](../../../src/momentumbot/research/prospective_account_evaluation.py)
- [Micro benchmark](../../../src/momentumbot/micro_benchmark.py)
- [Retrospective-evaluation movement](../processes/retrospective-evaluation.md)
