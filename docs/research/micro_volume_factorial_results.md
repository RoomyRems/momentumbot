# Micro volume-context factorial results

Status: **diagnostic interaction evidence; not promoted**.

> **Source correction (2026-08-17):** ARTL's old ~$5.25 trade label was misattributed from an earlier stock discussion. With ARTL retired, all four factorial cells score **8/10**. The broad-score gain disappears; the UPXI/MMA interaction and TIVC first-fill movement remain descriptive evidence only. See `docs/research/artl_source_label_correction.md`.

This experiment tests whether two previously isolated factors interact in the early micro-pullback misses:

1. the frozen Micro v0.1 information boundary, which discards pre-qualification chart structure; and
2. the frozen hard requirement that pullback mean volume be lower than impulse mean volume.

The experiment is deliberately factorial rather than a combined hand-tuned replacement. Micro v0.1 remains unchanged.

## Authoritative provenance

- Frozen parent: `micro-v0.1`
- Parent fingerprint: `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`
- Existing context-only cell: `micro-v0.2a-prequalification-context`
- Context-only fingerprint: `cdd9c1a18abf23a03aac67568f1c3b976bd4ab968a07f46966940b5e81feb49e`
- Volume-only cell: `micro-v0.2c-no-hard-volume-gate`
- Volume-only fingerprint: `a1c28368322a9eb45101339b79d62ca82221d5d27b3f19c3aa7525db2f023efc`
- Context + volume cell: `micro-v0.2d-context-no-hard-volume-gate`
- Context + volume fingerprint: `8ac8e9eaf306c09d6481f41492d268388458ed53eb920e42c0fe105ac0108530`
- Authoritative factorial workflow run: `31927848897`
- Runtime/workflow commit: `2b7b40b433d0fb11f742632166a47bfc61393b5d`
- Permanent comparison: `research/benchmarks/results/micro-volume-factorial-comparison.json`

All new runtime cells were generated label-blind before retrospective labels were loaded by the scorer.

## The 2 x 2 design

| Cell | Pre-qualification structural context | Hard lower-pullback-volume rejection |
| --- | --- | --- |
| Frozen baseline | off | on |
| v0.2a context-only | on, bounded to the already-measured 10 completed 10-second bars | on |
| v0.2c volume-only | off | off |
| v0.2d context + volume | on, same fixed v0.2a bound | off |

"Volume off" does not erase volume from the feature set and does not introduce a benchmark-fitted ratio. Impulse and pullback volume remain measured in every setup. The only change is that `pullback_mean_volume >= impulse_mean_volume` no longer causes an automatic rejection.

Everything else remains the frozen parent's setup/execution translation: qualification timestamp, strict running-high peak rule, five-bar impulse lookback, five-bar maximum pullback, 50% retracement limit, topping-tail filter, VWAP/EMA9 support, first-new-high trigger, pullback-low stop reference and SIP execution.

## Result

| Case | Baseline | Context only | Volume only | Context + volume | Main inference |
| --- | --- | --- | --- | --- | --- |
| DSY | $8.50 #10 | $8.50 #10 | $8.50 #10 | $8.50 #10 | neither tested factor explains the early miss |
| MMA | $4.02 #3 | $4.02 #3 | $4.02 #3 | **$2.59 #1** | genuine context x volume interaction |
| TIVC | $5.10 #7 | $5.10 #7 | **$4.98 #5** | **$4.98 #5** | volume-gate main effect; no context interaction |
| UPXI | $7.23 #8 | $7.23 #8 | $6.66 #7 | **$2.81 #1** | strong context x volume interaction |

Retrospective human fill references are approximately $3.07/$3.11 DSY, $2.40 MMA, $4.73/$4.76/$4.89 TIVC and $2.84 UPXI. These references were never available to the runtime policies.

### UPXI: strongest interaction evidence

UPXI qualifies causally at approximately **$2.82 at 08:02:42.541 ET**, so the upstream scanner is already early enough to participate near the human's reported ~$2.84 entry.

Neither factor by itself solves the miss:

- baseline: first fill $7.23, pullback #8;
- context-only: first fill $7.23, pullback #8;
- volume-only: first fill $6.66, pullback #7.

With both factors, the policy can use the completed pre-alert impulse while not hard-rejecting the one-bar pullback solely because its mean volume is higher than the impulse mean. At 08:02:50 ET it forms a pullback-#1 plan with:

- peak high $3.0167;
- impulse base $2.22;
- pullback low $2.62;
- retracement fraction ~0.498;
- impulse mean volume 10,266.25;
- pullback volume 15,777;
- VWAP at the low ~2.4103;
- EMA9 at the low ~2.3269;
- previous completed 10-second high $2.80;
- trigger $2.81;
- stop reference $2.62.

The plan arms at 08:03:00 ET and fills on a regular SIP print at **$2.81 at 08:03:01.685 ET**, only **$0.03 below** the retrospective ~$2.84 reference. The fill is not odd-lot-driven.

This is the clearest seed example that the information boundary and hard volume gate interact rather than acting as interchangeable independent fixes.

### MMA: independent interaction replication

MMA produces the same qualitative pattern on a different date and stock:

- baseline: $4.02 #3;
- context-only: $4.02 #3;
- volume-only: $4.02 #3;
- context + volume: **$2.59 #1**.

The retrospective reference is ~$2.40, reducing the first-fill distance from $1.62 to $0.19.

The recovered first setup has peak $2.79, pullback low $2.09, retracement ~0.473, impulse mean volume ~235,088 and pullback volume ~254,001. It therefore passes the frozen geometry/support rules but is rejected by the frozen hard volume test. With bounded prior context plus the non-hard volume interpretation, the trigger is $2.58 and the first qualifying SIP fill is $2.59.

Having the same interaction on UPXI and MMA is materially stronger evidence than fitting a one-stock exception.

### TIVC: a separate volume main effect

TIVC does not need the context factor for its observed improvement. Removing the hard volume rejection alone moves the first fill from $5.10/#7 to **$4.98/#5**, just $0.09 above the closest reported $4.89 fill. Adding context produces the identical first trade.

This means the hard lower-volume translation can also delay participation independently of the context boundary, even where it does not explain the entire first-pullback ordinal gap.

### DSY: neither factor addresses the miss

DSY remains $8.50/#10 in all four cells. Disabling the volume gate greatly increases later valid-plan count but does not alter the first fill. Earlier replay diagnostics continue to point to `micro_retrace_above_half` / impulse-base geometry as the more relevant hypothesis for this case.

## Broad diagnostic versus exact behavioral evidence

The descriptive broad-dimension counts are:

- baseline: 8/10 = 0.8;
- context-only: 8/10 = 0.8;
- volume-only: 8/10 = 0.8;
- context + volume: 8/10 = 0.8.

Those numbers are intentionally **not** an exact-human-trade score. The old apparent broad increase was entirely an artifact of the invalid ARTL label. The remaining descriptive evidence is first-fill price/ordinal behavior: TIVC improves under the volume main effect; UPXI and MMA show context-by-volume interaction recoveries; DSY does not improve.

## Opportunity-density cost

The relaxed volume interpretation materially increases activity across the four valid trade-taken seed examples:

| Cell | Total plans | Total fills |
| --- | ---: | ---: |
| Baseline | 11 | 7 |
| Context only | 11 | 7 |
| Volume only | 32 | 11 |
| Context + volume | 34 | 13 |

Plan count roughly triples and fills increase substantially. The current four primary cases are poor instruments for determining whether that extra activity is acceptable because they were selected as retrospective micro examples where the human **did trade**. They do not supply enough clean no-trade / rejected-setup controls to estimate false-positive cost.

That limitation is decisive for promotion. A rule that explains known trades while increasing opportunity density can look better on a trade-selected benchmark even if it would overtrade a realistic walk-forward universe.

## Decision

**Do not promote v0.2c or v0.2d yet. Do not modify Micro v0.1.**

The factorial establishes a credible mechanism worth carrying forward:

- bounded completed pre-qualification chart structure can matter;
- the hard `pullback_mean_volume < impulse_mean_volume` translation is too brittle in at least some human-like early micro entries;
- the two factors interact strongly in UPXI and MMA;
- volume alone improves TIVC;
- neither factor fixes DSY;

But the same relaxation raises plan/fill density enough that the next test must be **negative-control and walk-forward validation**, not another tweak chosen from these four labels.

## Next research step

Before any `micro-v0.2` promotion candidate is named, expand evaluation with label-blind historical examples that include:

- explicit no-trade / rejected-micro cases;
- attempted-but-no-fill cases;
- losing trades as well as winners;
- first-pullback skips and second-pullback entries;
- multiple price, float and RVOL buckets;
- different market regimes;
- ordinary scanner-qualified candidates that never became clean human-style micro setups.

Run baseline, v0.2c and v0.2d unchanged across that expansion. The principal comparison should include opportunity count, entry-participation rate, first-fill timing/price where a human reference exists, and false-positive behavior on no-trade controls. Only after that should a promotion candidate be frozen.

Separately, DSY/TIVC still justify a future retracement/impulse-base ablation, but it should remain independent of this volume/context mechanism so the causal contribution of each translation stays identifiable.
