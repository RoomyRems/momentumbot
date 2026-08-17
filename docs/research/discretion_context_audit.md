# Discretion-context coverage audit v0.1

## Purpose

The recent micro-pullback experiments show that changing a technical translation can recover a labeled entry while also creating much more activity elsewhere. That is consistent with an incomplete decision stack: the technical trigger is being evaluated without all of the contextual filters Ross Cameron may have used to decide that a stock and moment deserved participation.

This audit freezes the missing-layer inventory before any further context experiment. It does not change `micro-v0.1`, the causal scanner, candidate selection, risk, or execution. Its machine-readable source is `research/strategy/discretion-context-v0.1.json`.

## Current coverage

| Decision layer | Current state | What exists | Main missing element |
|---|---|---|---|
| Technical setup and trigger | Frozen baseline | Micro pullback geometry, volume, support, momentum state and confirmation trigger | Cannot explain candidate preference |
| Catalyst substance | Partial proxy | Provider news presence plus shadow chronology relative to market qualification | Substance, novelty, dilution risk, materiality and theme fit |
| Attention leadership | Feature only | Full-membership gain rank plus shadow leadership, handoff, persistence and competition features | No frozen general-profile attention or top-N rule |
| Daily-chart context | Partial proxy | Prior-high reward/risk room | Resistance clusters, repeated rejection and chart cleanliness |
| Market regime and theme | Not implemented | Evidence-backed cold/spark/hot/exhausted concepts | No causal state or theme-saturation model |
| Liquidity and fill quality | Partial proxy | Total volume, SIP prints and basic slippage checks | Complete quote, spread, depth and achievable-size model |
| Level 2 and tape | Deferred | SIP time and sales used for bars and fill modeling | Historical depth, queue/replenishment and synchronized screen evidence |
| Session state and aggression | Partial, not end to end | Risk objects, giveback and lockout rules | One replay carrying scanner, positions, realized PnL, cushion and re-entry state |

Only the technical setup layer is frozen as an implemented policy. Every incomplete contextual layer is explicitly fail-closed and cannot become a runtime strategy gate through this audit.

## Research implication

The five labeled micro cases remain useful diagnostics, but they do not represent the full strategy. A seed-case entry improvement can mean any of the following:

1. the technical translation became more faithful;
2. a missing contextual filter was accidentally approximated;
3. a broad rule was loosened enough to catch the labeled trade and many unrelated opportunities;
4. upstream selection qualified too late for the entry to be reproducible.

Therefore no further technical ablation should be interpreted as full-strategy imitation evidence while the required context domains remain incomplete. This does not forbid a narrowly justified technical correction; it changes the claim that may be made from it.

## Next evidence stage

The next bounded research task is a source-coverage audit, not a new trading rule. For each context domain, check the existing evidence registry and benchmark sources for:

- normative teaching that defines the intended judgment;
- pre-entry commentary rather than retrospective outcome explanation;
- both participated and skipped candidates;
- a resolvable timestamp and the market inputs available then;
- visual evidence only when the transcript does not contain the necessary chart, scanner, Level 2 or tape state.

The entire transcript corpus does not need to be re-uploaded. Request only a named video, timestamp range, or missing screen segment after the existing evidence has been checked. Trade recaps alone are not enough: skip and comparison examples are especially important because they identify the discretionary filter that controls activity.

### Seed benchmark evidence check

The five primary Micro benchmarks were checked against this inventory. All five sources are `same_day_behavioral_recap` videos and all five benchmark rows describe trades Ross took. They are useful retrospective behavior labels, but they are not a balanced discretion dataset.

| Case | Context already captured | Important context not frozen |
|---|---|---|
| TIVC | A later one-minute setup was skipped because of topping-tail history | Contemporaneous catalyst, competing candidates, regime and Level 2 state |
| UPXI | Initial and later pullback participation are distinguished | Why UPXI was preferred before the first entry and what was rejected |
| MMA | The recap names the 10-second setup and approximate entry | Pre-entry catalyst, daily-chart, leader and session-state reasoning |
| ARTL | Heavy price action, topping-tail rejection and the losing outcome are preserved | The pre-entry selection case and whether tape or catalyst quality justified aggression |
| DSY | DSY is described as the attention successor after VSME rolled over | A complete contemporaneous candidate ranking and the evidence that attention transferred |

None of the five benchmark payloads freezes a systematic pre-entry alternative-candidate set, catalyst-quality rubric, market-regime state, synchronized Level 2 state, or full session cushion. The immediate evidence priority is therefore trade-versus-skip and candidate-versus-candidate context, not additional fill labels.

### Wider boundary/context evidence

The five non-primary benchmark cases add important evidence that would be lost by looking only at first-entry price matching:

| Case | Discretion evidence |
|---|---|
| YOUL | Attempted entry did not fill; later caution cites high float, topping-tail rejection and unwillingness to chase extension |
| AGPU | Anticipatory entry is explicitly attributed to stacked Level 2 buyers and green time-and-sales |
| LABT | Front-side micros were traded, a later proper pullback was skipped, and whole-dollar resistance/heavy selling mattered |
| ZEVAI | Cooler regime, no breaking news and excessive aggression before building a cushion appear in self-critique |
| VRAX | Obvious-number-one-gainer status and slippage that changed reward/risk are both explicit |

The initial frozen coverage result is `research/data-audits/discretion-evidence-coverage-v0.1.json`. It validated 17 contextual evidence rows across all ten benchmarks and all eight decision domains before the DSY/VRAX enrichment below increased the count to 22. The evidence is materially broader than the primary Micro seed, but every row remains retrospective: zero has a verified pre-entry context timestamp and zero includes a complete alternative-candidate set. It can prioritize source review; it cannot become a runtime filter or justify policy promotion.

### DSY and VRAX transcript enrichment

Full transcript text for the DSY and VRAX source videos was subsequently supplied and distilled without storing the verbatim transcripts. The benchmark artifacts now separate retrospective decision context from the original trade labels.

DSY adds five linked layers:

- a hot but fragile regime after the prior leader gave back its full move;
- a speculative Chinese no-news theme that made an actual-news US biotech unattractive that morning;
- an attention handoff as VSME rolled over and DSY's volume/gain increased;
- earlier DSY pullbacks observed without a trade before the attention increase;
- prior challenge profits explicitly enabling a larger position while retaining a one-good-trade focus.

VRAX adds four linked layers:

- PMA, RPGL and SOT as a partial rejected comparison set before anything looked obvious;
- breaking news turning VRAX into the obvious number-one candidate;
- an uncertainty-based skip of the first pullback followed by participation in the second micro pullback;
- slippage widening planned risk from about 15 cents to roughly 35-40 cents per share and changing the intended exit posture.

This increases the frozen audit from 17 to 22 evidence rows. It is evidence that context changes selection, ordinal and risk decisions; it is not yet an algorithm. The narratives are retrospective descriptions of pre-entry state, their video timestamps are not independently verified, and their candidate comparison sets are incomplete. They remain runtime-ineligible.

### Attention feature checkpoint

The first deterministic context feature layer is now frozen as `attention-leadership-shadow-v0.1`. It derives only threshold-free market leadership and transition measurements from causal scanner rows. Validation on the two-date frozen scanner artifact found a genuine MNST-to-VRAX leadership handoff, while TIVC never reached rank one. This supports keeping leadership as a measured context feature and rejects making rank one an assumed universal eligibility rule. Full details are in `docs/research/attention_leadership_shadow.md` and `research/data-audits/attention-leadership-shadow-v0.1.json`.

### Catalyst timing checkpoint

`catalyst-timing-shadow-v0.1` now separates market qualification from causally available provider-news timing. In the frozen VRAX reconstruction, market qualification precedes the first Alpaca provider event by 153 seconds and market leadership follows it by 207 seconds. Ross's recap describes a different proprietary news-linked alert, so the mismatch is retained rather than tuned away. Timing is now measurable, but substance, relevance and theme fit remain unresolved. Full details are in `docs/research/catalyst_timing_shadow.md` and `research/data-audits/catalyst-timing-shadow-v0.1.json`.

## Integration order

1. Audit existing evidence for all eight domains.
2. Prioritize catalyst substance, attention leadership, daily-chart context and regime because they act before the micro trigger.
3. Freeze deterministic causal features wherever the judgment is measurable.
4. Use an AI component only for residual structured context, shadow-only, with no order or risk authority.
5. Evaluate each context layer in isolation on chronological held-out trade and skip examples.
6. Integrate scanner, context, setup, position and session state on one causal replay.
7. Make an overall imitation claim only after the complete decision chain is tested on a representative walk-forward panel.

## Non-negotiable guards

- Raw transcripts remain offline research evidence and never become runtime prompts.
- News, filings, scanner state, charts and session state must be available by the simulated decision time.
- Reported Ross fills, later highs, outcomes and PnL never enter runtime reconstruction.
- An AI reviewer remains shadow-only until the deterministic baseline and each contextual input pass causal validation.
- This audit is not policy-promotion eligible and does not imply profitability or live-trading readiness.
