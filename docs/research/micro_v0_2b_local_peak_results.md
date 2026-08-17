# Micro v0.2b local-impulse-peak ablation

Status: **completed diagnostic ablation; not promoted**.

> **Source correction (2026-08-17):** ARTL's old Micro labels were misattributed from an earlier stock discussion and are retired. Excluding ARTL, both baseline and v0.2b score **8/10**; the apparent broad-score improvement disappears. See `docs/research/artl_source_label_correction.md`.

This experiment isolates the strongest structural hypothesis remaining after the v0.2a null result: Micro v0.1 may be too restrictive because it requires the setup peak to be a strict running high over the entire post-qualification structural window. A human trader can instead recognize a fresh local momentum impulse even when that impulse remains below an older high.

The ablation does **not** change Micro v0.1. It is separately identified, label-blind at runtime, and compared to the same frozen parent afterward.

## Authoritative provenance

- Ablation ID: `micro-v0.2b-local-impulse-peak`
- Ablation fingerprint: `1efa57eda100ab3f57b6e95015516e03715ff23dabbd67364bfe00d643b11aa9`
- Parent policy: `micro-v0.1`
- Parent fingerprint: `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`
- Authoritative GitHub Actions run: `31926360113`
- Runtime commit: `3a67e2ae794a5d134254c5700489d5495f26c956`
- Stored comparison: `research/benchmarks/results/micro-v0.2b-local-peak-comparison.json`

## Isolated change

Only the definition of the candidate peak changes.

- Frozen v0.1: a peak must exceed every earlier high in the post-qualification structural window.
- v0.2b: a peak need only be a strict high over the frozen parent's existing **5-bar impulse lookback**.
- No new lookback constant is introduced or fit to the benchmark labels.
- Pre-qualification context remains disabled exactly as in v0.1.
- Pullback ordinal remains observed from the actual qualification timestamp.
- Maximum 5-bar pullback duration, 50% retracement limit, lower-volume requirement, peak-wick rule, VWAP/EMA9 support, first-new-high trigger, pullback-low stop, SIP execution and causal qualification are unchanged.

## Result

The ablation changes behavior materially, but only one case gets a closer first fill and the additional activity is substantial.

| Case | v0.1 baseline | v0.2b local peak | First-fill alignment |
| --- | --- | --- | --- |
| DSY | 2 plans / 1 fill; $8.50 #10 | 18 plans / 7 fills; first $8.50 #10 | unchanged |
| MMA | 1 plan / 1 fill; $4.02 #3 | 1 plan / 1 fill; $4.02 #3 | unchanged |
| TIVC | 3 plans / 1 fill; $5.10 #7 | 11 plans / 3 fills; first $5.10 #7 | unchanged |
| UPXI | 5 plans / 4 fills; first $7.23 #8 | 27 plans / 10 fills; first $6.27 #6 | closer, but still far from ~$2.84 |

The historical artifact rose from 8/12 to 9/12 only because ARTL produced a setup plan. Once the invalid ARTL labels are excluded, both cells are **8/10 = 0.8**. The ablation still raises opportunity density substantially—plans rise from 11 to 57 and fills from 7 to 21 across the four valid cases—without improving their broad score.

The only first-fill price improvement is UPXI: the first modeled fill moves from $7.23 to $6.27. That is directionally earlier but remains $3.43 above the reported ~$2.84 reference. DSY and TIVC gain many additional plans/fills without moving the first trade toward the human entry. That is evidence that simply relaxing the global-running-high requirement can increase opportunity density much faster than it improves behavioral alignment.

## Case-level interpretation

### UPXI

UPXI remains the most informative micro-layer miss because the causal qualification occurs around **$2.82**, essentially beside the reported ~$2.84 entry. The runtime is therefore early enough; the setup translation is what delays participation. v0.2b moves the first fill earlier from $7.23/#8 to $6.27/#6, proving the global-running-high rule contributes to lateness, but it does not explain the initial missed trade by itself.

Inspection of the context-aware v0.2a replay shows that the near-entry structure immediately before UPXI's explosive continuation is rejected specifically by `micro_pullback_volume_not_lower`. Thus the next controlled question is whether the frozen hard volume-contraction gate is interacting with the information-boundary/context rule.

### MMA

MMA qualifies around $2.00 versus the retrospective ~$2.40 entry reference, so the scanner is also early enough. Its context-aware early replay likewise encounters `micro_pullback_volume_not_lower` before the later $4.02 fill. This provides a second case supporting a volume-gate experiment without relying on UPXI alone.

### DSY and TIVC

Both remain dominated earlier by `micro_retrace_above_half` and related structure failures. Their unchanged first fills under v0.2b indicate that the peak-scope rule is not the primary explanation for those misses. The frozen 50% retracement / impulse-base translation remains a separate future hypothesis rather than something to alter inside this experiment.

## Decision

- **Do not promote v0.2b.**
- **Do not modify Micro v0.1.**
- Preserve v0.2b because it demonstrates a real structural effect, but also a substantial increase in trade opportunity count without commensurate first-trade alignment.
- Test the lower-pullback-volume requirement next using a factorial design rather than jumping directly to a fitted threshold.

The next experiment should compare four causal cells on the same seed cases: baseline v0.1 (no pre-qualification context, hard lower-volume gate), v0.2a (context, hard lower-volume gate), a new no-context/no-hard-volume ablation, and a context + no-hard-volume interaction variant. The volume change should be binary—remove the hard rejection while retaining the volume measurements in the artifact—so no benchmark-fitted ratio threshold is introduced.
