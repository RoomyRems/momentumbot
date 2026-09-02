# Sealed historical source recovery v0.10

## Status and purpose

Run `33577895166` dispatched v0.9 exactly once from `main`, passed every
provider-free validation gate, permanently consumed its authorization, and
failed during `Acquire canonical split-rank scanner source inputs`. The writer
had completed the first date's membership, previous-close, split-rank-bar, and
raw-candidate-bar records before rejecting BLRX. No automatic rerun is allowed.

The failure is a deterministic adapter/serialization mismatch. The exact
same-time RVOL calculator intentionally returns the full eligible minute grid.
Alpaca raw minute bars contain only observed minutes. The scanner already reads
RVOL at raw-bar timestamps, but the frozen canonical writer required the two
indexes to be identical before serialization. For BLRX on 2025-05-30, the raw
index has 177 minutes from 11:02 through 13:58 UTC while the exact-RVOL grid has
359 minutes from 08:00 through 13:58 UTC. This is not a timezone, credential,
provider, or budget failure.

v0.10 is an additive, one-shot recovery child. It projects each exact-RVOL
series onto the corresponding raw candidate-bar index immediately before the
unchanged writer. It does not fill, interpolate, synthesize, round, or otherwise
change a value. A raw timestamp missing from RVOL remains fatal. Scanner rules,
profiles, thresholds, dates, news rules, float calculations, Micro-v0.1,
account rules, and order authority do not change.

## Provider-free regression

The v0.10 regression reconstructs the retained BLRX index geometry and first
proves that the frozen writer rejects 177 raw timestamps against the 359-minute
RVOL grid. It then applies the adapter and requires:

- the projected index to equal the raw-bar index exactly;
- every projected value to equal the value already present at that timestamp;
- a complete canonical write/read round trip with 177 raw-bar and 177 RVOL
  records; and
- symbol disagreement, duplicate timestamps, or a missing raw timestamp to
  fail closed.

The adapter is scoped only around the canonical writer call and restores the
frozen writer afterward. The frozen scanner, exact-RVOL calculator, and v0.2
source serializer are not edited.

## Exact parent and recovery boundary

The parent is v0.9 run `33577895166`, attempt 1, research commit
`92d8b4deceae5c2bb6edfb10016a0e05c33c8bfa`, tree
`d214d0990665a92ea24760a972232998378fae38`, and dispatcher
`b92a236dc92e8311c70c1b76ab657cea809fbe90`.

The retained parent checkpoint is GitHub artifact `9827444933`, named
`sealed-historical-source-acquisition-v09-failure-checkpoint-33577895166-1`.
Its downloaded ZIP SHA-256 is
`0db44af6ffe695642444e384378faf3dfb3b6be8e059c0dca7bc0ee77d589244`.
The full retained source contains 646 files, 130 directories, 544,738,038
bytes, and tree commitment
`60113df5eb307e3c5f31ab075017c9cca4e1da70c2177de40c26df7bed7a5f9f`.

The partial scanner directory contains one incomplete May 30 tape and no
manifest. v0.10 validates that file and its BLRX evidence byte-for-byte, copies
the parent source, removes only that directory, and then requires the recovered
source to contain exactly 645 files, 128 directories, 543,955,728 bytes, and
tree commitment
`69ead0aa5a8eafc5b207627b2b0080ba3005abca33b84612072d1363c1f3dbc8`.
All 30 market, float, and news dates, all 946 candidates, and all 946 float
records are revalidated provider-free.

The composite request ledger begins at:

- Massive: 363
- Alpaca: 16,153
- SEC: 1,328
- Total: 17,844 of the unchanged 40,000 ceiling

No Massive, identity, market-discovery, SEC, float, or news acquisition entry
point is available to v0.10. The only network-capable child entry point is the
RVOL-aligned scanner source builder, and the transport guard admits only
`data.alpaca.markets`.

## Durable execution order

1. Validate the frozen v0.10 authorization, registration, exact v0.9 failure
   audit, real artifact metadata fixture, and BLRX round-trip regression without
   provider secrets.
2. Download, hash, and deeply replay the exact v0.9 failure checkpoint and
   compare the parent and child third-party environments before consumption.
3. Create the v0.10 consumption marker and atomically create its protected Git
   tag.
4. In a fresh job, repeat the metadata and checkpoint validation, remove only
   the incomplete scanner directory, materialize the 645-file source, and seed
   the 17,844-request ledger.
5. Run only the RVOL-aligned canonical scanner-source builder.
6. Upload the 706-file provider checkpoint.
7. In a separate credential-free job, rehash the checkpoint, add only the 61
   scanner snapshot files, deeply replay all 30 dates, and seal the 767-file
   final source bundle.

No transcript record, Ross action/fill/skip/label, later outcome, Databento
route, brokerage account, or order endpoint is available. Retrospective
comparison remains blocked until the label-blind scanner and Micro artifacts
are frozen.
