# Micro v0.2a pre-qualification context ablation

Status: **completed null-result research ablation; not promoted**.

This experiment isolates one hypothesis raised by the frozen Micro v0.1 seed benchmark: perhaps the deterministic model misses Ross Cameron's earliest micro pullbacks because it discards completed 10-second chart structure that existed immediately before the causal scanner qualification timestamp.

The ablation does **not** change Micro v0.1. It is a separately identified research policy layered on top of the frozen parent fingerprint.

## Authoritative provenance

- Ablation ID: `micro-v0.2a-prequalification-context`
- Ablation fingerprint: `cdd9c1a18abf23a03aac67568f1c3b976bd4ab968a07f46966940b5e81feb49e`
- Parent policy: `micro-v0.1`
- Parent fingerprint: `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`
- Authoritative GitHub Actions run: `31925898386`
- Runtime commit: `257f6a32b9ec0b089df1c97db29040d91c6c0150`
- Stored comparison: `research/benchmarks/results/micro-v0.2a-context-comparison.json`

## Isolated change

Only the setup detector's structural-history start changes.

- Requested pre-qualification context: **10 completed 10-second bars / 100 seconds**.
- The 10-bar bound was not fit to the labeled cases. It is derived mechanically from the frozen parent's existing 5-bar impulse lookback plus 5-bar maximum pullback duration.
- A pre-qualification bar is usable only if the entire 10-second bucket had completed by the actual causal qualification timestamp.
- Evaluation/action still begins only after actual qualification.
- No plan may be armed or filled before qualification.
- Pullback ordinal remains anchored at actual qualification, exactly as in the parent replay, so the experiment does not change a second variable.
- Retracement, volume, wick, VWAP, EMA9, trigger, stop and SIP execution semantics remain the frozen parent's rules.

## Result

The ablation changes **none of the five primary seed cases' modeled trade outcomes**.

| Case | Completed pre-alert context available | v0.1 baseline | v0.2a context ablation | Alignment change |
| --- | ---: | --- | --- | --- |
| ARTL | 10 bars | no plan / no fill | no plan / no fill | no fill either |
| DSY | 6 bars | first fill $8.50, #10 | first fill $8.50, #10 | unchanged |
| MMA | 10 bars | first fill $4.02, #3 | first fill $4.02, #3 | unchanged |
| TIVC | 4 bars | first fill $5.10, #7 | first fill $5.10, #7 | unchanged |
| UPXI | 3 bars | first fill $7.23, #8 | first fill $7.23, #8 | unchanged |

The broad behavioral score is therefore also unchanged at **8 / 12 comparable dimensions = 0.667**. As with the parent seed summary, this is not exact-trade imitation accuracy and not a profitability statistic.

Importantly, MMA and ARTL both had the full requested 10 completed bars available. The null result therefore cannot be dismissed solely as a consequence of sparse pre-alert history.

## Interpretation

The seed evidence does **not** support promoting pre-qualification context as a meaningful fix by itself. The causal information boundary was worth testing because a human does see the already-formed chart when a scanner alert fires, but simply exposing that bounded history to the unchanged strict-running-high setup detector does not recover the human entries.

This materially strengthens the next hypothesis: the more important mismatch is likely the frozen definition of a valid impulse peak. Micro v0.1 requires a strict running high over the entire post-qualification structural window. Ross's examples appear compatible with a **local momentum impulse high** that can form below an earlier session high.

The very high `no_current_running_high_pullback` rejection counts seen in the parent seed suite remain consistent with that interpretation. v0.2a did not change that peak rule, so its inability to alter the actual fills is expected in hindsight but was not assumed before running the experiment.

## Decision

- **Do not promote v0.2a.**
- **Do not modify Micro v0.1.**
- Preserve this null result so it is not repeatedly rediscovered or selectively forgotten.
- Proceed to an independent local-impulse-peak ablation with no pre-qualification context added.
- Only after both effects are measured separately should a combined context + local-peak variant be considered.

The next ablation should replace the parent requirement "peak must exceed every earlier post-qualification high" with a causal local-high rule using only the already-frozen parent impulse lookback. That avoids introducing a new fitted lookback constant while directly testing the strongest remaining structural hypothesis.
