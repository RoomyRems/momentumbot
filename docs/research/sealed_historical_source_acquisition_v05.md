# Sealed historical source recovery v0.5

## Status and purpose

Run `33468687163` permanently consumed source-acquisition v0.4 and then failed
in the first float-enrichment date. All 30 identity and split-consistent market
dates had completed. The failure checkpoint contains 523 normalized source
files (537,662,001 bytes) with source-tree commitment
`03182a9b2ccaf026589986f73f6bb3e3c156b360eee5e0cae3f8fc31b1537607`.

Provider-free replay validates all 946 market candidates and every exact
qualification-minute raw/split target pair. The retained tree therefore is not
the source of the exception. A candidate-specific provider response raised a
`ValueError` while the float builder was downloading or converting the daily
raw/split measure basis. The v0.4 safety wrapper correctly suppressed the raw
response and exception message, so the exact offending field cannot be
reconstructed.

v0.5 is a one-shot continuation child. It does not rerun v0.4 and does not
repeat Massive membership, identity, SIP coverage, corporate-action, or market
discovery requests. It downloads the exact GitHub failure-checkpoint artifact,
rehashes its complete normalized source tree, independently reloads the 30
identity/market/target-basis bundles, and resumes at float enrichment.

The frozen v0.5 authorization content SHA-256 is
`23ad997837490c14c200c10b34c8285db7b18ddebca131e6299a8cd70b3bbc49`.
It has not been consumed or dispatched.

## Candidate-level repair

The frozen float policy already specifies that a missing or malformed measure
basis produces an unknown, fail-closed float result. The v0.4 implementation
violated that policy only because provider-to-DataFrame `TypeError` or
`ValueError` exceptions escaped the candidate loop.

The v0.5 adapter contains only that provider-derived measure-basis boundary:

- `TypeError` or `ValueError` while downloading, converting, observing, or
  validating one candidate's daily raw/split measure basis rejects that one
  symbol-date.
- Recovered candidate identity, exact qualification-minute target basis, target
  date, and source hashes are prevalidated outside the contained exception
  boundary. A failure in one of those invariants remains fatal.
- The unchanged float policy records the candidate as
  `unknown_fail_closed_missing_measure_pair` and continues.
- A sanitized sidecar retains only date, symbol, stage, exception class, and
  disposition. It never retains the exception message, URL, provider payload,
  credential, or raw response.
- Transport failures, HTTP failures, pagination failures, request-ceiling
  exhaustion, blocked hosts, authorization failures, source tampering, and
  downstream artifact-validation failures remain fatal.
- A rejected candidate cannot retain a partially valid observation: final
  record construction receives no provider-derived disclosure or daily basis.
- The diagnostic must be unique by date/symbol, match a real recovered market
  candidate, and remain within the exact 946-candidate census.

The adapter does not alter float math, the $10 million threshold, scanner
profiles, Micro-v0.1, account rules, news rules, rank rules, or any order
authority.

## Composite request and provenance boundary

The child request ledger begins at the exact parent total, not zero:

- Massive: 363
- Alpaca: 14,155
- SEC: 6
- Total: 14,524 of the unchanged 40,000 ceiling

The v0.5 provider allowlist contains only float, news, and canonical scanner
source-input entry points. The parent Massive/identity/market builders are not
callable through the v0.5 wrapper, and the active child transport guard permits
only Alpaca and SEC; Massive is rejected before network access. New requests add
to the parent counts, so the combined parent-plus-child experiment cannot
exceed 40,000 attempts.

## Durable execution order

1. Validate the v0.5 authorization and permanent v0.4 failure audit without
   providers.
2. Before consumption, download and replay the exact retained parent artifact,
   require every third-party environment line to match, and independently bind
   each editable project line to its own authorized Git commit.
3. Create and persist a distinct v0.5 consumption tag before provider access.
4. Download the exact run `33468687163` failure-checkpoint artifact again.
5. Verify its artifact identity, source-tree hash/count/bytes, environment,
   request accounting, and all 30 identity/market/target-basis bundles.
6. Copy the exact normalized parent source and seed the composite request ledger
   at 14,524.
7. Resume with candidate-contained float normalization, then news and canonical
   scanner source inputs.
8. Upload a hash-inventoried provider checkpoint.
9. In a separate credential-free job, rehash the checkpoint, freeze scanner
   snapshots, deeply replay all 30 dates, and seal the final report.

The pre-scanner checkpoint requires exactly 706 source files. It binds the
parent recovery receipt, sanitized normalization diagnostics, pinned
environment, all six stage manifests, composite request ledger, empty
blocked-attempt ledger, and every source byte. The final binding requires
exactly 767 files and permits only the 61 scanner snapshot files to be added.

The dispatcher canonicalizes harmless leading/trailing form whitespace before
validating the exact 40-character commit and tree. Every new script is tested
through the same direct `python scripts/...` invocation used by GitHub, not
only as an imported unit-test module.

No transcript record, Ross action/fill/skip/label, later outcome, Databento
route, brokerage account, or order endpoint is available to this workflow.
Retrospective comparison remains blocked until scanner and Micro outputs are
frozen label-blind.
