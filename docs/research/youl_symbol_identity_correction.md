# YOUL benchmark symbol correction

## Outcome

The September 9, 2025 boundary benchmark's transcript-derived ticker `YOLO` is corrected to `YOUL` (Youlife Group Inc.). This is a benchmark-identity correction only. The human no-fill, topping-tail and later-caution labels are unchanged, and none of the identity evidence is available to runtime policy replay.

## Independent evidence

The first four-cell control against the listed security `YOLO` completed successfully in GitHub Actions run `31950276161`, but all four cells stopped upstream. Its raw market record had a $3.195 previous close, a $3.34 session high, only 1.67% maximum gain and 2.71x maximum same-time RVOL. That cannot be the stock described near $5.20 and later near $8, so the run is invalid as a strategy control.

A separate retrospective-only market-wide audit then screened 32,786 raw-SIP symbols in run `31950941920`. `YOUL` matched the unusually specific sequence:

| Evidence | YOUL observation |
|---|---:|
| Previous regular close | $1.77 |
| Rejection bar | 07:20 ET, high $5.20, close $4.80 |
| Later peak | 07:25 ET, $8.27 |
| Raw session volume | 91,178,693 |

The point-in-time SEC shell-company report for July 9, 2025 independently records 64,887,792 Class A ordinary shares and 11,160,808 Class B ordinary shares. The Class A count closely corroborates the recap's approximate 64M scanner figure, though it is not asserted to be a formal free-float calculation.

Price path, point-in-time share count and the near-identical transcript spelling jointly make the correction high confidence. Price similarity alone would not have been enough.

## Research handling

- The invalid `YOLO` four-cell run remains recorded at `research/benchmarks/results/micro-yolo-boundary-invalid-identity.json` and has no strategy implication.
- The identity audit is recorded at `research/benchmarks/results/youl-symbol-identity-audit.json` with `strategy_feedback: none`.
- The corrected `YOUL` benchmark remains `boundary_context_only` with no scored dimensions.
- The corrected four-cell label-blind runtime and post-replay comparison completed in workflow run `31951365058` at commit `f7401dff40664d14541515cd629d896c2ebfc13f`.

## Corrected four-cell control

The final comparison artifact is frozen at `research/benchmarks/results/micro-youl-boundary-comparison.json`. The GitHub Actions artifact `micro-youl-boundary-comparison` has artifact ID `9264829981` and digest `sha256:59198bfd913720661e152a2bf9512dede0ac01ddc48018ef13287a20b50c6da6`.

| Cell | Plans | Fills | First modeled fill |
|---|---:|---:|---:|
| Baseline | 12 | 8 | $2.82 / pullback #5 |
| Context only | 12 | 8 | $2.82 / pullback #5 |
| Volume only | 15 | 9 | $2.82 / pullback #5 |
| Context + volume | 15 | 9 | $2.82 / pullback #5 |

All cells acquired the candidate at 07:02 ET and refined causal qualification to 07:02:30 ET. The first plan was evaluated at 07:10:40 ET and the first modeled fill occurred at 07:10:55.482 ET at $2.82. Context has no effect on either activity or first-fill timing. Removing the hard volume gate adds three plans and one fill, all around pullback #12; the added fill is $4.94 at 07:20:48.788 ET. It does not change the first modeled opportunity.

The model therefore begins participating well before the observed 07:20 ET topping-tail episode and models repeated fills on a symbol where the human reported an attempted order but no completed trade. This target-only micro control omits full universe rank, point-in-time float eligibility and order-queue execution, so it cannot determine whether the discrepancy belongs to scanner selection, discretionary risk control or execution. It does establish that prequalification context does not repair the boundary and that disabling the volume gate increases later activity rather than improving the first opportunity.

This case retains zero scored dimensions and `strategy_feedback: none`. It is descriptive adverse boundary evidence for the volume-off ablation, not a promotion or rejection criterion by itself.
