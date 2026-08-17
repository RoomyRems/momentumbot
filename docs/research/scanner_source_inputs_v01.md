# Scanner source-input sidecar v0.1

Status: **deterministic replay infrastructure; no strategy change**.

## Purpose

The causal scanner already committed its reacquired market inputs to a SHA-256 hash, but it discarded the underlying input stream. That made the frozen scanner rows tamper-evident without making them independently reproducible after a historical provider revised its data.

`causal-scanner-source-inputs-v0.1` persists that exact canonical stream as deterministic gzip JSON Lines. The uncompressed stream hash must equal the existing `reacquired_market_inputs` source-chain hash. The frozen scanner policy and fingerprint remain unchanged.

## Persisted inputs

For each date, the sidecar records:

- the sorted identity-resolved membership symbols;
- the split-adjusted previous close for every member;
- all-member completed one-minute closes used for cross-sectional rank;
- candidate close and volume bars used by scanner features; and
- exact same-time candidate RVOL.

Candidate symbols are bound separately in the sidecar manifest so a candidate with no usable bar remains reconstructable as an empty, fail-closed input rather than disappearing.

## Validation

The loader verifies the compressed-file hash, canonical uncompressed hash, record counts and ordering, acquisition basis, source hashes, scanner fingerprint and label-blind knowledge boundary. It reconstructs shared candidate/rank frames and must reproduce the original scanner rows byte-for-byte when combined with the frozen upstream membership, candidate, float and news artifacts.

The sidecar does not persist raw provider responses and cannot independently rebuild upstream membership, market qualification, float or news artifacts. It makes the scanner feature stage replayable after those upstream artifacts have been frozen.

Use `scripts/build_causal_scanner_snapshot.py --persist-source-inputs` to create the companion artifact. This has no order, position-size, risk or policy-promotion effect.

