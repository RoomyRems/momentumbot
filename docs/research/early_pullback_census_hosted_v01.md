# Early-pullback census hosted launcher v0.1 — unarmed

## Parent and one hypothesis

Parent `242e5e6516339658216269dbf85cb0590acedda0`, tree
`e3479b68367e467cdb0bbbd70827e5b68d4f93fb`, census adapter registration
`1203e49170a69c5c6eb725b77aca997a61872379c69bece4bead42a7ec6a73a7`.
The hypothesis is an authorization boundary: exact-parent approval and retained
single-use consumption must validate before any credential read or census HTTP
request. It is not an entry-policy, source-selection or profitability experiment.

All 30 dates, pagination/retention limits, original source/account mechanics,
losing baseline and the local historical baseline replay waiver are unchanged.
No transcript records were read. Retrospective recap actions, fills, later
outcomes and evaluation narratives remain prohibited in runtime and backtests.

## What is implemented, and what is not authorized

The additive module and CLI validate an exact sole-file execution child,
time-limited owner approval/entitlement scope, successful code-parent CI including
every job step, a permanent consumption ref, independently pinned retained
preflight files, live artifact metadata and a frozen runtime. Only then does the
capture function invoke its credential loader and unchanged census adapter.

The workflow is **push-only on the separate execution JSON path**. That file is
not shipped. Adding this workflow, source, registration or documentation cannot
trigger capture. Current authority remains zero requests and USD 0.00 incremental
spend. No new permanent consumption ref is created by this implementation turn.

Creating an execution record is a separate action after explicit owner approval.
It must be the only added file in a single-parent commit whose exact parent has
passed CI. Any changed code/workflow, changed parent/tree, merge, dirty tracked
checkout, wrong repository/branch/workflow, dispatch or rerun is rejected.

## Approval and entitlement gate

The execution schema requires two non-placeholder evidence hashes: an explicit
approval record and an existing-subscription entitlement record. Their scope is
fixed to the 30 dates, the Massive PIT ticker/type endpoints, at most 601 requests,
no retries, no incremental charges and no subscription changes. The approval
window must be timezone-aware, no longer than seven days, and valid at launch.
Expiration is a launch deadline, not a promise that all requests finish before it.

Entitlement is explicitly **owner-attested, not provider-verified**. Hashes do
not establish the truth of an attestation. An operator must obtain and review the
actual owner approval and subscription confirmation before creating the execution
file. Neither an invented test attestation nor the old one-row API samples counts
as this confirmation. There is no automatic billing/account lookup, upgrade,
paid-data consent or fallback from `MASSIVE_API_KEY` to another credential.

## Hosted ordering and retained evidence

1. The credential-free consume job validates the registration, sole-file child,
   offline tests, code-parent CI and all test/compile steps.
2. It atomically creates `refs/tags/early-pullback-census-hosted-v0.1-consumed`
   at the execution commit using **create**, never update or force. Existing
   consumption blocks reuse. A later failure does not restore authority.
3. It produces and uploads nine preflight files, with a file inventory whose
   byte hash is passed as a consume-job output. The capture job depends on the
   successful upload and downloads the exact artifact ID, not a name search.
4. Before credential access, the capture process rechecks the permanent ref,
   exact artifact ID/name/run/branch/commit/expiry/digest metadata, all preflight
   byte commitments, approval scope and frozen runtime.
5. The adapter writes its normal complete/partial raw capture. A separate
   linkage directory preserves preflight bytes, live ref/artifact observations
   and report/inventory hashes. Both outputs have `always()` upload steps.

The consume job alone has contents-write permission. Capture has read-only
repository permissions and the Massive key only in its final capture step.
Checkout credentials are not persisted. Actions are pinned to full commit SHAs.
The dependency lock is unchanged: CPython 3.12.14 on Ubuntu 24.04 x86-64,
NumPy 2.3.5, pandas 2.2.3 and PyYAML 6.0.3; installation uses exact wheel hashes.
The full development suite is separately verified in the existing pandas 3
environment, preserving the earlier native-crash diagnosis boundary.

The adapter's 1.5 GB retained-data ceiling is unchanged; preflight has a separate
4 MB ceiling and is repeated in the small linkage artifact. These are not one
combined whole-workflow ZIP-size promise. No duplicate data ZIP is created on
the runner. The raw capture and linkage are uploaded separately so the original
flat census archive verifier can process the capture artifact unchanged.

At the 601-request ceiling, minimum request-start spacing alone spans 125 minutes.
The capture step has a 330-minute timeout inside a 360-minute job to leave time
for evidence upload. Timeouts can produce partial evidence, never a completeness
claim. Abrupt host loss or cancellation may prevent final metadata/upload;
permanent consumption still blocks rerunning that authorization.

## Evidence limits and next gate

The preflight inventory pin comes from a different job output; a self-rehashed
download alone cannot replace it. Artifact digest metadata is retained, but this
step does not independently download and verify GitHub's original ZIP after a
real capture. Following an authorized capture, independently verify workflow
event/attempt/commit and every step, consumption/upload ordering, all artifact
ZIP digests, preflight equality, linkage, and all census raw bytes/exhaustion.

Successful synthetic launch or capture protocol completion does not authenticate
provider origin, resolve historical identity, activate historical replay or open
financial evaluation. Every such gate remains false. Current type taxonomy is
still not historical identity evidence; float, news, corporate actions, causal
scanner inputs and management/exit sources remain subsequent dependencies.

Next requires explicit approval for one bounded census run and confirmation that
the existing Massive subscription covers these historical endpoints/dates with
no incremental charge. The intended hybrid still needs crucial discretionary
integration; incomplete deterministic losses do not settle its edge, and complete
integration does not guarantee profitability.

## Verification

Registration `a211bc565d25118675545b248d077050fa10e16fcb7f4f509518b85b35c915c0`.
All 66 focused tests pass normally and optimized, including 30 new launcher tests.
The preliminary 30-test draft passed; a one-character trailing-space cleanup
and its prior source/registration are preserved in the audit directory. No test,
authorization or strategy behavior changed in that cleanup.

The audit directory `research/data-audits/early-pullback-census-hosted-v0.1/`
contains terminal test receipts and an explicitly synthetic launch fixture.
Full-suite and hosted-CI results are recorded separately when available.

The completed full retry ran all 2,691 tests in 371.150 seconds: 2,618 passed,
73 optional SDK skips, zero failures/errors. Its completion receipt includes
372.572 seconds with discovery/wrapper overhead. All 367 file bindings validate.
Local implementation verification:
`35a1111270dede72ac92fda27211a474b3a5e36b67a18fb81a50ba08677695e4`.
The saved synthetic launch verified nine preflight files, capture/linkage equality
and all 127 capture ZIP members using the unchanged adapter verifier. Its
authority, checkout facts, registration loaders, clock and transport are explicit
fixtures; no actual owner approval or subscription confirmation was obtained.

The first local full attempt discovered all 2,691 tests but stopped advancing
at the existing capture-plan parent registration test, before the new launcher
tests, while remaining CPU-active. The same test passed alone in 0.372 seconds.
That incomplete run was interrupted (exit 130) and its source/log retained.
A fresh identical-source/dependency full attempt uses a 900-second watchdog
and separate receipts. The first run's cause remains unisolated; it is not a pass.

## API references checked 2026-09-12

- [GitHub create-reference API](https://docs.github.com/en/rest/git/refs#create-a-reference)
  supplies the create-only consumption operation.
- [GitHub artifact API](https://docs.github.com/en/rest/actions/artifacts#get-an-artifact)
  supplies artifact identity, expiry, digest and workflow-run metadata. Those
  observations require independent provenance verification after real execution.
