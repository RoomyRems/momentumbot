# Sealed historical source recovery v0.6

## Status and purpose

Run `33516311649` permanently consumed source-acquisition v0.5 and failed on
the third recovered float candidate, `CHEB`. The exact v0.5 failure checkpoint
contains all 30 label-blind market-discovery dates: 523 normalized source files,
66 directories, 946 candidates, and 537,662,001 retained bytes. Its source-tree
commitment is
`03182a9b2ccaf026589986f73f6bb3e3c156b360eee5e0cae3f8fc31b1537607`.

The failure was not caused by provider data. The upstream identity contract
uses exactly `composite_figi` and `unique_cik_fallback`; the consumed float
validator instead admitted the obsolete label `cik` and rejected
`unique_cik_fallback`. Provider-free replay proves all 946 candidates satisfy
the authoritative upstream contract: 737 use Composite FIGI and 209 use the
unique-CIK fallback.

v0.6 is an additive one-shot recovery child. It leaves every v0.4 and v0.5
artifact byte-for-byte reproducible, reuses the exact v0.5 checkpoint, and
changes only the downstream identity-vocabulary compatibility boundary. Its
authorization content SHA-256 is
`0343efff8ceb49b7c3ae2e589029cf4cf0b02d72c1961f85807913f67385202e`.
It has not been consumed or dispatched.

## Identity repair

The v0.6 float adapter performs an all-candidate provider-free preflight before
the float parent can access a provider. It accepts only:

- `composite_figi`, when the identifier exactly equals the selected Composite
  FIGI; and
- `unique_cik_fallback`, when there is no selected Composite FIGI and the
  identifier exactly equals the unique selected CIK.

It rejects `cik`, missing identifiers, ambiguous FIGI/CIK combinations, changed
identifier values, unexpected symbols, and any third identity kind. It never
rewrites an identity. During the immutable parent call, only the private
identity-validation function is temporarily rebound; it is restored even if
the parent fails.

The v0.5 candidate-level containment remains unchanged: provider-frame
`TypeError` or `ValueError` failures reject only that symbol-date as
`unknown_fail_closed_missing_measure_pair`. Transport, HTTP, pagination,
authorization, request-budget, artifact-integrity, and recovered-source errors
remain fatal. No float formula, threshold, scanner profile, Micro-v0.1 rule,
news rule, account rule, or order authority changes.

## Exact parent and request boundary

Before v0.6 can be consumed, the workflow downloads and validates GitHub
artifact `9803791643` from run `33516311649`, verifies its ZIP digest
`0c40d099acf86fef16203f8dc7fefb104abd71668a37ffc6e450e2513d469c35`,
rehashes every retained file, compares the pinned environment, reloads every
candidate and target-basis artifact, and validates all 946 identities.

The composite request ledger starts at the exact v0.5 terminal counts:

- Massive: 363
- Alpaca: 14,161
- SEC: 12
- Total: 14,536 of the unchanged 40,000 ceiling

Massive, identity, and market-discovery entry points cannot run in v0.6. The
child provider wrapper allows only the repaired float builder, unchanged news
builder, and unchanged canonical scanner-input builder; the active network
host set is limited to Alpaca and SEC. Every new attempt increments the inherited
ledger.

## Durable execution order

1. Validate the frozen v0.6 authorization, registration, v0.5 failure audit,
   exact parent artifact metadata, and clean pinned environment without
   provider credentials.
2. Download and deeply replay the exact v0.5 failure checkpoint, including the
   all-946 identity preflight, before authorization consumption.
3. Create the v0.6 consumption marker and atomically create its durable Git tag.
4. In a fresh job, revalidate the marker/tag and exact parent artifact, then
   materialize the unchanged normalized source and seed the 14,536-request
   ledger.
5. Run repaired float enrichment, unchanged news enrichment, and unchanged
   canonical scanner-input acquisition.
6. Upload the hash-inventoried pre-scanner provider checkpoint.
7. In a separate credential-free job, rehash that checkpoint, freeze scanner
   snapshots, deeply replay all 30 dates, and seal the final report.

The pre-scanner checkpoint requires exactly 706 source files. The final binding
requires exactly 767 files and permits only the 61 scanner-snapshot files to be
added after provider access. Safe-failure artifacts retain sanitized accounting
and complete recoverable label-blind data, never raw provider responses.

No transcript record, Ross action/fill/skip/label, later outcome, Databento
route, brokerage account, or order endpoint is available to this workflow.
Retrospective comparison remains blocked until scanner and Micro outputs are
frozen label-blind.
