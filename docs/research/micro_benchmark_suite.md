# Micro v0.1 multi-example benchmark suite

The benchmark suite exists to answer a harder question than "can MomentumBot reproduce VRAX?": **does one frozen chart-only micro policy behave sensibly across materially different historical examples without being rewritten for each stock?**

The seed manifest is `research/benchmarks/suites/micro-v0.1-seed.json`. It currently contains ten retrospective cases selected from the transcript corpus.

## Case roles

### Primary scored

These examples are close enough to the canonical chart-only micro family that Micro v0.1 is allowed to be judged on explicitly listed dimensions.

- **DSY — 2026-06-10.** Current-era 10-second micro; recap explicitly restates crossing-candle / first-new-high entry language and gives approximate fills near $3.07/$3.11.
- **TIVC — 2025-04-03.** First micro pullback taken with reported fills at $4.73/$4.76/$4.89 and about $3,000 on the first trade.
- **UPXI — 2025-04-21.** Initial 10-second entry is explicitly described as first candle to make a new high at about $2.84, with a later pullback described as picture perfect.
- **MMA — 2025-09-09.** Explicit 10-second micro entry around $2.40 followed by continuation through $3.
- **ONCS — 2026-03-27.** Deliberate losing example: entry around $5.25 on a micro pullback, brief progress, then topping-tail rejection and a reported roughly $2,400 first-trade loss.

Including ONCS is intentional. A benchmark suite made only from clean winners would be structurally biased toward finding entries and would tell us little about failure handling.

### Partial scored

- **VRAX — 2026-07-09.** Micro v0.1 may be judged on recognizing the setup family, not taking the first pullback, and identifying the second pullback. It is **not** judged on reproducing the human $6 whole-dollar continuation trigger or ~$6.30 fill because those are beyond the frozen canonical chart-only contract.

### Boundary/context only

These cases are valuable precisely because they expose information Micro v0.1 does not own. They must not be silently converted into primary failures.

- **AGPU — 2026-04-22.** The narration explicitly credits stacked Level-2 buyers and green time-and-sales with the anticipatory decision around support. This belongs to the future order-flow/context layer.
- **YOLO — 2025-09-09.** Attempted micro order was skipped/no-fill; later caution involved approximately 64M float, a topping tail and refusal to chase. This is primarily an upstream-selection/execution boundary case.
- **LABT — 2026-05-18.** Useful for front-side versus back-side behavior, whole-dollar heavy selling and later dip risk; several setup families are interleaved, so it is not reduced to one primary micro score.

### Ambiguous/excluded

- **ZEVAI — 2026-06-26.** The recap says the initial micro was skipped but also says it "could have, maybe should have" been taken. Later oversizing and a roughly $25k loss are explicit self-critique. The evidence is valuable for regime/risk research, but the initial skip is too ambiguous to score as correct behavior.

## Leakage rule

Every benchmark file uses:

`ground_truth_label_only_never_runtime_context`

The runtime replay must be produced first from market/news/reference data available at the historical timestamp. Benchmark labels may only be loaded afterward by a scorer. The suite loader validates references and rejects unsafe knowledge policies.

## Scoring discipline

A case is not a single binary "match". The manifest lists the dimensions on which a frozen policy may be evaluated. For example, VRAX may match pullback ordinal while disagreeing on trigger price. Those observations remain separate; there is no fitted weighted imitation score.

Boundary and ambiguous cases are structurally prevented from having scored dimensions in the manifest schema.

## Seed-suite limitations

This first ten-case set is deliberately small. It is intended to validate the benchmark architecture and produce the first cross-example results, not establish strategy profitability. The next expansion should add more negative outcomes, explicit no-trade examples, first-versus-second pullback cases, different price/float/RVOL buckets, and multiple market regimes before any benchmark score is treated as stable.

## Next execution step

For each primary/partial case:

1. reconstruct the causal market-selection timestamp;
2. download only the required historical SIP trade window;
3. derive and validate 10-second bars;
4. build completed-minute VWAP/EMA support with prior EMA warmup;
5. replay the **unchanged Micro v0.1 fingerprint**;
6. serialize a label-blind runtime artifact;
7. only then load the retrospective benchmark and compare the allowed dimensions.

The same runtime code and policy fingerprint must be used for every case. If a case motivates a new rule, that rule becomes a separately named ablation or future policy version rather than changing Micro v0.1 in place.
