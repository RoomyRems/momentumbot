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
- A corrected four-cell label-blind runtime must be generated for `YOUL` before any descriptive boundary comparison is recorded.
