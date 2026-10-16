---
type: object
id: object-context-shadow
title: "Descriptive context shadow"
cluster: discretionary-context
universe: live
status: verified
entity: src/momentumbot/research/context_semantic_shadow.py
verified_at: 2026-10-16
verified_commit: 53989a5f1637e759a3922980b40f24cbfbaab5fb
sources: ["src/momentumbot/research/context_semantic_shadow.py:21-34", "src/momentumbot/research/context_semantic_shadow.py:202-266", "src/momentumbot/research/context_semantic_shadow.py:608-686"]
---

# Descriptive context shadow

The implemented semantic shadow is deterministic execution of a frozen AI-authored rubric, not per-record model inference or a discretionary trader.

## Why this shape

Semantic interpretation must be inspectable without allowing subjective assessment to change measurable facts, account risk or order mechanics. The validator requires snapshot-only evidence and rejects transcripts, recap inventory, Ross actions, labels, outcomes and later prices. It also rejects any populated trading recommendation, priority, size or risk-action field (`context_semantic_shadow.py:202-266`).

## Shape

The stored model/prompt names identify the rubric's authorship and provenance. The required generation mode explicitly says deterministic compilation and `external_model_api_call_per_record=False`; the name is not evidence of a running model service (`:21-34,209-219`).

`build_compiled_shadow_assessment` produces six descriptive axes from a validated decision snapshot, including explicit abstention where evidence is insufficient. It binds the rubric hash and label-blind run ID, sets an expiry five minutes after the decision and validates the resulting assessment (`:608-650`). Date payloads restrict the registered panel, hash their records and set `runtime_strategy_effect="none"` and `policy_promotion_eligible=False` (`:653-686`). A full discretionary integration remains a future capability, not an implied output of this card.

## Connected to

- **owns:** Descriptive assessments, abstentions, validity interval and rubric provenance.
- **owned-by:** Frozen context-assessment and semantic-rubric contracts.
- **joins:** Structured facts derived from [causal scanner](causal-scanner.md); downstream [research/evaluation](research-evaluation.md).
- **looks-like-but-is-not:** An LLM API client, weighted selection score, priority policy or order manager.

## If you change this

- **Hits:** Axis descriptions, abstention rates, evidence references, assessment fingerprints and retrospective shadow comparisons.
- **Does not hit:** Candidate selection, plans, size, risk limits or account trades. A future adapter affecting strategy requires an explicitly separate policy and authorization.

## Surfaces

| Surface | Role |
|---|---|
| Validated decision snapshot | Supplies time-bounded structured evidence |
| Compiled rubric functions | Produce deterministic descriptions or abstentions |
| Date/root artifacts | Preserve provenance and no-effect boundary |
| Runtime order path | No authority from this shadow |

## See

- [Owning source](../../../src/momentumbot/research/context_semantic_shadow.py)
- [Assessment contract implementation](../../../src/momentumbot/research/context_assessment.py)
- [Context-shadow movement](../processes/context-shadow.md)
