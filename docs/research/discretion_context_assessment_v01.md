# Discretion context-assessment protocol v0.1

Status: **preregistered shadow schema; no runtime artifact, semantic model, threshold, or trading authority**.

## Research question

Can the project represent the context that appears to separate explicit Ross trades from explicit skips without changing the frozen scanner or Micro-v0.1 and without exposing retrospective behavior to runtime?

The prior ten-session comparison motivates the domains, but it is excluded from fitting or evaluating this protocol. The next evaluation must use dates registered before their recaps are opened.

## Frozen parent and isolated change

The technical parent remains `micro-v0.1`, fingerprint `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`. The causal scanner remains `causal-scanner-snapshot-v0.1`, fingerprint `ed21becad10855b4a085b6e05b6feac8f21e4ce511a100b2381522154818f42a`.

This change adds only:

1. a hash-bound decision snapshot that carries causal scanner, attention/leadership, catalyst, and later supplemental evidence in one envelope; and
2. a hash-bound AI shadow record that can describe six semantic axes while citing only evidence in that exact snapshot.

It does not change candidate acquisition, candidate qualification, Micro setup detection, fills, exits, position size, or risk.

## Decision snapshot

A snapshot may be emitted at candidate activation, a declared source-evidence change, or a registered scheduled refresh. Scanner and attention evidence are mandatory. Catalyst, daily-chart, theme/regime, liquidity, account-state, issuer-history, filing, and portfolio-attention evidence remain explicit as present or absent.

Every evidence item records:

- a stable evidence ID;
- its domain and availability timestamp;
- its source contract and source-artifact hash;
- the exact structured payload; and
- a content hash of that payload.

All availability timestamps must be at or before the snapshot decision time. Scanner and attention rows must share symbol, activation time, decision time, and rank-input lineage. Catalyst packets must be the same candidate, cannot come from a later decision, and cannot contain a headline published after their own decision time.

The snapshot rejects retrospective or outcome keys, including Ross actions or fills, recap judgments, trade outcomes, later prices, realized-P&L outcomes, benchmark labels, and raw transcripts. Provider-relative absence remains provider-relative; it is not converted into universal no-news evidence.

## Semantic axes

The AI shadow may assess only these axes:

1. catalyst substance and specificity;
2. catalyst commitment stage;
3. catalyst credibility and possible repetition;
4. theme fit or causal acceptance of no-news momentum;
5. opportunity obviousness and leadership quality; and
6. daily-chart context cleanliness.

Each assessed axis must include:

- one categorical value from the frozen vocabulary;
- low, medium, or high confidence;
- at least one observed-fact claim;
- at least one explicitly separate inference claim; and
- evidence IDs that exactly equal the union of the claims' citations.

Every citation must exist in the source snapshot and come from a domain allowed for that axis. Stronger claims also require their specific source domain: for example, possible recycled promotion requires causal issuer-event history, corroboration requires filing evidence, and chart-cleanliness claims require daily-chart evidence.

If the required domain is absent, the axis must abstain. It may also abstain for insufficient, ambiguous, unavailable, or out-of-protocol evidence. An abstained axis cannot contain a value, confidence, or inference.

## Bounded validity and authority

The logical assessment expiry must be after the source decision and no more than 300 seconds later. Historical label-blind generation may occur after that logical window; the expiry represents how long the context could have been considered current, not a claim that historical reconstruction happened live.

The record has no aggregate score, candidate priority, selection action, trade recommendation, order action, position size, or risk action. Those fields are structurally fixed to `null`. AI remains unable to place an order or increase deterministic risk.

## Excluded pilot and next evaluation

The frozen comparison `ross-discretion-heldout-comparison-v0.1`, content SHA-256 `809d4b4a7231b708f9c933c9bf45b58c736f4d3101c8328483c62c1c48bcfb3d`, is explicitly excluded from threshold fitting and protocol evaluation.

The next valid sequence is:

1. register a new chronological panel before opening its recaps;
2. materialize deterministic snapshots and any AI shadows label-blind;
3. freeze and hash those artifacts;
4. only then encode conservative account-scoped retrospective evidence; and
5. report each component separately without fitting an aggregate score.

Daily-chart, theme/regime, account, portfolio-attention, and liquidity sources are not implemented by this schema. Their absence remains visible and forces relevant abstentions; the schema does not invent substitutes.

## Files

- Contract: `research/strategy/discretion-context-assessment-shadow-v0.1.json`
- Validator and builders: `src/momentumbot/research/context_assessment.py`
- Protocol audit: `research/data-audits/discretion-context-assessment-shadow-v0.1.json`
- Tests: `tests/test_context_assessment.py`
