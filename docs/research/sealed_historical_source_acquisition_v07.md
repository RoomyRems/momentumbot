# Sealed historical source recovery v0.7

## Status and purpose

Run `33521937708` permanently consumed v0.6 and completed target-date float
acquisition for all 30 dates and 946 candidates. It then failed at step 12,
`Acquire publication-timed causal news inputs`, before constructing the news
provider client. The unchanged news builder deep-loaded the completed float
root through the legacy `historical_float_v04` identity validator. That
validator recognizes obsolete kind `cik` but rejects the authoritative
`unique_cik_fallback` kind used by 209 candidates.

The exact retained v0.6 checkpoint contains 584 normalized source files in 97
directories, 542,222,230 retained bytes, and source-tree commitment
`7eec4b420581efa52e39208952f386d4f81a092a39bca5c4acaaee7da642740c`.
Its complete float root is committed by
`eac2a02d24cb0106181480355778c5094ed9436769d75356bd2d1ee90de4a9cc`.

v0.7 is an additive, one-shot recovery child. It leaves every consumed v0.6
file and artifact reproducible, reuses the exact retained source, and changes
only the downstream identity-validation compatibility boundary. Scanner
profiles, thresholds, Micro-v0.1, news rules, float calculations, account
rules, and order authority do not change.

## Downstream compatibility repair

The v0.7 compatibility scope accepts exactly the upstream identity contract:

- `composite_figi`, when the stable identifier equals the selected Composite
  FIGI; and
- `unique_cik_fallback`, when no Composite FIGI exists and the stable
  identifier equals the selected unique CIK.

It rejects obsolete `cik`, missing identifiers, ambiguous FIGI/CIK states,
changed values, and any third kind. It never rewrites a candidate identity or
float record. The legacy private validator is rebound only while downstream
float artifacts are loaded and is restored even if validation fails.

Before v0.7 can be consumed, a provider-free preflight deep-loads the complete
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
`ab51a247d4fc86fef16203f8dc7fefb104abd71668a37ffc6e450e2513d469c35`.
The failure summary and consumption-marker ZIP hashes are independently bound
by the v0.6 permanent failure audit.

The composite request ledger begins at:

- Massive: 363
- Alpaca: 15,849
- SEC: 1,328
- Total: 17,540 of the unchanged 40,000 ceiling

No Massive, identity, market-discovery, SEC, or float acquisition entry point
is available to v0.7. The child transport guard admits only
`data.alpaca.markets`, and only the news and canonical scanner-source adapters
can run. The completed float stage is reused byte-for-byte.

## Durable execution order

1. Validate the frozen v0.7 authorization, registration, exact v0.6 failure
   audit, artifact metadata, and pinned environment without provider secrets.
2. Download, rehash, and replay the exact v0.6 checkpoint, including all 946
   candidates and float records, before authorization consumption.
3. Create the v0.7 consumption marker and atomically create its protected Git
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
