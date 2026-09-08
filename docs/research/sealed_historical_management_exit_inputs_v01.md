# Complete historical management exit inputs v0.1

This isolated child of `c0ccf773fcc49091682f600c07d991fdd26ab6a8` combines
the verified 80-request exit capture with the original verified XAGE pair.
Its hypothesis is that these sources supply all 41 previously registered common
quote/status pairs while preserving every original source identity and every
opportunity's original bounds. It introduces no strategy or execution-policy change.

## Source composition

The four exact retained GitHub archives are bound to their original sizes,
SHA-256 hashes, artifact IDs and run IDs. The acquisition verifier reconstructs
the full exit capture and its quote provenance; the original availability/reuse
verifier reconstructs the full original entry capture chain and XAGE proof.
All 352 direct archive members are reopened. Shared result/consumption evidence
must match. No provider credentials, requests, re-quotes or purchases are used.

The bundle copies **82 original compressed tapes byte for byte**, under separate
entry/exit source namespaces. It contains **2,223,297 quote records and 151 status
records**, or **604,286,662 normalized bytes**. The full original XAGE request
is retained, including its longer original end. No tape is clipped, recompressed,
sorted, deduplicated, renormalized or assigned new quote ordinals. Every source
receipt, artifact, original request ordinal and request fingerprint remains bound.

Each final file is written exclusively in one write, flushed and fsynced.
Before freezing, the composer reopens all final tapes, verifies compressed
hashes and sizes, reaches gzip EOF/CRC, and verifies normalized hashes, byte
counts and row counts against the original receipts. Failed compositions retain
sanitized partial evidence and cannot pass the complete-file verification.

Five small committed documents pin the 87-file bundle: source verification,
source/group manifest, opportunity index, readiness report and freeze manifest.
The compressed source files are retained as a GitHub Actions artifact.

## Access and causality

`ExitInputBundle` requires an external freeze-manifest content hash, validates
the registration, compares all five metadata files to their committed bytes,
and rechecks all 82 tapes. It retains the exact original 109 opportunity records
and original management windows, including all 23 unavailable entries.

`execution_tape(opportunity_id, decision_ns, expected_window_content_sha256=...)`
checks the original opportunity's identity, entry availability, earliest possible
exit decision, latest covered decision and required 550 ms capture tail plus the
exclusive-end nanosecond. It rereads the exact source files before returning the
original four-key quote/status payload and its independently reproducible hash.

The payload is complete execution evidence, **not a strategy observation stream**.
Its hash remains identical across sell attempts, as required by the frozen fill
feedback engine. Original quote request hashes and record ordinals continue to
identify consumed liquidity. A later registered runner must expose confirmed
feedback only at the frozen causal clock; a full source file is not permission
to let a strategy inspect future quotes.

`capture_window(...)` applies the unchanged record-order adapter to the same
bound source. It returns only the conditional execution envelope, including the
bounded post-decision fill tail. Unknown status, missing fresh quotes, halts and
unusable quotes retain the frozen adapter's behavior. Complete source bytes do
not mean every proposed exit is executable. A longer common/XAGE source cannot
extend the original opportunity or rescue an unavailable entry.

## Reproduction

The CLI installs external network/process IO denial before importing research code.
The hosted workflow has read-only GitHub permissions, no provider secrets, a
fixed four-artifact download list and the existing hash-locked Python 3.12.14
verification environment.

```bash
python scripts/build_sealed_historical_management_exit_inputs_v01.py --validate-registration
python scripts/build_sealed_historical_management_exit_inputs_v01.py --build --check-committed \
  --exit-result-zip EXIT_RESULT.zip --exit-consumption-zip EXIT_CONSUMPTION.zip \
  --entry-result-zip ORIGINAL_ENTRY_RESULT.zip --entry-consumption-zip ORIGINAL_ENTRY_CONSUMPTION.zip \
  --output-root artifacts/sealed-historical-management-exit-inputs-v0.1
python scripts/verify_sealed_historical_management_exit_inputs_v01.py \
  --exit-result-zip EXIT_RESULT.zip --exit-consumption-zip EXIT_CONSUMPTION.zip \
  --entry-result-zip ORIGINAL_ENTRY_RESULT.zip --entry-consumption-zip ORIGINAL_ENTRY_CONSUMPTION.zip \
  --output-root artifacts/sealed-historical-management-exit-inputs-v0.1
```

Only an absent output may be built. The independent stdlib checker imports no
production verifier. It compares all four archive inventories, every selected
compressed source byte, every normalized row and ordinal, all 41 full-payload
hashes, all original group/entry/window identities and all final metadata files.

## Verification result

The first local composition succeeded. All **1,951 tests passed with zero skips**
in 157.584 seconds. The 161-test focused group passed normally and optimized
with zero skips. The primary and independent verifiers agree on all 87 output
files and all 41 execution payload hashes. The frozen bundle content commitment
is `a7f7a6e864e012fb2623872a7325c57fcc9c0ccbf8cd880597839c8b44965b67`.

Real-input reader checks covered all 109 original opportunities: 86 available
boundary pairs accepted; 86 late tails, 86 incorrect window pins and all 23
unavailable entries rejected. The complete GITS and XAGE execution payloads
remained identical across the first and last covered decisions. No fill or
account simulation was run. The [permanent audit](../../research/data-audits/sealed-historical-management-exit-inputs-v0.1-independent-verification.json)
retains both verifiers, complete output inventories, reader evidence and test
log commitments.

Code `1fc6ae1999edf89767a44912f0efadbbaba68fc1` passed all eight hosted
workflows on attempt 1. [Dedicated run 34176013955](https://github.com/RoomyRems/momentumbot/actions/runs/34176013955)
passed 161 normal/optimized tests with zero skips, fully reconstructed the
bundle and passed the independent source checker. CI passed 1,951 tests with
73 optional-SDK skips. Bundle artifact `10037358910` is 30,747,584 bytes,
SHA-256 `94877d03a9e91372f9a36d68275b6c44421139bc5c4eab0f26403c26f26aed80`.
All 87 downloaded files and the separately retained independent-verification
report match their local counterparts byte for byte. The
[hosted audit](../../research/data-audits/sealed-historical-management-exit-inputs-v0.1-hosted-verification-34176013955.json)
retains exact run, job, artifact and verification evidence.

## Remaining dependencies

This completes the source composition dependency. It does not activate the
historical runner. The immutable runner's original registration remains intact;
this child's readiness report records the two source-verification dependencies
as complete while keeping all account/execution dependencies unresolved.

The next integration needs the historically correct 2025 fee schedule,
executable sell reconciliation, authenticated account-state production,
causal next-session valuation and continuous account/order/scarcity handling.
A separately registered historical execution child must bind those completed
dependencies before the 30-session account replay can run and freeze results.
Only after that freeze may retrospective Ross evidence be opened for comparison.
