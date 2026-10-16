# Change-impact index

This is a catalog into first-order effects, not a duplicate dependency specification.

## Inputs

Working: the proposed change. Reference: [root constraints](../../../AGENTS.md)
and the relevant verified cards below. Read their cited code before implementation.

## Process

| Changing | Open these cards |
|---|---|
| Provider requests, bounds, archives or identity | [Source capture](../objects/source-capture.md), [bounded capture](../processes/bounded-capture.md) |
| Rank, raw/split basis, RVOL, float or news | [Causal scanner](../objects/causal-scanner.md), [scanner reconstruction](../processes/scanner-reconstruction.md) |
| Pullback geometry, triggers or SIP entry assumptions | [Micro replay](../objects/micro-replay.md), [Micro process](../processes/micro-replay.md) |
| Simulated fills, fees, risk or account carry | [Execution/accounts](../objects/execution-account.md), [account replay](../processes/account-replay.md) |
| Causal context or semantic rubric | [Context shadow](../objects/context-shadow.md), [shadow process](../processes/context-shadow.md) |
| Registrations, labels or outcome interpretation | [Research/evaluation](../objects/research-evaluation.md), [retrospective evaluation](../processes/retrospective-evaluation.md) |
| CLI backtest behavior | [Legacy baseline](../processes/legacy-backtest.md); do not assume it is the Micro runner |
| CI, capture gating or navigation | [Workflow control](../objects/workflow-control.md), [maintenance](../../agent-workflow/maintenance.md) |

## Outputs

A scoped impact/non-impact statement in the work record, plus source-reviewed card
updates when required. Search actual imports, callers, workflow paths and byte pins;
the map is a starting point, not an exhaustive static call graph.

## Human check

Confirm first-order Hits and Does not hit in the selected cards. Unknown external
consumers stay unknown. Ask the owner before any future path move; no grep can
discover every outside bookmark, agent configuration or scheduled job.
The approved adoption retains all existing paths and frozen source bytes.
