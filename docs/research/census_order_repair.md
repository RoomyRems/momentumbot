# Census provider-order repair

## Verified fault and repair

The immutable diagnostic code is `7bba0854cbfbf58dbe79ce3f0fd8b6f3ac02ee17`.
Its [full CI](https://github.com/RoomyRems/momentumbot/actions/runs/34715001971)
ran 2,750 tests, with 73 optional SDK skips, and compiled successfully. The
[diagnostic](https://github.com/RoomyRems/momentumbot/actions/runs/34715001958)
then completed exactly one HTTP-200 request, with no retry or pagination.

The retained 293,790-byte response contains 1,000 tickers, correctly ordered by
their exact provider spelling. Uppercasing first introduces eleven false order
regressions: for example, `ACRV` followed by `ACRpC` becomes `ACRV`, `ACRPC`.
The unchanged parser reproduces `provider page order regressed` on these bytes.
The original failed census body was not retained and has a different hash;
this is not a claim of byte-identical reproduction of that unavailable body.

`census_order_repair.py` separates the two representations:

- Validate within-page and cross-page order against exact provider tickers.
- Keep the existing canonical normalization, membership identities, duplicate
  rejection, missing metadata and ticker-collision accounting unchanged.
- Retain provider tickers in the projection and its hash chain. Empty pages do
  not erase the preceding page's boundary.
- Reject raw regressions even when uppercasing would conceal them. Do not relax
  cursor host/query restrictions, count/schema filters, date selection or limits.

The raw page is checked before constructing a separate canonical-sorted
validation view. The frozen parser validates that view for every other rule;
the original response is never rewritten, rehashed as the view, or replaced.
The repaired state still binds the following request to the original response
hash. This narrow extension reuses the existing schema and pagination machinery
without modifying any frozen parent source or previously consumed launcher.

## Evidence and validation

Both original GitHub ZIP digests, every retained member, independent preflight
pin, CI/code/run/ref identities, successful job steps and one-request report are
reverified by the offline evidence reader. Original artifacts and logs are under
`research/data-audits/early-pullback-census-diagnostic-v0.1/`.
Diagnostic verification: `a8e5dc575eec599c0aac420a4909825550c7b150fd494d05a2ae1e5e351077c0`.

All 90 focused tests passed normally (4.272 seconds) and optimized (4.480 seconds):
29 new repair tests plus 61 existing adapter/diagnostic tests. They cover the
actual retained page, both directions of the case-order error, empty-page
boundaries, duplicate identity, unchanged schema/cursor guards, all 30 dates in
a synthetic 61-request protocol, and the synthetic 601-request maximum. These
synthetic checks are not historical market captures. Compilation also passed.
Code `5fac11a900dea3f603442798022870608d358635` passed the authoritative
[GitHub CI run](https://github.com/RoomyRems/momentumbot/actions/runs/34716020057):
2,779 tests in 418.048 seconds, 73 pinned-SDK skips, all 29 new checks passed,
and successful compilation. All six legacy validations passed; their provider
jobs were skipped. The original CI log, job/run receipts and verification report
are retained alongside the repair audit. No provider call occurred in this code
verification and no duplicate full local suite was run.

The evidence-only follow-up uses GitHub's documented
[workflow-skip commit directive](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).
It changes only documentation and saved CI evidence, not code, tests, workflows,
registrations or execution authority. This is not a substitute for exact-code CI
on the next executable change and does not authorize a provider job.

```bash
PYTHONPATH=src python scripts/verify_census_order_repair.py
PYTHONPATH=src python -m unittest tests.test_census_order_repair -v
```

## Remaining work and scope

This is an offline protocol repair, not a new full-census launch. The old
launchers deliberately remain frozen. The next implementation must wire this
projection and state into the bounded collector **and its raw-archive verifier**,
retain safe failures, and use a fresh single-use execution after exact-code CI.
Reuse the streamlined CI/consumption mechanism; do not add approval-only commits
or rerun a duplicate local full suite. The owner's continuing authorization is
already recorded; a new subscription, expanded dataset or live-order scope is
not included.

The diagnostic page stays quarantined. No backtest, historical identity
acceptance, financial evaluation, parameter tuning or transcript ingestion took
place. Actual billing remains unverified. The incomplete deterministic baseline
does not establish the full hybrid strategy's edge; crucial discretionary
integration remains outstanding and profitability is not guaranteed.
