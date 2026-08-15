# July 9, 2026 historical discovery reference

This directory freezes the **market-data-qualified** candidate set from the July 9, 2026 reference reconstruction. It is research input for SEC bulk float enrichment; it is not a claim that all listed symbols are valid Ross Cameron trades.

Provenance:

- historical reference workflow run: `31897605284`
- discovery code commit: `5881b3478237b261f79bbcf621ddc9a61369528b`
- split-basis regression tests: `8d71e0c43cb917a2f25059632b9fa57267e6dbb3`
- cleaned candidate count: **14**
- exact RVOL method: 50 prior sessions, cumulative volume compared at the same minute of day
- percent-gain basis: raw target-session prices compared with a split-consistent prior close
- execution prices remain raw historical prices
- SEC/API float was **not** used to create this candidate file

The prior discovery run produced 15 names because ENLV's July 9 1-for-15 reverse split made a raw `$0.4805` July 8 close incomparable with July 9's post-split price. The corrected discovery normalizes that boundary and ENLV disappears. A follow-up audit across all 14 retained candidates found no target-day raw/split basis mismatch.

`VRAX` remains independently rediscovered at 07:31 ET with about 94.5x exact same-time RVOL, matching the intended reference case.

## Local SEC enrichment

After the SEC bulk ZIPs are present at `data/sec/companyfacts.zip` and `data/sec/submissions.zip`, run from the repository root:

```powershell
python scripts/enrich_reference_2026_07_09_with_sec_bulk.py
```

The generated files go under `artifacts/sec-enrichment-2026-07-09/`, which is ignored by Git.
