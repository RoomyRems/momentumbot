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

## Independently verified result — 2026-09-07

The separate diagnostic completed once as push attempt 1 in
[run 34079022132](https://github.com/RoomyRems/momentumbot/actions/runs/34079022132),
execution `8854bb2e63dc3961d98c5d8827f857ef85ccb341`, tree
`e7951840e1268d5e048bde57cb25980d72e2c468`. The validated code parent is
`e38b4b8a5b17c6dda00a6b5e830a55e9815f50b6`, tree
`fe61b33ab645dbb3956c1b67648d7dbe2565edfd`.

The downloaded DBN is exactly the same 99 bytes as the original failed JVA
request: SHA-256 `ae2ff3b0dd1be78d948ac39bda9de49eafef668e1678f92128aff6f1b227519f`.
Its 206 decompressed bytes contain metadata only. The exact JVA symbol resolves
to instrument 9236 for the requested date, with empty partial/not-found lists.
There are zero native records, zero mapped records and zero normalized rows.
The unchanged v0.2 normalizer correctly rejects it as `empty_exact_request`.
No records were lost in symbol mapping or normalization. This conclusion applies
to the exact registered venue/window; it does not establish absence of resting
quotes outside that window or quotes on other venues.

| Evidence | Measured SHA-256 |
|---|---|
| [Consumption artifact 10003076964](https://github.com/RoomyRems/momentumbot/actions/runs/34079022132/artifacts/10003076964) ZIP | `4e8866f8536291ca305b9e836f59e932e52b7c042a154a8d746249906d602225` |
| [Diagnostic artifact 10003079091](https://github.com/RoomyRems/momentumbot/actions/runs/34079022132/artifacts/10003079091) ZIP | `246ab302c949f22af2907fecba9e024b0c30b6901c91446f4401fab5627e91ea` |
| Report file | `e106fdd8a2293294636d73eed94774ea37178ce259141ae0fe6983df1f593bf9` |
| Report content | `b7324d1e6f123a2adca163f8d8e609db6a173f200c36a180396b8dad734c7da7` |
| Diagnostic inventory content | `a12933959d973c0bbe73b65e20c344422cb54bee357e26736adcd60202fff5c5` |

Both ZIP digests and all 30 files (13 consumption / 17 diagnostic) passed an
independent stdlib verifier. The frozen source verifier separately agreed. Both
full decompressed projections, all JSON content/file hashes, exact request and
receipt bindings, environment, seven protected parent refs and the new durable
consumption were checked. The embedded parent ZIP and all 62 retained parent
files remain byte-identical.

The separate diagnostic ledger is exactly three HTTP attempts, zero blocked
attempts, no retries and no redirects. The original 30,522-request source ledger
and all 24 completed v0.2 tapes / 73,614 rows remain unchanged.

Validation passed 97 focused tests normally and optimized and 1,561 repository
tests locally. Code CI [34078724263](https://github.com/RoomyRems/momentumbot/actions/runs/34078724263)
and dedicated validation [34078724334](https://github.com/RoomyRems/momentumbot/actions/runs/34078724334)
passed at the exact code parent, with its diagnostic job skipped. Execution CI
[34079022165](https://github.com/RoomyRems/momentumbot/actions/runs/34079022165)
passed as well. Hosted base CI skips 35 optional SDK tests; 30 pass in the exact
97-test dedicated job, and five unchanged tests are covered by the frozen v0.2
parent validation. The hosted diagnostic checks CPython 3.12.14 and all 29 pins.

The permanent receipt is
`research/data-audits/sealed-historical-execution-input-empty-diagnostic-v0.1-independent-verification-34079022132.json`.
The diagnostic is consumed. Its raw DBN was deleted under the registered rule;
its bounded observations remain retained. The completed monitor remains paused.

The next dependency is a separately registered missing-input resolution for the
66 unavailable normalized tapes: this confirmed empty quote request and the 65
requests not reached after the original failure. Any next child must preserve
exact request windows and represent unavailable inputs explicitly. The
acquisition and quote gates remain closed; no account/fill simulation,
backtesting, policy change or retrospective activity occurred.
