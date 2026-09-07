# Sealed historical execution empty-input diagnostic v0.1

The frozen parent is checkpoint `36375ab2d627e98b864aba3c91157efe55e2203c`, tree
`764c0a1880f0d4ec32120b27af04bb2fd146368a`. Acquisition v0.2 run
[34076412463](https://github.com/RoomyRems/momentumbot/actions/runs/34076412463)
permanently failed on request index 24, `2025-06-13-JVA-mbp-1`. Its 24 completed
tapes and all retained failure bytes remain immutable. This diagnostic has a
separate registration, sole execution child and durable consumption tag.

The hypothesis is that a positive metadata estimate for the exact 650,000,001 ns
JVA window can accompany a metadata-only native DBN response. This is tested by
counting native records before DataFrame mapping and comparing the unchanged
v0.2 normalizer with the mapped rows. No retrospective inputs are involved.

Databento documents that record-count, billable-size and cost estimates can
over-report for time ranges that are not discrete multiples of ten minutes.
A positive estimate therefore does not establish that an exact short window
contains records. MBP-1 is an event/update schema, so the registration does not
assume every such window must contain an event. These documented semantics are
a possible explanation; they do not independently prove what the original
99-byte response contained.

- [Historical metadata billable-size reference](https://databento.com/docs/api-reference-historical/metadata/metadata-get-billable-size)
- [Historical API reference, including metadata limits](https://databento.com/docs/api-reference-historical/timeseries/timeseries-get-range)
- [MBP-1 schema](https://databento.com/docs/schemas-and-data-formats/mbp-1)

## Exact scope

| Item | Bound value |
|---|---|
| Dataset / schema / symbol | `XNAS.ITCH` / `mbp-1` / `JVA` |
| Date | `2025-06-13` |
| Inclusive start ns | `1749822929742083339` |
| Exclusive end ns | `1749822930392083340` |
| Request SHA-256 | `5e0ef1993dac42f58332997b14179cc1097ec37fc51f1cdcb703f9617a505d6b` |
| Prior raw DBN SHA-256 | `ae2ff3b0dd1be78d948ac39bda9de49eafef668e1678f92128aff6f1b227519f` |
| Fresh billable-size ceiling | 14,640 bytes |
| Fresh cost ceiling | USD 0.000016361475 |
| Download wire ceiling | 80,176 bytes |
| HTTP ceiling | Two exact metadata calls, then one exact time-series call |

No get-record-count, alternate symbol, venue, expanded window, previous quote,
retry, redirect or resumed acquisition is registered. The old acquisitions,
GITS diagnostic, main dispatcher, source ledger and seven protected refs are
checked unchanged. The code parent must have successful first-attempt push CI
and dedicated normal/optimized validation before the sole execution child.
CPython 3.12.14 and the existing 29 hash-locked package pins are required before
consumption or provider access.

## Evidence and interpretation

The diagnostic retains the exact request, both metadata results, the three-call
ledger, native DBN counts and typed metadata, a typed native MBP-1 projection,
a typed mapped projection, the unchanged normalization outcome, receipts,
provenance, environment, report and full file inventory. Every projection is
bounded by 50,000 rows and 64 MB decompressed / 16 MB compressed. Native DBN
decompression is bounded and must exhaust one complete frame without trailing
payloads or incomplete records. The ephemeral raw download is hashed and deleted
in `finally`; its hash is compared with the prior 99-byte download.

A metadata-only response may complete the diagnostic with
`metadata_only_exact_dbn_empty_before_mapping`. Both `runtime_input_eligible`
and `acquisition_gate_passed` remain false. Nonempty diagnostic records also
remain ineligible. A mismatch, truncated stream, missing mapping evidence,
increased quote or failed transport is retained as a failed diagnostic.
Unknown provider text is hashed or reduced to fixed codes.

`verify_result` recomputes the complete retained file set, all JSON seals, both
full decompressed projections, native/mapped equivalence, exact request metadata,
consumption, the pinned environment and the three-call ledger. Independent
verification also checks GitHub ZIP digests and every job/step at the exact run.
The diagnostic must not imply the original raw download was empty unless the
measured DBN bytes match its frozen hash.

The next dependency remains a registered resolution of the missing execution
input. No account/fill simulation, strategy change, backtesting, policy promotion
or retrospective comparison follows merely from diagnostic success.
