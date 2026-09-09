# Frozen residual account runtime reproduction v0.1

## Completed local and hosted reproduction

Both registered attempts succeeded at unchanged implementation
`5b3e1864654abdd239f46f7e07b74fd070759f33`. Local session `93257` exited 0;
[hosted run 34347599749](https://github.com/RoomyRems/momentumbot/actions/runs/34347599749),
job `102452809165`, attempt 1, completed successfully. Hosted logs show the
original CLI starting at `2026-09-09T11:50:44Z`, its runtime result at
`13:06:30Z`, and the corrected verification plus exact comparison succeeding
at `13:06:52Z`. The prior active-execution sections below are historical.

The [hosted artifact](https://github.com/RoomyRems/momentumbot/actions/runs/34347599749/artifacts/10105333963)
contains exactly nine files. Its 1,127,255 downloaded bytes match GitHub's
SHA-256 `b73dd35a9a41b1ab49e0a965670d520cd85cb732ca5b37bd7619b5760f6a7c47`.
Independent verification checked ZIP inventory, duplicates, symlinks, CRC,
canonical JSON bytes and content seals. Every member is byte identical to local
output, and all six original component files match their frozen expectations.

| Commitment | Content SHA-256 |
| --- | --- |
| Original reproduced runtime | `21bd9efa65c5c5776242bb9a6a53d28c134aefe31ed7da00d389402e29f3efba` |
| Frozen corrected verifier report | `0d9c7cbcaac8970178bb15b16a47f13ff5df3b9b9d7f9cb28e039bffa40d5178` |
| New reproduction report | `70690fa827f4396d1eb3189f88de6f2ceb5a2117c6cc5656499ec60744eede24` |
| New reproduction freeze | `5702b00cb875313e1dc75661a2a040fb025e17b2e2bd7afe47099a4c889aa4cb` |
| Independent local/hosted/original comparison | `f16ec230a20830bff4a248e5e7807f48d27d1e070953521d61cff240ee18ffb2` |
| Completed outcome audit | `62fbe6fee26b0564479f4dd06301e488300f16efefaff149f46b7bcf51cb7c8d` |

The [success audit](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1-success.json)
and [comparison](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1-comparison.json)
preserve provenance and per-file commitments. The evidence directory also retains
the [local execution log](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1/local-execution.log),
[hosted execution log](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1/hosted-execution.log),
[artifact metadata](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1/hosted-artifact.json)
and the [independent download comparison script](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1/compare_downloaded_artifact.py).
The original failed checker and missing original local output remain preserved;
this separately registered successful attempt does not replace them.

Local validation passed 12 focused, 12 optimized and 2,327 full tests with zero
skips. Implementation CI and both interim checkpoint CIs passed 2,327 tests with
73 existing optional-SDK skips; the implementation's other six metadata workflows
and both interim walk-forward checks also passed. No frozen producer, corrected
verifier, registration, main ref or consumed ref changed during reproduction.

All incomplete states remain exact: 36 flat slots, 30 flat slots with unavailable
inputs, 12 exhausted original windows, 282 blocked later slots and zero complete
account paths across the 12 paths / 360 slots. Financial metrics, account-backtest
completion, retrospective labels and policy promotion remain closed. The next
gate is separately registered unresolved-continuation work; this completed
contract authorizes no further replay, orders, window extension or liquidation.

## Local success; hosted comparison pending

Local executor session `93257` completed with exit code 0, observed at
`2026-09-09T12:46:22Z`. Its nine output files passed independent inventory,
canonical serialization and content-seal checks. All six original component files
match the registered bytes exactly, including the original runtime
`21bd9efa65c5c5776242bb9a6a53d28c134aefe31ed7da00d389402e29f3efba` and corrected
verifier report `0d9c7cbcaac8970178bb15b16a47f13ff5df3b9b9d7f9cb28e039bffa40d5178`.

The [new reproduction report](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1/reproduction-verification.json)
is `70690fa827f4396d1eb3189f88de6f2ceb5a2117c6cc5656499ec60744eede24` and its
[freeze](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1/reproduction-freeze.json)
is `5702b00cb875313e1dc75661a2a040fb025e17b2e2bd7afe47099a4c889aa4cb`.
The [local success audit](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1-local-success.json)
records file hashes and the retained execution log commitment.

Hosted run `34347599749`, job `102452809165`, attempt 1, is still in the replay
step. Its exact artifact and all nine local/hosted file comparisons are pending.
Do not restart either attempt. The prior execution checkpoint below remains a
historical record; the local attempt is now complete. All incomplete account
states and evaluation boundaries remain unchanged.

## Active execution checkpoint — do not restart

Implementation `5b3e1864654abdd239f46f7e07b74fd070759f33`, tree
`8ad0688fb6947c18dbc5a2037b513d345fc3cd87`, was published before reproduction.
[Hosted run 34347599749](https://github.com/RoomyRems/momentumbot/actions/runs/34347599749),
job `102452809165`, attempt 1, passed setup, registration, synthetic tests and
all original-archive downloads and entered the replay step. The local registered
attempt is running in executor session `93257`, with output
`residual-reproduction-local-attempt-01` and log
`residual-reproduction-local-running-session-01.log` in the task workspace.

The local reproduction receipt is
`17b568eb0265af4d6caa7118af83847ad82819126761f8f27798bf2fa0c839bf`;
the original producer also emitted its exact registered receipt. At this
checkpoint neither a final local runtime nor a reproduction comparison exists.
Resume monitoring these exact attempts. Do not start another replay, reuse their
directories, cancel or rerun the hosted job as a recovery shortcut, or change any
registered producer/verifier file while they execute.

A preliminary local detached-process launcher produced an empty log and no
output directory or reproduction receipt. Its launch record and empty log were
kept. The single registered local replay then started through the supported
running-session mechanism, which emitted both receipts. No existing reproduction
output was overwritten; the preliminary launch's termination cause was not
established.

All seven non-reproduction workflows passed at attempt 1. [Implementation CI
34347599884](https://github.com/RoomyRems/momentumbot/actions/runs/34347599884),
job `102452811878`, passed 2,327 tests in 281.678 seconds with the existing
73 optional-SDK skips. This CI result does not certify the still-running replay.
The [execution audit](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1-execution.json)
and [durable attempt receipt](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1-attempt-receipt.json)
record the active attempt identities and preserved launcher evidence.

## Registered reproduction scope

This is a separately recorded reproduction of the original residual account
replay. Its single hypothesis is that the unchanged producer recreates the
already accepted original runtime byte for byte. It does not change strategy,
execution, cancellation, source windows, risk or continuation behavior.

## Frozen parents and scope

The preceding checkpoint is `94fb0d37749ce8fe9c96df5d8d091b0b9d30b69c`, tree
`89fba9cf670db8b69274eb6ed00c4b238ac38e87`.
The original producer remains implementation
`49e35b57f06b97a73590517b993de0e333d692dd`, with registration
`33ced4d6e2069f36a277b3b2025f38e07e2d7a3e9eeecd031345400ed6b54dae`.
The separately corrected verifier remains implementation
`25091dfd212f8afc595aca2a5d7d92b6d38dc78d`, with registration
`ed0f19906970ed71af17bf32cbd72ebe2284daa8ad59f80557257035a5f85f85`.
All of those files remain unchanged.

The reproduction contract is `sealed-historical-account-residual-exit-reproduction-v0.1`.
Its contract content SHA is
`ecbe9a777489fca6f87ef106abc9a3fe71b846f0d5b58fa7ac4897e25ccee468`;
registration freeze is
`25b2124138c419363176286e9bb8e209c210792365f00fc6ae4c6245a1742582`.
It commits 289 original producer, verifier and evidence files, plus the three
new harness/test/workflow files. Registration must be published before replay.
One new local attempt and one new hosted attempt are registered, with no
automatic retries. The hosted time budget is 120 minutes.

The original hosted replay finished under run `34295994393` and produced
artifact `10085178783`; its old checker failed. The corrected checker accepted
that runtime in separate run `34309642311`, with byte-identical local and hosted
verification reports. The original local replay process disappeared after
emitting only its attempt receipt; no termination cause was logged. Neither
original attempt is overwritten, restarted in place, or reclassified.

This new reproduction invokes the exact original CLI in its own new output
directory, then calls the exact frozen corrected verifier. The original producer
and verifier functions are not patched, copied or replaced. An offline audit
guard denies network and subprocess I/O inside the reproduction process.
GitHub archive transfer and environment installation occur outside that process.

## Exact input and output commitments

The five original replay archives are scanner, management, exit, entry-result
and entry-consumption. The original binding and verified waiting-parent archives
are used for independent verification. All seven archive byte lengths and SHA-256
digests must match the registration before the producer is invoked. There are
no new market-provider requests or substitute data sources.

The mandatory runtime remains content SHA
`21bd9efa65c5c5776242bb9a6a53d28c134aefe31ed7da00d389402e29f3efba`,
file SHA
`90f5a02dacc26eec03e8aacb5758150c0efc8b6a9b56d9c1d4eb7f5d7287c716`,
10,602,145 bytes. All 12 paths, 360 session slots, 744 opportunity references
and 162 unavailable references remain mandatory.

Success requires exact hashes, sizes and document seals for all six original
component files: the original replay receipt, runtime, runtime freeze, corrected
verifier receipt, corrected report and corrected report freeze. The corrected
report must remain content SHA
`0d9c7cbcaac8970178bb15b16a47f13ff5df3b9b9d7f9cb28e039bffa40d5178`.
Its frozen `account_runtime_reproduced: false` field describes the verifier's
own operation; reproduction is established by the distinct reproduction report
and registered original-CLI execution evidence, without editing that report.

The final reproduction artifact contains nine files: six exact component files,
a new reproduction receipt, a reproduction comparison report, and its freeze
manifest. Local and hosted copies must be directly compared after download.
Any mismatch or newly encountered failure remains recorded at this frozen
registration; the expected hashes are never adjusted to fit the result.

## Attempt preservation and validation

A new external nonsymlink directory is required. The reproduction receipt is
created exclusively and flushed to disk before source validation or replay.
An existing attempt directory cannot be reused. Failure preserves its stage,
error, receipt and any original component output; no next stage is run after a
failed producer or verifier. Successful output requires the exact registered
inventory, including unchanged receipt bytes.

Twelve synthetic tests cover frozen metadata, the offline CLI, exact original
CLI arguments, argument restoration on failure, receipt ordering, six-file
byte comparison, output inventory, changed sources, partial-output retention,
verifier failures, altered bytes, changed receipts, symlinks and retry refusal.
All 12 tests passed normally (0.149 seconds) and under optimization
(0.192 seconds), with zero skips. All 2,327 local tests passed with zero skips
in 281.006 seconds on Python 3.12.13 before publication. Exact log hashes and
registration checks are preserved in the
[registration audit](../../research/data-audits/sealed-historical-account-residual-exit-reproduction-v0.1-registration.json).

The cached local scanner candidate failed preflight byte comparison and was
left intact. Original artifact `9993250947` was downloaded separately; all
78,404,172 bytes match SHA
`af89836213a905a1e02dabd54cce1d2bab2f55214c2d7bc0dce44d4700243638`.
This preflight finding does not establish the cause of the earlier missing
local runtime.

## Remaining boundary

The expected runtime is still incomplete: 36 flat-complete slots, 30 flat-complete
slots with unavailable inputs retained, 12 windows exhausted with unresolved
state, and 282 blocked later slots. Reproduction must preserve those states.
It cannot open financial evaluation, account-backtest completion, retrospective
Ross labels, overnight execution or promotion.

After successful reproduction, the next gate is separately registered work on
unresolved continuation. No additional terminal order, window extension, inferred
liquidation or policy tuning is authorized by this reproduction. Ross attachments
remain unopened.
