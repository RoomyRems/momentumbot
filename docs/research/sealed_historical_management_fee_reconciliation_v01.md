# Historical fees and confirmed-fill reconciliation v0.1

This isolated child of `1cd6f71fa36710c357c30dd3c3b5cda118c1a742`
adds historical fee assumptions and exact account bookkeeping to the frozen
entry-binding and management-fill mechanics. The hypothesis is that confirmed
executions can reconcile cash, shares, daily fees and net account guards without
changing the scanner, Micro strategy, order policy or management signals.

The implementation is `ReconciledAccountDay` in
`src/momentumbot/research/sealed_historical_management_fee_reconciliation_v01.py`.
The registration pins 41 ancestor files, including the verified exit-input
freeze, and assigns a fee period to every one of the original 360 session slots
across 12 account paths. No source tapes or retrospective datasets were opened.

## Historical fee model and evidence

| Trade date | SEC per sale dollar | TAF per sold share / per-trade cap | CAT per executed share, either side | Commission |
|---|---:|---:|---:|---:|
| May 30–June 30, 2025 | $0 | $0.000166 / $8.30 | $0.000035 | $0, assumed |
| July 1–17, 2025 | $0 | $0.000166 / $8.30 | $0.000022 | $0, assumed |

The [SEC April 8 advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2025-2)
sets Section 31 sale assessments to zero from May 14, covering this panel.
The [FINRA fee adjustment schedule](https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule)
specifies the rate and cap in its explicit 2025 column. The unchanged frozen
execution component's 2026 defaults are never used by this child.

CAT includes both the current assessment and the $0.000013 historical
assessment on each executed share. The
[January 28 notice](https://www.catnmsplan.com/sites/default/files/2025-01/01.28.25-CAT_Fee_Alert_2025-1.pdf)
establishes the first period. The
[May 29 announcement](https://www.catnmsplan.com/sites/default/files/2025-05/05.29.25-CAT-Fee-Alert-2025-2.pdf)
proposed reducing the current component from $0.000022 to $0.000009 for July
trades, invoiced in August. This research model assumes that announced July
schedule takes effect. The
[July SEC filing notice](https://www.sec.gov/files/rules/sro/iex/2025/34-103400.pdf)
and [August confirmation](https://www.catnmsplan.com/sites/default/files/2025-08/08.14.25-CAT-Fee-Alert-2025-3.pdf)
are recorded as later verification evidence; they are not pre-trade information
supplied to a strategy or account scheduler. No subsequent reversals or refunds
are retroactively inserted into the panel's buying power.

These are documented **regulatory member assessments plus explicit customer-fee
assumptions**. They do not verify what a particular broker charged a customer.
One-to-one customer pass-through, zero direct-API commissions, and the frozen
parent's account-day rounding convention remain assumptions. Current Alpaca
documents describe accrual and daily posting, but its current fee PDF is dated
September 2026 and is not evidence of a 2025 customer agreement. Other optional,
venue, clearing, financing or service charges have not been inferred. The
[machine-readable source record](../../research/strategy/sealed-historical-management-fee-reconciliation-v0.1-fee-sources.json)
preserves these distinctions; broker-statement equivalence remains false.

## What changes at a confirmed fill

The account is constructed once from an empty, caller-pinned session ledger.
Each entry re-executes frozen binding, sizing and execution, then reconstructs
the identical accepted post-entry ledger before fees are applied. A caller
cannot submit a claimed fill directly to the account reducer.

The fee accumulator retains all confirmed trades for that account, path,
scenario and New York trading date. It caps TAF for each sell trade, sums each
fee type by account-day, rounds each cumulative total upward to cents, and
debits only the increase since the previous fill. A second position retains
the same fee book. Reads, cancel acknowledgements and end-of-day posting do
not debit fees again. Per-campaign attribution assigns each rounding increment
to the campaign causing it; that penny allocation depends on event order.

Sell intents and submissions reserve shares but do not change cash or fees.
Only receipts exposed by the frozen engine at the current clock are booked.
Equal-time market observations precede fill feedback. Partial and zero fills
retain unresolved shares; canceled shares produce no fee or proceeds. Each
order has at most the frozen simulator's one positive fill and duplicate fill
or order identities are rejected.

The exact Decimal journal computes cash, gross and net realized P&L, campaign
costs and net high-water P&L. A child ledger hook installs the final values
before the frozen sell reducer evaluates the unchanged loss/giveback limits.
This prevents a transient gross profit from creating an incorrect high-water
mark. Entry fees also affect net guards. Existing `exit_accepted` event P&L
continues to mean gross execution P&L; the child account and campaign realized
fields mean net P&L, with both quantities explicit in the journal.

Remaining ledger lots move their stops to entry only when the entire intended
target tranche is confirmed filled. A partial target leaves the original stop
and remaining open risk intact. Each public transition works on a copy and
commits only after all evidence, fee, cash and share checks succeed. Failure
preserves the preceding state. If exact values cannot be represented in the
frozen ledger's float projection without changing their decimal values, the
transition fails rather than silently rounding the journal.

## Supported boundary and remaining integration

One position can be active at a time. A flat position can be released only after
all sell and entry cancellation acknowledgements, and its fee/account history
persists for the next position. Existing account locks continue to block new
entries. Fees cannot resize or erase a confirmed fill; any cash shortfall is
explicit. The later scheduler must act on `flatten_required`; this component
does not manufacture a risk-flatten order or fill.

The starting ledger is mechanically pinned, not authenticated historical state.
Imported history, carried open positions, overnight valuation, session close
authentication, continuous scarcity/order scheduling and historical activation
remain outside this child. Confirmed position share closure is not account-close
evidence. The old historical runner and its closed activation gate are unchanged.
All financial metric and broker-statement eligibility flags remain false.

Next: build the authenticated account-state producer, then causal valuation and
continuous account/order integration, before registering and running the sealed
historical account replay. Ross comparison still follows a frozen replay result.

## Verification

The dedicated tests cover both frozen execution scenarios, original entry
binding, partial/unfilled sales, cancellation, one-share management, equal-time
feedback, duplicate application, rollback, daily rounding/caps, the July rate
boundary, net loss/giveback thresholds and a second position's fee carryover.
The independent stdlib checker verifies the registration's file commitments and
all 360 slots, then separately recomputes 28 confirmed executions in ten
synthetic account cases and two additional fee-boundary/cap vectors. It also
rejects a rehashed vector with altered final cash.

The builder and the dedicated workflow are offline after dependency setup.
Neither has provider/account credentials or a historical replay entry point.
Published validation results and retained development failures are recorded in
the accompanying permanent audit and current checkpoint.
