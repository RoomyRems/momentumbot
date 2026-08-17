# Micro v0.2e qualification-anchored impulse-base results

Status: **rejected; not promoted**.

## Question

DSY and TIVC were often rejected before their reported early entries by the frozen `micro_retrace_above_half` translation. Micro v0.2e tests one categorical alternative without fitting a new threshold: keep the frozen strict-running-high peak and 50% limit, but measure the retracement denominator from the minimum post-qualification low through that peak instead of the minimum low in the parent's five-bar impulse window.

Only the retracement base changes. The parent's five-bar window still supplies impulse mean volume, and pullback duration, hard lower-volume gate, wick rule, VWAP/EMA9 support, trigger, stop, execution, action gate and pullback ordinal are unchanged. Pre-qualification prices remain unavailable.

## Paired input contract

The run did not reacquire market data. It downloaded the five exact label-blind runtime bundles from authoritative Micro v0.1 workflow run `31925087895`, verified each ZIP digest, and required the current parent replay to reproduce every frozen v0.1 runtime-core field before applying the ablation. Retrospective benchmark information was loaded only by the later comparison step.

- Ablation ID: `micro-v0.2e-qualification-anchored-impulse-base`
- Ablation fingerprint: `01d89b565a6fc82775af27a25e78b7775b8e635c432c3ff314f4e48c7d7a4402`
- Frozen parent fingerprint: `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`
- Successful workflow: run `32037408114`, head `afc2910eb48da3632303a9f47e47cd4cebb0e70e`

## Result

| Case | Frozen v0.1 first fill | v0.2e first fill | Plans v0.1 -> v0.2e | Main evidence |
|---|---:|---:|---:|---|
| ARTL | none | $7.36 / #3 | 0 -> 8 | late participation, not the upstream-incompatible ~$5.25 event |
| DSY | $8.50 / #10 | $8.50 / #10 | 2 -> 9 | first modeled trade unchanged |
| MMA | $4.02 / #3 | $4.02 / #3 | 1 -> 5 | first modeled trade unchanged |
| TIVC | $5.10 / #7 | $5.10 / #7 | 3 -> 11 | first modeled trade and ordinal unchanged |
| UPXI | $7.23 / #8 | $7.23 / #8 | 5 -> 10 | first modeled trade unchanged |

Aggregate plans increased from 11 to 43 (+32) and modeled fills from 7 to 16 (+9). The broad diagnostic rises from 8/12 to 10/12 only because ARTL gains a late plan and late fill; it does not recover the same reported human trade. No case with an existing baseline fill moves its first price or pullback ordinal.

## Decision

Do not promote v0.2e and do not modify Micro v0.1. A qualification-anchored minimum makes the 50% test progressively easier as a stock extends, increasing later opportunity density without solving the DSY/TIVC early-entry miss it was intended to isolate.

This closes only this base definition; it does not prove that the frozen five-bar impulse translation is uniquely correct. The five-case seed should not be mined for another geometry variant. A further Micro change requires a separately precommitted, representative validation design rather than another rule chosen from these labels.

## Provenance

- Permanent comparison: `research/benchmarks/results/micro-v0.2e-qualification-base-comparison.json`
- Runtime artifact: `9291337317`, digest `sha256:a1c90a49a04dc66d39abb06eb5740bdf85678d93dcc27c457e7b72fd92d1673c`
- Comparison artifact: `9291337519`, digest `sha256:da394d0f3da1895c46d9898d6d383bd09beb0d2ec577bf7c425b779e8005ad48`

The first workflow attempt, run `32036673146`, failed before MMA replay because the input loader incorrectly required unique trade timestamps. Frozen SIP tapes may contain multiple prints at the same timestamp; the execution engine already preserves their stable source order. Commit `afc2910eb48da3632303a9f47e47cd4cebb0e70e` removed uniqueness only for trades while retaining ordered/unique bar and support indexes. No strategy or result semantics changed.

