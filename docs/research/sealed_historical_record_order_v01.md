# Historical record-order adapter v0.1

This provider-free development child follows independently verified diagnostic
checkpoint `726f00344ba061a1c6e71be64db7cd3b239eead0`, tree
`ddd901f72c45d5b48a0b1460469ee1e0ceb8c4c9`. Its single hypothesis is that a
separate original record position can preserve distinct MBP-1 updates sharing
native receive time and sequence, while keeping the frozen capture and
execution mechanics intact.

## Evidence and scope

Diagnostic run [34069896968](https://github.com/RoomyRems/momentumbot/actions/runs/34069896968),
attempt 1, retained a byte-identical response to the original failed GITS
request. Result artifact [10000122082](https://github.com/RoomyRems/momentumbot/actions/runs/34069896968/artifacts/10000122082)
has ZIP SHA-256
`5626dd395c5bc4af329721d768bc1c1f2f8ad5fb02df7833aa5dc581c11fc3d7`.
All 1,136 rows passed field and metadata normalization. The strict uniqueness
assumption rejected 175 distinct Trade/Cancel pairs sharing native keys.

The committed regression fixture retains the exact diagnostic projection gzip
as base64, including all 14 typed fields and original positions. Its decoded
file hash is
`1ba1571113bee4577785dbd7c4b880cac6043c67eef03f0c9f26eae67f3802e4`;
its complete projection content hash is
`9f4fd81be871d19dc12ed28df03d0586d31a129a6c598e2ba50d1c4aad9ffa1c`.
The original seven-field normalization remains
`d0d7742a17bf95201e157917f62e5f1a50372e3186ecda087b82891a4e9050c5`.
This fixture is diagnostic evidence only. No capture window, order attempt,
historical fill, or account result is computed from it.

## Versioned mechanics

`sealed_historical_record_order_v01.py` imports the original field/metadata
normalizer and frozen quote/status value validators. Every quote adds:

| Field | Meaning |
|---|---|
| `source_request_sha256` | Canonical commitment to the complete exact request |
| `source_record_index` | Original zero-based position in that request's decoded stream |

Complete quote tapes require contiguous indices from zero and nondecreasing
native `(ts_recv_ns, sequence)` keys. Filtered windows retain increasing original
indices, including gaps. Symbols, request bounds and provenance must match.
There is no sorting, deduplication, synthetic timestamp, or sequence rewrite.
Identical rows also remain separate source records. The ordinal does not imply
ordering relative to the independently captured status stream.

The versioned causal window preserves the frozen 100-millisecond lookback and
550-millisecond tail. Unknown initial/status coverage remains unavailable;
equal receive-time quote/status events remain ambiguous. Crossed, locked,
one-sided and undefined books retain the original exclusions. Status action
values remain 0 through 14, with the original Y/N/~ vocabulary. The capture
validator rebuilds the complete result from its bound tapes, so rehashing an
altered window cannot pass. Historical plan identity must still be verified by
the subsequent complete input composer; this mechanical window function does
not reinterpret prospective date restrictions or artifact IDs.

The original source files are hash-pinned and unchanged. Two explicit static
blocks exist in the new module because the frozen functions internally call
their strict ordering validators. Registration checks their syntax trees:

- the capture loop differs only by adding the two direct provenance fields;
- the execution body differs only by calling the versioned ordering validator.

Latency, quote age, cancellation timing, displayed-size participation, limits,
fees and management assumptions are unchanged. Synthetic tests establish that
arrival uses the last available tied state, while a post-arrival order uses
the first eligible displayed state once, without refill credit. Both frozen
scenarios and order sides match the original implementation for strict streams.
No actual historical execution stage runs in this development checkpoint.

## Verification and next gate

The provider-free command verifies the frozen parent chain, registered
contract, structural equivalence, full diagnostic projection and lossless
1,136-row adapter output:

```bash
PYTHONPATH=src:scripts python scripts/validate_sealed_historical_record_order_v01.py
```

The validation workflow pins CPython 3.12.14 and the existing hash-locked
execution-quote requirements. It has only a validation job, read-only repository
permission, no provider step and no execution/consumption record. Focused tests
run normally and under optimized Python, including actual pinned-SDK decoding
of synthetic Trade/Cancel messages. The full repository suite remains required.
The registration audit records exact test results and measured output hashes.

The next dependency is a separately versioned bounded acquisition child using
this adapter and the unchanged 90-request plan. It needs its own code validation,
exact execution record and durable consumption, fresh size/cost checks under
the existing ceilings, complete per-request receipts and independent artifact
verification. It must preserve failed acquisition `34067754001` and diagnostic
`34069896968`; neither consumed operation may be repaired or rerun. Diagnostic
rows cannot substitute for any of the 90 complete inputs.

All 30 dates, 109 opportunities, original source/strategy artifacts, source
ledger and main dispatcher remain frozen. Input capture and management gates
must pass before historical account/fill simulation. This registration grants
no new provider, order, backtest, policy-promotion or retrospective authority.
