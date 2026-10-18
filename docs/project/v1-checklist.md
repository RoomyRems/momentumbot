# MomentumBot V1 completion checklist

Owner-approved direction, October 17, 2026. V1 means an end-to-end historical
hybrid evaluation plus a working paper-trading shadow. It does not mean proven
profitability or live-money deployment. This is a completion checklist, not a
replacement for frozen research contracts or the [current status](../agent-workflow/status.md).

| Milestone | Current state | Completion evidence |
|---|---|---|
| Preserve irreplaceable source data | Nine originals saved; fourteen checked references covered with Git-backed evidence | [Recovery inventory](../agent-workflow/runs/source-preservation-daily-2026-10-17/source-preservation.json) |
| Publish daily-input checkpoint | Focused normal/optimized tests passed; publication/full CI pending at authoring | Exact branch commit and successful full CI |
| Complete source inputs | Exact RVOL ready for 2,101/2,103 retained cases; daily-close audit passes; daily/minute basis and historical float/news remain incomplete | Causal source coverage, validated units and explicit unavailable inputs |
| Connect historical pipeline | Components exist; complete captured-source scanner-to-shadow bridge remains incomplete | One reproducible data → scanner → setup → shadow → simulated execution run |
| Evaluate actual model shadow | Current shadow is a deterministic compiled rubric, not per-record inference | Frozen model/schema, causal inputs, abstention, logged responses and held-out comparison |
| Evaluate full hybrid | Not complete | Pre-registered held-out comparison against deterministic baseline, realistic costs/latency and unchanged risk limits; no outcome-driven tuning |
| Demonstrate paper shadow | Not complete | Incoming-data operation with stale-data/outage handling, reproducible logs, no live orders; acceptance period/criteria frozen before starting |

## Immediate sequence

1. Finish publication and exact-code CI for the already-tested checkpoint.
2. Establish the supported daily/minute basis and historical float/news coverage;
   integrate only verified fields. Keep unsupported cases explicit rather than
   repeatedly fitting them. Exclusions must preserve ranking semantics and be
   declared before evaluation, not chosen from favorable outcomes.
3. Build the smallest complete historical path and evaluate it. Add infrastructure
   only to complete this path or remove a demonstrated blocker.

No defensible completion date yet: remaining data coverage and integration effort
are not bounded. Report progress by these milestones, not invented percentages.

## Shadow-model shortlist — research recommendation, not adoption

Jev is the first candidate for a bounded comparison; Laya is the self-hosted
alternative. Neither has been run on MomentumBot or shown a trading advantage.
Keep the existing deterministic rubric as a baseline. The first model experiment
must remain descriptive and have no strategy effect; a later hybrid policy needs
its own frozen contract and acceptance decision.

Use atomic descriptive axes (for example catalyst substance and commitment), not
a free-form buy/sell instruction. Missing evidence must cause abstention before
inference where appropriate. Model confidence is not a probability of profit.
Numerical indicators, sizing, stops, risk limits and order authority stay in code.
Typed output prevents format errors, not incorrect judgments.

Pin model/checkpoint and prompt/schema versions, retain original responses and
input hashes, and compare temporal holdouts for accuracy, calibration, abstention,
option-order sensitivity, latency and cost. Do not tune from registered evaluation
outcomes. Training-data contamination remains a limitation even with causal prompts;
forward paper shadow provides additional evidence. No raw recap narratives,
Ross actions/fills, later prices or retrospective labels enter model inputs.

Sources inspected October 17, 2026:

- [TypeSafe models](https://docs.typesafe.ai/models): hosted text/structured-state
  input, versioned IDs, and request-based customization rather than customer
  fine-tuning. A pinned stable release is preferable to a moving alias.
- [Creator's Laya model card](https://huggingface.co/convaiinnovations/laya):
  Apache-2.0, local weights, typed decisions and domain fine-tuning. Serving and
  calibration become our responsibility; it is not automatically cheaper overall.
- [Paired agent-harness evaluation](https://arxiv.org/abs/2610.02267): Jev outperformed
  Laya on nine of eleven studied decision points, but those are non-trading tasks
  and tested versions; this does not establish performance on MomentumBot or on
  newer releases.

No model dependency, account, subscription, external inference call or trading
policy change is authorized or implemented by this comparison.
