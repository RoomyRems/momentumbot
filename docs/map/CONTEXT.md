# System map — walk one question

## Inputs

- Working: one task from the owner and the [current status](../agent-workflow/status.md).
- Reference: [root boundaries](../../AGENTS.md), [catalog](CLAUDE.md), [schema](_meta/schema.md).

## Process

1. Select one object or process from the catalog; read its cited source before editing.
2. Follow its first-order Hits / Does not hit, then inspect actual referrers.
3. Treat live as in force, leftover as a retained alternative, ghost as not wired.
   These describe a component's use, not readiness for live trading.
4. After source changes, re-review affected cards and update their verification evidence.

## Outputs

Updated cards and generated indexes, plus the work item's review evidence.
Do NOT load all cards, all research histories, transcript attachments, or retrospective
labels to solve a runtime task. A normal walk should fit roughly 2,000–8,000 tokens;
smaller is fine, padding is not. Source citations can be loaded selectively.

## Human check

Confirm the intended change and boundaries in the work item's scope; a cold walk
may verify intermediate map slices. New authority still needs the owner's decision.
See [adoption decisions](_meta/adoption.md) for the approved no-move migration.
