# MomentumBot agent routing

MomentumBot is research-first, historically causal small-cap momentum research.
Active branch: `phase-3-historical-snapshot`. No live-money trading.

## Start here

| Task | Read next |
|---|---|
| Resume / current status / next gate | [Workspace context](CONTEXT.md) |
| Understand or change a component | [System map](docs/map/CLAUDE.md) |
| Determine change impact | [Impact index](docs/map/effects/CONTEXT.md) |
| Find a versioned experiment | [Preserved task routes](docs/map/task-routes.md) |
| Plan, implement, verify, hand off | [Development workflow](docs/agent-workflow/CONTEXT.md) |

## Non-negotiable boundaries

- Runtime order is market data -> label-blind replay -> frozen artifact -> retrospective Ross comparison.
- Never expose Ross fills, actions, recap labels or later price outcomes to runtime reconstruction.
- Do not tune thresholds case by case or promote a policy from the diagnostic seed suite.
- Measurable facts, timestamps, order mechanics and every risk limit remain deterministic.
- AI begins shadow-only, uses time-causal structured inputs, may abstain, cannot submit orders and cannot increase deterministic risk.
- Preserve failed experiments and their provenance.
- Interpret interim financial results as evidence about the components actually integrated. The intended project includes crucial discretionary/context components; an incomplete deterministic baseline does not settle the full hybrid strategy's edge. Completing the hybrid remains a research goal, not a profitability guarantee.
- Transcripts may clarify offline, versioned strategy design. Keep recap actions, fills, later outcomes and evaluation-case narratives out of replay and runtime AI prompts; do not use registered evaluation cases to tune a frozen experiment.

## Working protocol

1. Read the current status and relevant component card, then its cited source; do not load the whole repository.
2. State the frozen parent, one hypothesis/change, and prohibited retrospective inputs.
3. Make the smallest isolated change and add deterministic focused tests.
4. Run focused local tests and optimized-mode checks for new safety gates. Publish for one authoritative full GitHub CI run; do not duplicate the entire suite locally. No provider job or policy promotion before exact-code CI passes.
5. Record success, failure and unavailable inputs; promotion is a separate explicit decision.
6. Reuse tested utilities and batch related fixes. Preserve bounded spending, credential protection and single-use provider jobs. A bounded diagnostic under current owner continuation authorization may follow same-code CI without another confirmation turn; new subscriptions, expanded datasets or financial/live-order authority need explicit approval.
7. Before moving existing paths, obtain approval against a reference/collision report. Frozen evidence is never edited for organization.
8. Maintain the map with [the documented commands](docs/agent-workflow/maintenance.md); templates and generated indexes are not parallel policy authorities.
