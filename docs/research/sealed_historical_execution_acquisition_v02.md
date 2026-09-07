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
