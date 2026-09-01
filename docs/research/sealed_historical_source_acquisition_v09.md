# Sealed historical source recovery v0.9

## Status and purpose

Run `33543415600` dispatched v0.8 once and failed closed in validation at
`Preflight exact retained parent artifact metadata before consumption`. All
authorization, commit/tree, pinned-environment, focused, optimized and compile
gates before it passed. The single-fetch validator reported the exact sanitized
field `digest`, so the mismatch was fully recoverable. Consume, acquire and
freeze were skipped. No consumption tag, run artifact or provider request was
created, and v0.8 may not be rerun.

The v0.8 preregistration contained a mistyped v0.6 checkpoint ZIP SHA-256. The
live GitHub metadata and the independently downloaded, archive-verified ZIP
both bind the correct value:
`ab51a247d4fc86b61d0099087721987b704def9d1086c6cdafb7767d63fa8b6e`.
v0.9 corrects only this provider-free provenance value and adds a frozen
real-metadata fixture plus a byte-recomputed ZIP cross-check. The validator
cannot derive its expected digest solely from the constant under test.

The exact retained v0.6 checkpoint contains 584 normalized source files in 97
directories, 542,222,230 retained bytes, and source-tree commitment
`7eec4b420581efa52e39208952f386d4f81a092a39bca5c4acaaee7da642740c`.
Its complete float root is committed by
`eac2a02d24cb0106181480355778c5094ed9436769d75356bd2d1ee90de4a9cc`.

v0.9 is an additive, one-shot recovery child. It leaves v0.8 and every consumed
v0.6 file reproducible, reuses the exact retained source, preserves the v0.8
downstream identity repair, and changes only the provider-free artifact-metadata
digest binding and its regression evidence. Scanner profiles, thresholds, Micro-v0.1, news rules, float
calculations, account rules, and order authority do not change.

## Artifact metadata repair

Each validation gate calls GitHub once and writes the full response to a bounded
regular JSON file. The v0.9 validator rejects duplicate keys, non-finite values,
symlinks, empty or oversize input, boolean/integer type confusion, and any
change to artifact ID, name, digest, byte size, parent run or `expired: false`.
It returns a hash-bound provider-free receipt and exposes only the field name on
failure, never an unbounded response value. A registration-bound sanitized
fixture freezes the independently observed GitHub fields, and its digest must
equal the independently downloaded ZIP SHA-256. The artifact is still
downloaded, rehash-verified and deeply replayed before authorization
consumption.

## Downstream compatibility repair

The v0.9 compatibility scope accepts exactly the upstream identity contract:

- `composite_figi`, when the stable identifier equals the selected Composite
  FIGI; and
- `unique_cik_fallback`, when no Composite FIGI exists and the stable
  identifier equals the selected unique CIK.

It rejects obsolete `cik`, missing identifiers, ambiguous FIGI/CIK states,
changed values, and any third kind. It never rewrites a candidate identity or
float record. The legacy private validator is rebound only while downstream
float artifacts are loaded and is restored even if validation fails.

Before v0.9 can be consumed, a provider-free preflight deep-loads the complete
float root and every date manifest, candidate payload, target-basis record, and
float record. The frozen receipt requires exactly 946 candidates, 946 float
records, 737 Composite FIGI identities, and 209 unique-CIK fallbacks. The same
scope wraps both the publication-timed news builder and canonical scanner-input
builder, preventing the mismatch from recurring at the next stage.

## Exact parent and request boundary

The parent artifact is GitHub artifact `9806541315` from run `33521937708`,
attempt 1, named
`sealed-historical-source-acquisition-v06-failure-checkpoint-33521937708-1`.
Its ZIP SHA-256 is
`ab51a247d4fc86b61d0099087721987b704def9d1086c6cdafb7767d63fa8b6e`.
The failure summary and consumption-marker ZIP hashes are independently bound
by the v0.6 permanent failure audit.

The composite request ledger begins at:

- Massive: 363
- Alpaca: 15,849
- SEC: 1,328
- Total: 17,540 of the unchanged 40,000 ceiling

No Massive, identity, market-discovery, SEC, or float acquisition entry point
is available to v0.9. The child transport guard admits only
`data.alpaca.markets`, and only the news and canonical scanner-source adapters
can run. The completed float stage is reused byte-for-byte.

## Durable execution order

1. Validate the frozen v0.9 authorization, registration and exact v0.8 safe
   failure without provider secrets.
2. Fetch the exact v0.6 checkpoint artifact metadata once, validate the typed
   field-specific receipt, then download, rehash and replay the checkpoint,
   including all 946
   candidates and float records, before authorization consumption.
3. Create the v0.9 consumption marker and atomically create its protected Git
   tag.
4. In a fresh job, revalidate the marker, tag, parent checkpoint, and 17,540
   request seed; materialize the source byte-for-byte.
5. Run the identity-compatible unchanged news builder, followed by the
   identity-compatible unchanged canonical scanner-source builder.
6. Upload the 706-file pre-scanner provider checkpoint.
7. In a separate credential-free job, rehash that checkpoint, add only the 61
   expected scanner snapshot files, deeply replay all 30 dates, and seal the
   767-file final source bundle and scanner replay.

No transcript record, Ross action/fill/skip/label, later outcome, Databento
route, brokerage account, or order endpoint is available. Retrospective
comparison remains blocked until the label-blind scanner and Micro artifacts
are frozen.
