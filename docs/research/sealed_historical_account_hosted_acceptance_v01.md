# Hosted historical acceptance and input completeness v0.1

The user authorized proceeding without another local replay. The successful
GitHub terminal-continuation runtime is now accepted as the mechanical replay
checkpoint. Full cross-environment reproducibility remains **unverified**, not
passed. No historical replay was launched by this amendment.

This is explicitly a **post-result validation-plan amendment**, made after the
hosted success was known. It is not a preregistered replication success and does
not rewrite the original contract, interrupted local attempt or frozen outputs.
It waives only the local replay requirement. Input completeness, financial
evaluation, label access and policy promotion are separate requirements.

## Accepted evidence

- Parent checkpoint: `ffa97914add1882b376460b2d41fcc9491873a35`.
- Original implementation: `0f057039e00480f3b0275d0bcd0bdabd23da7a96`.
- [Hosted run 34362104473](https://github.com/RoomyRems/momentumbot/actions/runs/34362104473),
  job `102501424811`, attempt 1: replay, independent check and upload succeeded.
- Original registration:
  `0f2570ba5b71783c3d27b47f2718217d7331bba8a2e8f7f09527c097fdf4a3fb`.
- Runtime:
  `a429f6723668fe9614ba6366de44b27d016ef939a5361d323bf58dceef250e91`.
- Original independent report:
  `d1eb98692d4795ff6985bf19683505ad7f8d9d2a14f019f0790ac723fff390d6`.
- Artifact `10120239248`: 5,733,269 bytes;
  `4683050552fe81e68b9bbaf7ecdd154bb90fdec50c5baeecf9439ff38c28b014`.

The exact original hosted ZIP and original source-binding ZIP are retained in
`research/data-audits/sealed-historical-account-hosted-acceptance-v0.1/` so that
future inspection does not depend on Actions artifact retention or another
replay. Both are immutable copies, not rebuilt archives.

The original local attempt remains incomplete at 20 of 360 saved session
records. All 20 records and the attempt receipt match the corresponding hosted
bytes exactly. Its archived logs and follower-start receipt remain preserved;
its termination cause and exit status are unknown. This prefix comparison is
not a full local reproduction.

## What the new check establishes

The offline inspector reads only committed metadata and the exact retained ZIPs.
It cannot launch a replay, request market data, submit an order or read labels.
It verifies original archive bytes, CRC and member inventories; canonical
document bytes and seals; runtime/checker/freeze identities; every original
path, slot and opportunity reference; exact flat-cash, fee and cumulative-state
arithmetic; retained unavailable history; all progress-to-runtime pairs; and the
saved local prefix.

The original source-based independent checker is reused as accepted evidence;
it is not rerun or described as a second independent fill simulator. Original
boundary flags and the `path_complete` values remain untouched.

Acceptance contract:
`c22f691546c5370525a32eca00436f3ebbf812c56f45e058b24aea22854a3657`.
Acceptance/coverage report:
`d876c42cc079360b2af2173094446620df5e1e4944323c8f14b2c51b53b94d13`.

## Coverage outcome

All 12 paths retain all 30 selected dates: 360 session slots, 744 opportunity
references, 240 `flat_complete` sessions and 120
`flat_complete_with_unavailable_inputs` sessions. There are no execution-blocked
or input-failure sessions, and all captured positions/orders resolve flat.

The missing-reference classifications are not all download failures:

| Frozen reason | Unique opportunity IDs | Path references | Interpretation |
|---|---:|---:|---|
| `unavailable_no_fresh_decision_quote` | 22 | 156 | No usable reference under the existing inclusive 100 ms decision-quote rule; not evidence of a failed download or an authorized no-trade decision |
| `unavailable_exact_quote_request` | 1 | 6 | Original JVA quote request unavailable; not permission to retry it |

Alternative account/horizon/scenario references are not independent trades.
The complete report retains each opportunity ID, symbol, decision timestamp,
availability/request evidence hashes and exact affected path/session identities.

A [supplemental inspection](../../research/data-audits/sealed-historical-account-hosted-acceptance-v0.1/entry-reference-observation.json)
matched all 23 availability rows to those exact bindings. All 22 fresh-reference
cases have a saved capture and complete status coverage, but zero usable quote
rows at or before the decision in that saved window, including the inclusive
100 ms lookback. JVA has no usable capture. No earlier standing quote is inferred
from this absence, and no later quote is borrowed for the earlier decision.

| Account, in each of its six alternative paths | Sessions with unavailable inputs | Unavailable references | First affected date |
|---|---:|---:|---|
| Main | 14 of 30 | 21 | 2025-05-30 |
| Small | 6 of 30 | 6 | 2025-05-30 |

Every path has an unavailable opportunity on the first selected date. Therefore
each full-coverage prefix is zero sessions. A later `flat_complete` session
means its own inputs/execution completed; it does not remove the earlier gap
from the inherited cash/account history. Dropping affected dates or treating
missing entries as known skips would not establish a complete account backtest.

## Next development boundary

Local reproduction is no longer a blocker. The next substantive scope is the
unavailable **entry-reference** boundary, not another exit replay. Use the
retained quote/status evidence to distinguish what the existing capture proves
from what it cannot prove. Preserve the 22 no-fresh-reference classifications
and the separate JVA unavailable request until a separately defined rule or
evaluation scope authorizes a change. Do not relax freshness, borrow future
quotes, extend source windows or retry provider requests implicitly.

An available-input-only performance report would require an explicit separate
conditional evaluation scope; it must not be labelled a full-coverage backtest.
This amendment computes no return, win rate, profit factor or policy ranking.
Financial evaluation, retrospective Ross comparison and promotion remain closed.

## Validation

All 25 focused tests passed normally and with Python optimization enabled.
The full suite passed all 2,374 tests in 270.736 seconds with zero skips.
Registration revalidation, exact archive-copy checks and the original-artifact
acceptance run also passed. Synthetic end-to-end cases reject failed checkers,
pending steps, reruns, wrong artifacts, missing progress and altered local
evidence. Coverage tests reject omitted/relabelled inputs, lost gap history,
open state, cash/fee/carry changes, reseeding and false completeness claims.
See the [implementation verification](../../research/data-audits/sealed-historical-account-hosted-acceptance-v0.1/implementation-verification.json).

## Deterministic inspection

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts python \
  scripts/verify_sealed_historical_account_hosted_acceptance_v01.py \
  --hosted-zip research/data-audits/sealed-historical-account-hosted-acceptance-v0.1/hosted-runtime-original.zip \
  --binding-zip research/data-audits/sealed-historical-account-hosted-acceptance-v0.1/source-binding-original.zip \
  --expected-contract-sha256 c22f691546c5370525a32eca00436f3ebbf812c56f45e058b24aea22854a3657 \
  --output /tmp/new-hosted-acceptance-report.json
```

The output must be a new file. Repeating this read-only artifact inspection is
not a historical replay. See the [acceptance registration](../../research/strategy/sealed-historical-account-hosted-acceptance-v0.1.json),
[report](../../research/data-audits/sealed-historical-account-hosted-acceptance-v0.1/acceptance-report.json)
and [recorded hosted provenance and user authorization](../../research/data-audits/sealed-historical-account-hosted-acceptance-v0.1/hosted-provenance.json).
