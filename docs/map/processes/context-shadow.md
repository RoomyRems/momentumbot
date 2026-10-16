---
type: process
id: process-context-shadow
title: "Assess frozen context without trading effects"
cluster: discretionary-context
universe: live
entity: src/momentumbot/research/context_semantic_shadow.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/context_semantic_shadow.py:202-266", "src/momentumbot/research/context_semantic_shadow.py:608-686"]
status: verified
consumes: ["docs/map/objects/context-shadow.md"]
produces: ["docs/map/objects/context-shadow.md"]
---

# Assess frozen context without trading effects

This movement applies the frozen semantic rubric to a validated decision snapshot and emits descriptive axes or explicit abstentions.

## Input → Movement → Output

Input is a causal structured context snapshot, frozen rubric hash, generation timestamp and label-blind run identifier. Deterministic rubric functions interpret the available evidence and validate the resulting shadow assessment. Output is a time-limited assessment and hashed date payload with no strategy effect or promotion eligibility.

## Why this shape

Subjective context can be studied without giving it a hidden route into selection or risk. The rubric validator prohibits later prices, trade outcomes, Ross actions and retrospective labels. Its generation contract also makes clear that the authoring-model name describes provenance: no external model call occurs per record (`context_semantic_shadow.py:202-266`).

## Steps

1. Validate the rubric identity, frozen parents and deterministic compilation mode; reject retrospective inputs and any trade/size/risk-action fields (`context_semantic_shadow.py:202-266`).
2. Validate the supplied decision snapshot before applying catalyst, leadership and chart-context functions (`:608-631`).
3. Abstain on insufficient credibility evidence or unavailable domains rather than inventing knowledge; attach rubric/run provenance and a five-minute validity window (`:615-650`).
4. Restrict the date to the registered panel, preserve records and source hashes, and seal a payload whose `runtime_strategy_effect` remains `none` (`:653-686`).

This map does not invent an active scanner-v0.3-to-model-service route. The input snapshot contract and prospective real-source integration require their own verified adapters; this process describes the compiled shadow that actually exists.

## If you change this

- **Hits:** Descriptive axis outputs, abstention behavior, assessment validity, provenance hashes and downstream shadow comparisons.
- **Does not hit:** Candidate priority, setup plans, execution, position size or risk limits. An assessment is not permission to buy or sell, even if its wording sounds favorable.

## Surfaces

| Surface | Role |
|---|---|
| Validated structured snapshot | Supplies only allowed evidence |
| Compiled rubric | Evaluates deterministic semantic functions |
| Shadow date artifact | Stores bounded, hashed descriptions |
| Order/account engine | Receives no strategy authority from this process |

## See

- Object: [Context shadow](../objects/context-shadow.md)
- [Owning source](../../../src/momentumbot/research/context_semantic_shadow.py)
- [Snapshot/assessment contract](../../../src/momentumbot/research/context_assessment.py)
