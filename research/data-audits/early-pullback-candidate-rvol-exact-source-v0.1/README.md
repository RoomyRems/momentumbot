# Accepted exact-RVOL source evidence

Original independent proof: `original-verification.zip`, byte-pinned by the
source reader. Source capture metadata and implementation identity:
`source-evidence.json`. This work makes zero market-provider requests.

`integration/integration-report.json` binds thirty per-date `.json.gz` files,
their source provenance, exact aligned RVOL values and all comparison findings.
`integration.log` records the completed optimized offline run. The report seal is
`0a65a01ff43fa5e7c8b72d02bc6f960dc99dd1daae1e92bf17c7430e71bff2a0`.

Result: 2,101 ready cases, 159,079 RVOL values, eight reconciled target refreshes.
MGN/2026-03-25 and RUBI/2026-05-19 are withheld for 48 and 50 historical-session
volume disagreements. Their target buckets and timestamps agree; historical
consistency is still unavailable. No multiplier or threshold was fitted.

These are immutable child records of the original captures. Correct future
interpretations through additive evidence, not by rewriting these bytes.
The source adapter and reproduction contract are documented in
[the research note](../../../docs/research/candidate_rvol_exact_source.md).
