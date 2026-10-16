# Verification — exact-minute RVOL source integration

Status: focused checks and all-date integration passed within scope; two source
cases remain unavailable. This record is frozen before the final branch update;
the published checkpoint's exact-commit CI is the hosted acceptance authority.

## Inputs and identity

[Scope](01_scope.md), [change](02_change.md). Implementation source commit
`b83b5dba644cc237ed1cb41fc10dc59b27c65995`, tree
`ee3f955c664d1ed48e75027e7aa64c1862830594`. The code under the offline audit
is unchanged from this tree; no provider or policy operation is launched.

## Focused results

With `PYTHONPATH=src:scripts`, both normal and optimized invocations of
`python -m unittest tests.test_candidate_rvol_exact_source tests.test_rvol tests.test_scanner_rvol_alignment_v10 -v`
passed all 18 tests. The new suite contributes eleven checks. Compilation passed.
An initial test-fixture run had one error because its empty synthetic frame used
a timezone-naive index; the fixture was corrected to explicit UTC and both final
runs passed. Production empty-frame projection already preserved UTC.

No full local suite was run. One full hosted CI run is required for the published
checkpoint. Queued or in-progress CI is not acceptance.

## Source and impact review

Original capture ZIPs were recovered from their known GitHub artifact IDs and
matched all recorded byte sizes/SHA-256 values. The exact proof was pinned and
preserved. The original independent archive verification is reused, not repeated
as a separate full archive-verification job. The new integration validates the
page projections and comparisons required by its different source contract.

Cold-walk: root → status → scanner reconstruction/source-capture cards → exact
source reader → offline audit. The route distinguishes source curves from the
still-incomplete full captured-source scanner adapter and descriptive shadow.
Reviewed the new source reader and the existing RVOL/alignment consumers. Updated
only the affected source/scanner cards and their lock entries; existing source
fingerprints are unchanged. Navigation maintenance passed at the implementation
stage and will be refreshed after the final evidence is added.

## All-date integration

Optimized offline audit completed normally (exit 0) using the exact implementation
above. Network/process I/O was denied inside the integration process.

- Thirty dates, 2,103 retained cases and 105,150 prior-session comparisons.
- All 3,309,900 exact-capture bars accounted for, including target refreshes.
- All eight target refreshes reconcile to the coarse buckets and raw timestamps.
- 2,101 ready cases produce 159,079 exact RVOL observations; 4,663 exhausted
  empty historical sessions remain explicit.
- MGN/2026-03-25 (48 sessions) and RUBI/2026-05-19 (50 sessions) have historical
  volume disagreements. Their curves are withheld. Target buckets/timestamps
  match for both, so that alone is insufficient for acceptance.

The [sealed report](../../../../research/data-audits/early-pullback-candidate-rvol-exact-source-v0.1/integration/integration-report.json)
has seal `0a65a01ff43fa5e7c8b72d02bc6f960dc99dd1daae1e92bf17c7430e71bff2a0`.
It pins all thirty per-date files. The
[source evidence](../../../../research/data-audits/early-pullback-candidate-rvol-exact-source-v0.1/source-evidence.json)
records original artifact identities, byte hashes and the implementation tree.
The original capture, coarse filter, exclusions and failed evidence are unchanged.

Two additional frozen-evidence checks validate report/file seals, the exact
retained population, timestamp order/window, nonfinite encoding and unavailable
case exclusion. The final normal and optimized focused runs both passed 20 tests. Their logs
are preserved as `focused.log` and `focused-optimized.log` in the source-audit
directory.
No whole-suite local replay or repeated provider capture was performed.

## Hosted boundary

Publish the child evidence/navigation tree once to the existing active branch.
One authoritative full GitHub CI run must pass on that published tree. This
pre-publication record does not claim an unobserved hosted pass. The final user
handoff and GitHub run provide the actual publication/CI identities.
