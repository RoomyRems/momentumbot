# Remaining historical execution inputs v0.3

Frozen parent: `b0bd86a49cd04225ee88740f9cc10ece83e33ec7`, tree
`d3efc3ef0719a3957759d1e3b13cb4ac8d97692e`. The independently verified JVA
diagnostic proves that original request index 24 returned a complete metadata-only
DBN, with no events before or after symbol mapping. It is unavailable input.
The completed 24 v0.2 tapes and receipts remain byte-identical inside the exact
parent artifact; JVA is retained through the exact diagnostic artifact.

The single hypothesis is that the remaining, never-attempted request suffix can
be acquired and classified without substituting data or reacquiring the prefix.
The exact 65 requests are original indices 25–89, in frozen order. Their list
SHA-256 is `9f96fe77746cd08fbbb6174bb2bea8baa3529a0cf3d71ab036abbf01aa75acae`.
All original 109 decisions, 45 symbol/date pairs and 30 sessions remain bound.
No retrospective inputs are read.

## Separate acquisition boundary

`research/strategy/sealed-historical-execution-input-acquisition-v0.3.json`
registers at most 130 fresh metadata calls and 65 time-series downloads. Every
fresh size and cost must be positive and no larger than its original exact
quote. Total ceilings are 131,758,640 billable bytes and USD 0.147390693429.
Actual billing is unknown. The new ledger is separate from the original source,
prior acquisitions and diagnostics. No retries, redirects, window changes,
symbol substitutions or additional methods are allowed.

The versioned transport constructors accept only the frozen suffix. They reuse
the immutable parent's bounded HTTP methods without monkeypatching its global
90-request validator. All downloads require a complete bounded suffix requote.

A sole added execution record binds the exact tested code commit/tree and two
successful code validation runs. A first-attempt research-branch push creates a
new consumption ref and uploads it durably before the only credential-bearing
provider step. Existing consumed refs, main and installed dispatchers remain
immutable. Code-only pushes validate and skip acquisition.

## Native completeness and unavailable evidence

Every fresh native stream must fully decode, match its exact request and valid
session mapping, and contain only the expected schema records. The fixed
normalizer and record-order adapter preserve every row and its native values.
Complete tapes must reconcile the native and normalized counts and pass the
unchanged quote/status validators. Full normalized JSONL hashes, gzip hashes,
receipts, raw DBN hashes and separate ledgers are retained. Raw DBN is deleted.

A complete stream with zero native and zero normalized records emits only an
explicit `unavailable` receipt. It creates no empty runtime tape and implies
neither a resting quote nor an active trading status. This terminal evidence
classification permits the next independent request to proceed. Truncation,
wrong metadata or mapping, unexpected records, reversed ordering, transport
errors, or write failures stop the suffix and retain bounded partial evidence.

`request_evidence_complete=true` means all 90 original requests have a retained
classification through the two parents and this child. It never means all
inputs are usable. `acquisition_gate_passed=false` and
`runtime_input_eligible=false` remain mandatory because JVA is unavailable.
No scanner/Micro rerun, account/fill/order simulation, backtest, policy change,
or retrospective activity is part of this stage.

## Verification and next dependency

The provider-free verifier downloads neither providers nor labels. It verifies
both exact parent ZIPs and every embedded file; independently recomputes every
new decompressed tape, receipt, inventory, report and request coverage; and
rebuilds counts and gate flags from the ledgers. Dedicated tests run normally
and under optimized Python using the real pinned SDK with synthetic HTTP.
The repository full suite must pass before publishing an execution child.

After exact-run artifact verification, retain all usable and unavailable
outcomes. Missing inputs require a separately registered resolution. They must
not silently become no-trade outcomes or permit account execution to begin.

Local preparation passed 142 focused tests normally and optimized, all 1,587
repository tests, and undefined-name validation. All 29 locked dependencies
match; the local interpreter is CPython 3.12.13. Exact hosted CPython 3.12.14
validation remains a required gate before the sole execution child.
