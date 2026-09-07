# Historical execution/status acquisition v0.2

This separate acquisition binds record-order adapter commit
`45f24e880ef6cc1f3eadd490ca5aa59e5ee94c71`, tree
`8f0727234c6d9634b6a789da04a4b19445ae7f41`. It tests whether the unchanged 90
candidate-bound requests can produce complete minimal quote/status tapes using
that independently verified adapter. The sole normalization delta already
registered by the adapter is the original per-request record ordinal; native
timestamps, sequence numbers, prices, sizes and status semantics remain frozen.

## Immutable prerequisites

- Source Snapshot run `34039993297`, its 767 files, 190 directories, 30 dates
  and original 30,522-request ledger.
- The frozen scanner/Micro outputs and all 109 decisions, including profile
  unions and five explicit no-decision dates.
- Exact request list
  `4515172de55e48d42f1312b5b298dd2c126fccea700b39417cf600221d76e8ce`:
  45 symbol/date pairs, 45 `mbp-1` and 45 `status` requests.
- Quote run `34066187628`, artifact `9999061044`, ZIP
  `2a353b635407bffdb8076d88acdc520ad48f0bc19e28ff5d8c2e4ede8a88aa43`.
- Failed acquisition `34067754001` and diagnostic `34069896968`, both attempt
  1, their complete retained evidence and original consumed refs.
- Adapter contract
  `d66a2ff55dbba8497567ac3ffa0694272a30135b2e11710d683626e95291c0e9`,
  verified through CI `34073929422` and dedicated validation `34073929465`.
- The frozen HTTP transports, source/strategy/account/execution policies,
  installed main dispatcher and original consumption refs.

The contract pins prerequisite file hashes and protected ref values. The first
request's seven native fields must reproduce the diagnostic content commitment
`d0d7742a17bf95201e157917f62e5f1a50372e3186ecda087b82891a4e9050c5`.
The provider must supply those rows during this new acquisition. The diagnostic
fixture is a regression input and cannot replace a provider response or become
a runtime tape.

## Bounded provider operation

The exact original transport makes 180 fresh size/cost calls first. Every quote
must be complete and nonzero; aggregate size and estimated cost must be at or
below 154,456,640 billable bytes and USD `0.172787457709`. Failed, missing or
increased quotes block all data downloads. The actual bill is not inferred.

Only a successful complete preflight enables one download per exact request in
frozen order. There are no retries, redirects, alternate symbols, dates,
schemas or endpoints. The first failed request stops all later downloads.
The maximum is 270 HTTP attempts with separate metadata/time-series ledgers.
Each request's wire ceiling remains its original billable-size quote plus
65,536 metadata/compression bytes. Compressed normalized tape bytes are capped
at 1,000,000,000 and decompressed normalized bytes at 1,500,000,000.

The runner uses the unchanged record-order adapter and validates every quote
and status row. Quote provenance binds the exact request and contiguous
original ordinal. Native receive-time/sequence keys may tie but cannot reverse;
ties are never sorted or deduplicated. Frozen status vocabulary and ambiguity
rules remain unchanged. Missing records fail the acquisition gate.

## Consumption, evidence and verification

The code-only push cannot acquire inputs. After exact-parent CI and dedicated
normal/optimized validation pass, one sole added v0.2 execution JSON can start
attempt 1 from the research branch. It binds the exact code commit/tree,
workflow hash, contract and successful validation runs. The workflow checks
immutable adapter, parent-run and ref evidence, verifies every parent quote
ZIP member, then atomically creates its own
`refs/tags/sealed-historical-execution-input-acquisition-v0.2-consumed`.
The complete consumption evidence must be uploaded before the only provider
step. CPython 3.12.14 and all 29 hash-locked dependencies are checked at runtime.

Every completed request retains one deterministic gzip JSONL tape and one
sealed completion receipt. Receipts bind request identity, full decompressed
content and file hashes, native ordering summary and ephemeral DBN hash.
Raw DBN bytes are removed before the next request. A failed write preserves
its bounded tape prefix and any receipt prefix with hashes and explicit
`runtime_input_eligible=false`; preceding completed tapes remain unchanged.
Only fixed sanitized error codes and failure phases are recorded.

A complete result contains 194 files: 90 tapes, 90 receipts and 14 metadata
files. The runner independently reconstructs its report from every retained
file, decompressed row, receipt and ledger before returning success. A separate
post-run verification must still download both GitHub ZIPs, compare measured
GitHub digests and file counts, inspect every job/step and sanitized log, and
recompute all internal/file hashes and normalized records. Green job status
alone is insufficient.

Provider-free tests cover the full CLI and pinned SDK with synthetic HTTP
replies, all 1,136 diagnostic records and 175 Trade/Cancel ties, exact 90-request
ordering, ceilings, partial writes, safe failure retention and rehashed-evidence
tampering. Only hosted environment observations and the previously verified
external quote ZIP are mocked in this test harness; the actual operational
gates remain mandatory. No test executes historical account/fill simulation.

The preparation audit is
`research/data-audits/sealed-historical-execution-input-acquisition-v0.2-registration-2026-09-07.json`.
Local validation passed 94 focused tests normally and optimized, and all 1,539
repository tests. The local interpreter is CPython 3.12.13; operational
execution remains blocked there by the explicit CPython 3.12.14 environment
gate. Hosted checks must verify the exact interpreter and all dependency pins
before a sole execution child can be published.

After independent acquisition verification, the next dependency is the
provider-free historical capture composer for the exact 109 decisions. It must
retain explicit unavailable book/status outcomes and satisfy the registered
management-input gates before account/fill simulation. No source or Micro
rerun, policy change, retrospective input, brokerage access, paper/live order
or backtest is part of this acquisition. Neither consumed parent is repaired
or rerun.

## Permanent first-attempt missing-input failure

Code commit `7d474682a6a42f519c41b373756be1ac6a16eeb2`, tree
`17a599583b5a0eaf8c367865d5f08090bf697ddc`, passed CI `34076112217` and dedicated
validation `34076112234`. Dedicated CPython 3.12.14 validation passed 94 tests
normally and optimized. Local full validation passed all 1,539 tests; general
CI passed with 20 optional SDK skips. Sixteen were covered by the new dedicated
job; four unchanged diagnostic tests were covered by pinned adapter validation
`34073929465`. The code-only acquisition job was skipped.

Sole execution child `e2c250367895d209ec4706288a22655636298685`, tree
`952c82ffb4ffb8be141006d5a0244ad54adfa808`, started run `34076412463` as push
attempt 1. The exact checkout, sole-child check, 29 dependency pins, normal and
optimized validation, every parent prerequisite and durable consumption upload
passed before provider access. The fresh 180-call quote matched both original
ceilings exactly. Execution-commit CI `34076412479` also passed.

The first 24 requests completed: 12 quote tapes and 12 status tapes across
12 symbol/date pairs and eight dates. Every one of their 73,614 normalized rows
passed independent verification: 73,573 quote rows and 41 status rows, including
8,239 preserved adjacent native-key ties. The first GITS request exactly matches
all 1,136 diagnostic native rows. This verifies the record-order repair on the
retained prefix; it does not establish complete input coverage.

Request 25, `2025-06-13-JVA-mbp-1`, returned HTTP 200 with 99 wire bytes, within
the unchanged 80,176-byte wire ceiling. Its exact interval is
`1749822929742083339` through `1749822930392083340` nanoseconds, end exclusive:
09:55:29.742083339 through 09:55:30.392083340 New York. Despite its complete
14,640-byte size quote, normalization produced no quote rows and rejected it
with `empty_exact_request`. Its ephemeral DBN SHA-256 is
`ae2ff3b0dd1be78d948ac39bda9de49eafef668e1678f92128aff6f1b227519f`.
No failed-request tape or receipt prefix exists; raw DBN bytes were removed
according to the registered retention rule. The provider-side reason for the
empty interval is not established by the retained evidence.

The runner stopped before the remaining 65 requests. There were 205 total HTTP
attempts: 180 metadata and 25 time series, zero blocked attempts, redirects or
retries. All previous tapes/receipts remain retained. Acquisition and downstream
input gates are false; all 66 missing normalized tapes are unavailable inputs.
No symbols, dates, windows, policies or source records were substituted.

Independent downloads verified all 18 consumption and 62 result files, every
internal/file hash, all full decompressed tapes and both ledgers. Result artifact
`10002303908` ZIP SHA-256 is
`2065c140c2c14bc7da14a22483934eb1631169a36a599e522e0b59c27d7ff6e9`;
consumption artifact `10002219905` ZIP SHA-256 is
`f848f9f79afc62c82249ba27afde23e0d6948875cee6df2820425b1e65b9efa9`.
Capture report file/content hashes are
`ddd6160e67f09420ff914c5db50b418fd60ec0fae615dfc32168eed87a69dd57` /
`62e20bfc72efe69c56811b49d320195da1e562f7195d2b04119e47c9284e9d6b`.

The original source ledger remains 30,522 requests; main and all consumed refs
remain exact. No account/fill simulation, retrospective access or backtest
occurred. The monitor is paused. This consumed v0.2 cannot be modified or rerun.
The next dependency is a separately registered, narrowly scoped diagnosis of
the exact missing JVA input. Request bounds and validation cannot be weakened
or replaced to infer a successful capture.

Permanent records:

- `research/data-audits/sealed-historical-execution-input-acquisition-v0.2-independent-verification-34076412463.json`
- `research/data-audits/sealed-historical-execution-input-acquisition-v0.2-report-34076412463.json`
- `research/data-audits/sealed-historical-execution-input-acquisition-v0.2-inventory-34076412463.json`
