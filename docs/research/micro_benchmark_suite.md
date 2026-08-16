# Micro v0.1 multi-example benchmark suite

The benchmark suite exists to answer a harder question than "can MomentumBot reproduce VRAX?": **does one frozen chart-only micro policy behave sensibly across materially different historical examples without being rewritten for each stock?**

The seed manifest is `research/benchmarks/suites/micro-v0.1-seed.json`. It currently contains ten retrospective cases selected from the transcript corpus. The first five primary cases have now been reconstructed and scored with the unchanged Micro v0.1 fingerprint; see `docs/research/micro_v0_1_seed_results.md`.

## Case roles

### Primary scored

These examples are close enough to the canonical chart-only micro family that Micro v0.1 is allowed to be judged on explicitly listed dimensions.

- **DSY — 2026-06-10.** Current-era 10-second micro; recap explicitly restates crossing-candle / first-new-high entry language and gives approximate fills near $3.07/$3.11.
- **TIVC — 2025-04-03.** First micro pullback taken with reported fills at $4.73/$4.76/$4.89 and about $3,000 on the first trade.
- **UPXI — 2025-04-21.** Initial 10-second entry is explicitly described as first candle to make a new high at about $2.84, with a later pullback described as picture perfect.
- **MMA — 2025-09-09.** Explicit 10-second micro entry around $2.40 followed by continuation through $3.
- **ARTL — 2026-03-27.** Deliberate losing example: entry around $5.25 on a micro pullback, brief progress, then topping-tail rejection and a reported roughly $2,400 first-trade loss. The transcript-derived ticker was originally `ONCS`; independent same-day market verification showed that `ARTL` matches the date and unusually specific $3-to-$12.45 price path. The benchmark preserves the original transcript label and correction provenance.

Including ARTL is intentional. A benchmark suite made only from clean winners would be structurally biased toward finding entries and would tell us little about failure handling.

### Partial scored

- **VRAX — 2026-07-09.** Micro v0.1 may be judged on recognizing the setup family, not taking the first pullback, and identifying the second pullback. It is **not** judged on reproducing the human $6 whole-dollar continuation trigger or ~$6.30 fill because those are beyond the frozen canonical chart-only contract.

### Boundary/context only

These cases are valuable precisely because they expose information Micro v0.1 does not own. They must not be silently converted into primary failures.

- **AGPU — 2026-04-22.** The narration explicitly credits stacked Level-2 buyers and green time-and-sales with the anticipatory decision around support. This belongs to the future order-flow/context layer.
- **YOUL — 2025-09-09.** Attempted micro order was skipped/no-fill; later caution involved approximately 64M float, a topping tail and refusal to chase. The transcript-derived `YOLO` label was corrected to `YOUL` only after an independent retrospective identity audit matched the $5.20 rejection, later ~$8 high and point-in-time share count. This is primarily an upstream-selection/execution boundary case; see `docs/research/youl_symbol_identity_correction.md`.
- **LABT — 2026-05-18.** Useful for front-side versus back-side behavior, whole-dollar heavy selling and later dip risk; several setup families are interleaved, so it is not reduced to one primary micro score.

### Ambiguous/excluded

- **ZEVAI — 2026-06-26.** The recap says the initial micro was skipped but also says it "could have, maybe should have" been taken. Later oversizing and a roughly $25k loss are explicit self-critique. The evidence is valuable for regime/risk research, but the initial skip is too ambiguous to score as correct behavior.

## Leakage rule

Every benchmark file uses:

`ground_truth_label_only_never_runtime_context`

The runtime replay must be produced first from market/news/reference data available at the historical timestamp. Benchmark labels may only be loaded afterward by a scorer. The suite loader validates references and rejects unsafe knowledge policies.

## Scoring discipline

A case is not a single binary "match". The manifest lists the dimensions on which a frozen policy may be evaluated. For example, VRAX may match pullback ordinal while disagreeing on trigger price. Those observations remain separate; there is no fitted weighted imitation score.

For the primary seed run, `setup_detected` and `entry_participation` are explicitly **broad behavior** dimensions: any later valid plan/fill inside the eligible post-qualification window can match them. They do not prove that the model reproduced the same human trade. The scorer therefore exposes reported-entry differences and pullback ordinals descriptively and leaves the exact-human-trade aggregate score unset.

Boundary and ambiguous cases are structurally prevented from having scored dimensions in the manifest schema.

## Completed primary seed execution

Authoritative run: GitHub Actions `31925087895` on runtime commit `37b8f45f13e6e2f0159c9d307a2a14333d237ab8` with frozen policy fingerprint `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`.

The five primary cases produced 8 matches across 12 comparable **broad behavior** dimensions. This 0.667 descriptive fraction is not imitation accuracy: DSY, MMA and UPXI find materially later trades, TIVC fills pullback #7 rather than the labeled first pullback, and ARTL produces no post-qualification v0.1 plan. Exact-human-trade identity is intentionally not aggregated.

The strongest cross-case research findings are:

1. the frozen strict-running-high peak definition appears substantially more restrictive than the human local-impulse interpretation; and
2. resetting all micro structural history at candidate qualification can erase already-visible completed chart context just before a fast setup.

These findings are documented in `docs/research/micro_v0_1_seed_results.md`. They are hypotheses for separately named ablations, not changes to Micro v0.1.

## Seed-suite limitations

This first ten-case set is deliberately small. It validates the benchmark architecture and produces the first cross-example findings; it does not establish strategy profitability. The next expansion should add more negative outcomes, explicit no-trade examples, first-versus-second pullback cases, different price/float/RVOL buckets, and multiple market regimes before any benchmark statistic is treated as stable.

## Next research step

Keep Micro v0.1 unchanged and evaluate isolated candidate improvements against the same frozen cases before combining them. The first recommended ablation is bounded **pre-qualification structural context**: completed 10-second bars that already existed before the causal scanner alert may inform the first post-qualification pattern, while no order may be armed or filled before qualification. A separate local-impulse-peak ablation should then test the strict-running-high hypothesis independently.

Any rule motivated by these results must become a separately named research policy/version and later be checked on additional held-out transcript cases and broader walk-forward days rather than optimized only against this seed suite.

