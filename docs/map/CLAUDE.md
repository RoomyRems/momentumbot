# MomentumBot system map

A source-linked edit map, not a second specification.
Read [root rules](../../AGENTS.md) first; status lives in the [status record](../agent-workflow/status.md).

## Route by question

| Question | Card |
|---|---|
| Where do dated inputs and capture authority come from? | [Source capture](objects/source-capture.md) |
| How are candidates and rank reconstructed? | [Causal scanner](objects/causal-scanner.md) |
| What emits Micro setups and simulated entries? | [Micro replay](objects/micro-replay.md) |
| What owns execution, risk, fees and account carry? | [Execution/accounts](objects/execution-account.md) |
| What does the discretionary shadow actually do? | [Context shadow](objects/context-shadow.md) |
| Where are experiments, labels and evaluations separated? | [Research/evaluation](objects/research-evaluation.md) |
| What runs jobs and verifies changes? | [Workflow control](objects/workflow-control.md) |

## Choose the next shelf

- Movements: [process index](processes/_index.md).
- Dependencies: [change-impact index](effects/CONTEXT.md).
- Particular historical stage: [all preserved task routes](task-routes.md).
- Exact file lookup: [generated file inventory](FILE-MAP.md); search, do not load it all.
- Card maintenance: [schema](_meta/schema.md).

## Names that collide

“Runtime” may mean synthetic replay, a sealed historical artifact, or a descriptive shadow—not live trading.
“Execution” may mean simulated fills or a provider job—not brokerage orders.
“AI shadow” includes a deterministic compiled rubric—not an active model service.
“Scanner source” archives are not yet validated scanner features.
“Current” in an old checkpoint title is historical; use the status link above.
The public CLI baseline is not the Micro or sealed account replay.

The [walking contract](CONTEXT.md) defines live/leftover/ghost and read limits.
Edit this catalog; generate its byte-identical AGENTS.md and routing.md twins.
