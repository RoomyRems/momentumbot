# Sealed historical source acquisition v0.4

## Status and purpose

v0.4 is an authorization-only, one-shot child of the permanently consumed
v0.3 acquisition. Run 33449815223 failed after acquisition because its scanner
validator compared split-adjusted percentage gain with the raw displayed
price. The provider data was not the cause. The v0.3 authorization and partial
tree may not be rerun, mutated, or reused.

The frozen v0.4 authorization content SHA-256 is
`bbe51f4483a73f92b1f58c9f6c2085d8a47505346c2d340fbe59c0421f3f31b7`.

This child also repairs the provider-free blockers found after that failure.
It does not change either strategy profile, Micro-v0.1, the 30 historical
dates, providers, routes, credentials, total request ceiling, retained-byte
ceiling, or any trading authority.

## Frozen parents

The contract validates these repository files itself before it can load:

- v0.3 authorization content SHA-256:
  `77a37b207dc9ef15b5cbbef32911285c11926c95a53821635458b54b8ae3bffb`
- v0.3 permanent failure audit content SHA-256:
  `f63d995117fb95d673d9b0678baa258086f67f9f11bde331acbd74ee7604baaf`
- Run 33449815223 sanitized-failure ZIP SHA-256:
  `71afe1777bb71beb3abcc1dba4682206fd1b555e1a47d9d998e0300053523478`
- Run 33449815223 consumption-marker ZIP SHA-256:
  `ca1243c521f0b2f19c1507d48b7b11078a103faed7d4fea75f982f7d0d46b070`
- v0.2 success audit content SHA-256:
  `5be0fef73e639a6cbe9d40b0ec6b38ca22aefb007175790a7bc45248eeac583c`
- v0.2 completed source ZIP SHA-256:
  `4d2b7528c846b428acee3024dbc727646b60756f0b811afcdfce1398dbdc5254`

The v0.1, v0.2, and v0.3 authorizations all remain non-rerunnable.

## Exact repair boundary

The display and threshold bases remain separate and explicit:

- Displayed price and cumulative volume use raw candidate-minute bars.
- Percentage gain uses split target close divided by split previous close.
- Cross-sectional rank uses that same split/split ratio over membership.
- The validator compares gain with the split target close, never the raw
  displayed price.
- Raw and split target timestamp coverage must match exactly.

Acquisition uses the immutable `historical-profile-union-v0.1` superset:
$1.50-$20.00, at least 10% gain, at least 5 RVOL, at most 10 million shares,
and no acquisition-time rank gate. The union covers the unchanged general and
small-account profiles; it is not a new strategy profile. To prevent this
broader acquisition from being truncated, the per-date operational candidate
cap rises from 50 to 100. The 40,000 total HTTP-attempt ceiling is unchanged.

Float normalization uses the exact qualification-minute target pair. With
`A(x) = raw_close(x) / split_close(x)`, the measure-to-target share factor is
`A(measure) / A(target)`. Later target-session prices are forbidden, and
provider adjustments after the target cancel. Missing or misaligned target
pairs fail closed.

## Durable execution order

Every network-capable acquisition script runs through the v0.4 pre-network
wrapper. It permits direct HTTPS requests only to the three frozen hosts,
disables ambient proxies, rejects redirects before a follow-up request, and
blocks direct socket or subprocess escape paths. Every attempted request is
charged to the shared 40,000-attempt ledger before transport. Sanitized
blocked-attempt accounting is retained separately; any blocked attempt makes a
completed provider checkpoint ineligible for success. Provider substitution is
prohibited.

The dependency environment is a clean CPython 3.12 virtual environment on
Ubuntu 24.04 x86-64. Exact wheel hashes, wheels-only installation, no
dependency resolution, `pip check`, and a retained `pip freeze --all` are
required. The separate provider-free freeze job recreates that environment and
must byte-match both the requirements lock and captured freeze before it reads
the checkpoint.

The workflow must use this order:

1. Validate this authorization and all frozen parents without providers.
2. Install the hash-locked v0.4 wheels in a clean environment and capture
   `pip freeze`.
3. Build the provenance-bound marker, atomically create the repository
   consumption tag, and upload the marker immediately before provider access.
   The tag name includes the authorization content hash and targets the exact
   authorization commit. Deleting that consumption tag is prohibited.
4. Acquire only the frozen Massive, Alpaca SIP, and SEC routes through the
   pre-network wrapper.
5. Upload an upstream progress artifact after market, float, and news
   acquisition and before the long canonical source-input stage.
6. Close provider access, persist canonical scanner source inputs, and retain
   the exact request-budget and blocked-attempt ledgers.
7. Build and upload `sealed-historical-source-checkpoint-v0.1` before any
   scanner loader, deep validation, or scanner snapshot.
8. In a separate job with no provider credentials, download the checkpoint,
   recreate and compare the environment, and require zero blocked attempts.
9. Load and validate the checkpointed canonical inputs while freezing
   label-blind scanner outputs provider-free.
10. Deeply validate the completed bundle and exactly replay every scanner
    snapshot provider-free.

The checkpoint retains the pinned requirements and environment freeze. It
contains the complete label-blind acquired/canonical source tree but no scanner
snapshot. A downstream validation failure therefore cannot erase the source
evidence again.

The provider job keeps GitHub's 360-minute ceiling, but the canonical source
step has its own 150-minute limit so failure cleanup retains time to upload the
latest evidence. Scanner freezing and deep replay no longer consume that
provider job's wall-clock budget.

## Unchanged limits and prohibitions

- Manual workflow dispatch and attempt 1 only; no push, schedule, or automatic
  rerun may access providers.
- Maximum 40,000 HTTP attempts and 1,500,000,000 retained bytes.
- Incremental provider cost is $0; no paid acquisition or Databento call.
- Raw provider HTTP responses are not retained.
- No transcript records, Ross labels/actions/fills/skips, later outcomes, or
  final-volume knowledge may enter acquisition or runtime reconstruction.
- No Databento, brokerage account, order, paper-order, or live-order endpoint.
- No order submission, account runtime, policy promotion, provider
  substitution, strategy threshold change, profile change, or Micro change.

The next gate after a verified acquisition is still provider-free and
label-blind. Retrospective transcript comparison remains sealed until all
scanner and Micro outputs are frozen.
