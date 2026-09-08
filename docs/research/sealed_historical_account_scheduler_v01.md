# Chronological account scheduler v0.1

This isolated child starts from verified valuation checkpoint
`86733376b10b2a5feb252d174254f4e40fe701ef`, tree
`38c5ab6fe7ddee72d27202675620c890af5c51cf`. It pins 82 ancestor files and the
valuation freeze `22328ab6acb6e94a8941748a7f578d95658c8c7880f4571d71404ed47a835afa`.
The hypothesis is that one chronological account clock can enforce the frozen
scarcity rules across overlapping position windows without future execution
knowledge, changed risk limits or retrospective inputs.

## Implemented behavior

The original policy permits one open position per account. The scheduler treats
an outstanding entry as reserved capacity from submission through cancellation
acknowledgment, including zero-fill orders. Positive entry fills remain private
until their actual feedback time. Cash, fees, shares and the account's risk lock
cannot reflect the fill earlier. A fill-reconciliation failure is also deferred
to feedback; its known execution evidence remains explicitly unresolved.

| Same-time phase | Effect |
|---|---|
| Completed bars | Make only completed management bars eligible. |
| Ranked entry decisions | Apply the frozen activation-candidate priority within one account. |
| SIP prints | Observe the original print order and produce eligible management intents. |
| Fill and cancel feedback | Book confirmed execution and acknowledgments. |
| Original window boundary | Settle only the currently active original window. |

Consequently, an entry decision tied with a fill or cancellation cannot reuse
that capacity. A decision one nanosecond after a fully acknowledged flat release
can. Ties in candidate priority reuse the unchanged quality, top-gainer rank,
gain, relative volume, cumulative volume, float and identifier ordering. Caller
list order is not a selection rule. Candidate identity and activation time are
checked; historical scanner-source authentication remains a separate gate.

After a position is confirmed flat and all entry/sell cancellations are known,
the account can accept another symbol without waiting for the old management
window to end. Both original bar and print streams still receive complete
lineage/hash validation, including trailing records after capacity has been
reused. Bad trailing evidence retains the already confirmed account history and
records an input failure; it is not rewritten as a zero-trade result.

One fee book and net account ledger persist throughout a session. Exact flat
cash carries across a complete prefix of the original 30 slots, using the
$30,000 main or $2,000 small seed only once. Daily fees and risk guards restart
from carried capital, not a replacement seed. Fractional cents remain exact.
Each source program and result requires an independent caller commitment, and
`verify_path` reruns every session and intermediate checkpoint.

Known net daily-loss/giveback guards latch a terminal exit request on the next
eligible SIP print. This uses the frozen marketable-limit execution, existing
share reservations, original source bounds and one-terminal-attempt ceiling.
It adds no automatic retry. Partial fills remain open, missing executable
quotes retain an unsubmitted intent, and no liquidation proceeds are invented.

`continue_valued_session` separately verifies a frozen producer prefix and its
causal valuation before handing the next session to the scheduler. Verified
flat capital can execute. Open positions, orders and valuation evidence remain
intact when continuation is not supported. It applies no additional seed.

## Explicit limitations and next work

This completes the tested intraday scheduling component, **not the entire
continuous historical account engine**. Two dependencies remain explicit:

1. Same-symbol re-entry is not implemented by the frozen single-entry binder.
   The scheduler records an unsupported dependency when the account otherwise
   has capacity. It does not silently classify it as a legitimate strategy or
   risk rejection. The existing two-entry policy is not changed.
2. A next-day mark does not authorize resuming an old position outside its
   original execution window. Carried positions, pending orders, incomplete
   feedback and source failures still block later execution. There is no
   guessed share adjustment, cancellation, liquidation or window extension.

Those behaviors need an isolated child before original market/corporate-action
source binding and historical activation. Cross-account attention is unresolved;
main and small paths remain independent. The original parent implementations,
policies, fees, 12 paths, 360 slots, 348 close dependencies, 744 opportunity
references and 162 unavailable references are unchanged. No original market
tapes, provider accounts, brokerage accounts or Ross attachments were opened.
Historical/account-close, financial-metric and promotion eligibility stay false.

## Verification and artifacts

The 42 new tests cover delayed and unfilled entries, exact-time collisions,
entry/sell acknowledgment boundaries, future price and reconciliation-failure
isolation, partial and missing risk exits, fee/cash carry, source failures,
valuation handoff, input tampering and immutable offline registration.

The independent stdlib checker recomputes candidate priority, public order
reservations, frozen execution latencies, fee/share/cash/net-guard arithmetic,
session carry and original metadata. Its 23 synthetic cases include both
execution scenarios and all 12 empty 30-session paths. It imports no production
module. It does not independently simulate every market fill or authenticate
original market-source provenance; full mechanics are recomputed by the primary
source-program verifier.

- [Contract](../../research/strategy/sealed-historical-account-scheduler-v0.1.json)
- [Freeze](../../research/runtime/sealed-historical-account-scheduler-v0.1/freeze-manifest.json)
- [Scheduler](../../src/momentumbot/research/sealed_historical_account_scheduler_v01.py)
- [Tests](../../tests/test_sealed_historical_account_scheduler_v01.py)
- [Independent checker](../../scripts/verify_sealed_historical_account_scheduler_v01.py)
- [Hosted workflow](../../.github/workflows/sealed-historical-account-scheduler-v01.yml)

All 2,106 local tests passed with zero skips, and 174 focused tests passed
normally and optimized. The independent checker verified 378 checkpoints, 88
scheduler events and 30 confirmed journal fills across 23 cases. The
[local audit](../../research/data-audits/sealed-historical-account-scheduler-v0.1-independent-verification.json) records the complete evidence and
preserves development failures. Hosted verification follows code publication.

```bash
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_scheduler_v01.py --verify
PYTHONPATH=src:scripts python scripts/build_sealed_historical_account_scheduler_v01.py --synthetic-vectors --output-root /tmp/new-account-scheduler-vectors
PYTHONPATH=src:scripts python scripts/verify_sealed_historical_account_scheduler_v01.py --vectors /tmp/new-account-scheduler-vectors/synthetic-vectors.json --output /tmp/new-account-scheduler-vectors/independent-verification.json
```

Use the hash-locked execution-quote validation environment and a new output
directory. These commands have no provider or historical-run mode.
