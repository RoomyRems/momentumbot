# Fixed new-panel account context v0.1

This child of `6a7e385b277aab0c0690ad0325bc5f81e2225d70` connects the verified
synthetic source catalogue to the final account engine. All 24 arm/account/
horizon/scenario paths execute their own 30 registered March–May 2026 sessions,
with once-only $30,000/$2,000 seeds and exact previous-close handoffs. It does
not activate a historical backtest or establish the hybrid strategy's edge.

## Source and account boundary

`replay_synthetic_panel` accepts the existing `SourceArchive` plus a separately
pinned synthetic execution inventory. It reconstructs the full source panel,
then requires an explicit available/unavailable record for **every** reconstructed
plan, including third and later pullbacks. No candidate rank, decision, mask,
starting balance, claimed fill, or saved control result is a public input.

Original scanner activation rows produce the account candidates through the
unchanged original profile projection. The original Micro reconstruction and
first-two binding produce decisions and selection eligibility. New opportunity
identities identify this panel; dates are never mapped to the old catalogue.
Window lengths, strict quote reference requirements, native fill mechanics,
risk/sizing, event priority, management and terminal continuation are inherited.

All declared-available entry/exit evidence is checked before either arm runs,
including evidence belonging to a withheld late trigger. Source streams retain
the original chronological verification: an invalid trailing stream preserves
known account state and blocks subsequent sessions. A late selection withhold
stays at its original event time/rank, creates no order or campaign entry, and
still consumes and verifies its management streams.

Each arm/cell has its own account and session identities. A later session must
use the immediately preceding close from that exact path and arm. Flat cash
carries without reset. Open shares, pending orders, fees and unresolved inputs
are retained; missing marks, corporate actions or expired windows do not create
an invented liquidation or permit a fresh seed. Explicit unavailable entry
inputs remain recorded as nonblocking source gaps, separately from blocking
runtime failures and unresolved positions.

## Isolated engine integration

The two new modules leave every frozen ancestor file unchanged. The context
module owns the new slot, opportunity, seed and fee-date identities. The engine
module copies only the methods whose module-level dependencies require that
new context. Fifteen method bodies are compared structurally with their frozen
parents, allowing explicit validator/candidate/session-start substitutions,
child method names and the original final-engine initialization fields.

The final engine's market processing, order feedback, source cursors, entry
roles and campaign limits, position management, cancellation/continuation,
cash journal and risk projection are inherited directly. Fee accumulation and
rounding also use the original implementation. This source comparison guards
against an unintended policy change; it is not an independent execution model.

## Required fee-date context

The original fee book deliberately permits only its 2025 interval. The first
integration attempt stopped at that guard. The new child therefore registers
an explicit 2026 schedule shared by both arms. **Numeric historical rates differ
from the old panel**; fee arithmetic, rounding and customer pass-through
assumptions are unchanged. This exogenous date correction was made before any
new-panel historical prices or outcomes were opened.

| Registered dates | SEC per sale dollar | TAF per sold share / trade cap | CAT per executed share, either side |
|---|---:|---:|---:|
| March 4–April 2, 2026 | $0 | $0.000195 / $9.79 | $0 |
| April 6–30, 2026 | $0.0000206 | $0.000195 / $9.79 | $0 |
| May 4–19, 2026 | $0.0000206 | $0.000195 / $9.79 | $0.000003 |

The [SEC February 27 advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2)
sets the transaction rate change for April 4. The
[FINRA adjustment schedule](https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule)
provides the explicit 2026 equity TAF rate and cap.

[CAT's November 25 notice](https://www.catnmsplan.com/sites/default/files/2025-11/11.25.25-CAT-Fee-Alert-2025-4.pdf)
ends the prior monthly invoices after November trades. The April 1 notices
propose [a $0.000001 prospective assessment](https://www.catnmsplan.com/sites/default/files/2026-04/04.01.26-CAT-Fee-Alert-2026-1.pdf)
and [a $0.000002 historical assessment](https://www.catnmsplan.com/sites/default/files/2026-04/04.01.26-CAT-Fee-Alert-2026-2.pdf)
on May trades. The prospective notice also states that reserves fund
December–April costs without CAT assessments for that period.

The model assumes the announced May schedule takes effect. Later FINRA filings
and CAT confirmation are verification provenance only. No later refund or
revised assessment is inserted into earlier buying power. Zero direct-API
commissions, one-to-one customer pass-through and trade-date accrual with the
original daily upward-cent rounding remain research assumptions. These member
assessment sources do not authenticate a broker customer agreement or statement.
Every date's exact rates and source references are frozen in the
[fee record](../../research/strategy/early-pullback-panel-accounts-v0.1-fee-sources.json).

## Provider checks and remaining source gates

The [provider-check preparation](../../research/data-audits/early-pullback-panel-accounts-v0.1/provider-check-preparation.json)
binds the unchanged four requests to ordinal and request hashes: one Alpaca SIP
SPY daily interval check, two minimal Massive membership samples and one
Databento XNAS.ITCH dataset-range metadata check. It preserves no-retry and
no-pagination limits, zero currently authorized calls, and a $0.00 authorized
incremental spend. Actual incremental cost remains unknown. There is no provider
transport or durable one-shot consumption implementation in this checkpoint.

Those checks can establish only limited availability evidence. They cannot
establish every full session, a complete point-in-time universe, exhausted
candidate discovery, SEC/news lineage or complete execution coverage. The
source adapter still uses declared synthetic candidate/membership inputs.
Separately pinned synthetic management and quote/status streams also do not
prove common vendor origin or consistency with every overlapping scanner/Micro
source record. Those are remaining historical capture/provenance requirements.

Next is bounded provider transport and request/response provenance, independently
confirmed full sessions, and the exact shared source request graph. Paid capture
requires quote evidence, per-request and aggregate ceilings, and one-shot
consumption before execution. Only verified real inputs can enable a later
historical child. Both complete account chains must be frozen before any
registered financial comparison is opened.

## Verification and retained attempts

Provider-free registration and tests:

```bash
PYTHONPATH=src:scripts python -O scripts/build_early_pullback_panel_accounts_v01.py
PYTHONPATH=src:scripts python -m unittest tests.test_early_pullback_panel_accounts_v01 -v
```

Focused coverage includes all 24 paths/720 slots, distinct arm identities,
once-only seeds, DST and the last selected date, independently derived candidate
ranks, late withholds, unavailable inputs, open-position carry, corrupted
trailing streams, source commitments, and unchanged ancestor guards. Fee tests
check the dated rate boundaries, per-trade TAF cap, daily increments and
duplicate-fill rejection. All 23 focused tests pass in 26.965 seconds normally
and 27.140 seconds with assertions disabled under pandas 3.0.5/NumPy 2.5.3.
All 2,572 full-suite tests pass in 428.471 seconds with zero skips; compilation
and optimized registration validation pass. Exact results are in the
[implementation verification](../../research/data-audits/early-pullback-panel-accounts-v0.1/implementation-verification.json).

The first unpublished run found the old fee interval. The next reached the
old session-start ancestry guard. The following run found a missing copied
candidate-schema alias. A fourth run reached actual fills; two assertions had
incorrectly assumed that the synthetic target/stop combination lost money.
The test now reconciles its known cash/fee arithmetic, and its common quote
fixture provides sufficient exit depth for both fixed participation scenarios.
A subsequent test exposed that the common tape lacked a fresh observed update
at the stress arrival. The fixture now includes that update to exercise both
fill paths, and a separate test preserves the original valid no-fill/no-fee case.
The $8 scanner fixture also correctly excludes the small-account profile;
its zero-activity paths are retained, and a separate qualifying-price fixture
exercises small-account fills using the original $2,000 seed and risk limits.
No execution or management rule was changed to satisfy those assertions.
Exact code/registration snapshots and all failed logs are retained. One later
test process returned exit 1 with an empty log; it is recorded as an unverified
execution attempt and was retried without code changes.
The first full-suite invocation also lost its session handle without a final
result. Its partial log is preserved. A detached retry did not produce a start
marker; the required gate was rerun as a tracked foreground process. Neither
incomplete invocation is counted as a passing full suite.

The [saved synthetic source/execution bundles](../../research/data-audits/early-pullback-panel-accounts-v0.1/synthetic-bundle-verification.json)
and replays demonstrate reproducible
account plumbing, not financial evidence for the selected historical dates.
The main-account case has 24 control entries, 18 child entries, six late
withholds and 24 retained unavailable references across its fixed paths. Its
small-account alternatives correctly remain inactive. The qualifying-price
case has 24 entries per arm across both account classes. Each case retains
all 720 slots. Both results also reproduce exactly under pandas 3 with
assertions disabled, using the same saved source and execution bytes.

To reproduce a saved case without provider access:

```python
import gzip, json
from pathlib import Path
from momentumbot.research import early_pullback_panel_accounts_v01 as account

base = Path(account.BASE)
audit = json.loads((base / "synthetic-bundle-verification.json").read_bytes())
case = audit["cases"][0]
execution = json.loads(gzip.decompress((base / case["execution"]["file"]).read_bytes()))
result = json.loads(gzip.decompress((base / case["result"]["file"]).read_bytes()))
with account.sources.SourceArchive(base / case["source_file"], **case["source_pins"]) as archive:
    account.verify_replay(archive, execution, result,
        expected_execution_sha256=case["execution"]["full_envelope_sha256"],
        expected_result_sha256=case["result"]["full_envelope_sha256"])
```

The original losing baseline, all earlier failures and source gaps, and the
user's waiver of another local historical baseline replay remain intact.
Crucial discretionary/context components still need integration. Transcripts
remain available for offline versioned design, with recap actions, fills,
later outcomes and evaluation narratives excluded from backtests and runtime.
