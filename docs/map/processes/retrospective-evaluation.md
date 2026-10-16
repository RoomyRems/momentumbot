---
type: process
id: process-retrospective-evaluation
title: "Compare frozen runtime to retrospective labels"
cluster: research-boundaries
universe: live
entity: src/momentumbot/research/prospective_account_evaluation.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/prospective_account_evaluation.py:1-7", "src/momentumbot/research/prospective_account_evaluation.py:1251-1324", "src/momentumbot/research/prospective_account_evaluation.py:1332-1412", "src/momentumbot/micro_benchmark.py:164-188"]
status: verified
consumes: ["docs/map/objects/execution-account.md", "docs/map/objects/research-evaluation.md"]
produces: ["docs/map/objects/research-evaluation.md"]
---

# Compare frozen runtime to retrospective labels

The prospective evaluator joins separately frozen runtime and human labels to produce component and portfolio reports without changing replay decisions.

## Input → Movement → Output

Input is the preregistered contract, label-blind runtime bundle and a label bundle bound to its exact hash. The evaluator verifies chronology and identities, compares decisions and computes registered metrics across all cells. Output preserves both source hashes, runtime-freeze/label-open timestamps and the report's authority boundary.

## Why this shape

If labels can influence reconstruction, an apparent behavioral match is circular. The runtime validator rejects retrospective review already being started and forbidden label keys; the label validator requires a strictly later opening timestamp (`prospective_account_evaluation.py:1251-1324`). No raw transcript text is accepted in either bundle.

## Steps

1. Validate the frozen evaluation contract and runtime schema, parents, registered dates and no-effect/no-label boundary (`prospective_account_evaluation.py:1251-1284,1332-1346`).
2. Require labels to bind the same runtime hash and freeze time, with review strictly after freeze (`:1287-1324,1347-1356`).
3. Normalize runtime/session/human records and construct comparisons under their registered identities (`:1358-1373`).
4. Check identical candidate sets across cells; emit component metrics, portfolio metrics, decision comparisons and source provenance (`:1374-1412`).

The separate Micro comparator similarly checks runtime/label knowledge policies and symbol identity before comparison (`micro_benchmark.py:164-188`). Neither path is a weighted imitation optimizer or an automatic choice of the most favorable execution scenario.

## If you change this

- **Hits:** Report values, comparison coverage, denominators and interpretation. Changes need a versioned evaluation contract, not edits to a frozen historical result.
- **Does not hit:** Runtime decisions, candidate selection, provider requests or order authority. Results cannot establish performance for discretionary/source components that were not integrated into the evaluated run.

## Surfaces

| Surface | Role |
|---|---|
| Runtime bundle | Read-only causal evidence |
| Label bundle | Post-freeze human comparison evidence |
| Evaluator | Validates and joins without feedback |
| Report | Downstream metrics and provenance |

## See

- Objects: [Execution/accounts](../objects/execution-account.md), [research/evaluation](../objects/research-evaluation.md)
- [Owning source](../../../src/momentumbot/research/prospective_account_evaluation.py)
- [Micro comparator](../../../src/momentumbot/micro_benchmark.py)
