# Conditional historical account evaluation v0.1

**All 12 original account scenarios lose money after their modeled fees.** The
new evaluator has completed the conditional financial step using the saved
hosted replay. It changes no selection, risk, entry, management or execution
policy and does not repeat the historical simulation.

The 1-, 5- and 10-second behavioral-horizon paths have identical financial
results within each account/execution combination. All 12 rows remain in the
[complete report](../../research/data-audits/sealed-historical-account-conditional-evaluation-v0.1/report.md).
The compact table below groups those identical results; it does not pool their
capital, trades or returns.

| Original account seed | Execution assumption | Horizons | Ending equity | Net P&L | Seed return | Closed positions | Net profit factor |
|---|---|---|---:|---:|---:|---:|---:|
| $30,000 | Conservative | 1s / 5s / 10s | $29,735.23 | −$264.77 | −0.882567% | 42 | 0.299884 |
| $30,000 | Stress | 1s / 5s / 10s | $29,760.22 | −$239.78 | −0.799267% | 31 | 0.072776 |
| $2,000 | Conservative | 1s / 5s / 10s | $1,964.25 | −$35.75 | −1.787500% | 15 | 0.158824 |
| $2,000 | Stress | 1s / 5s / 10s | $1,986.25 | −$13.75 | −0.687500% | 12 | 0.345861 |

## Frozen inputs and one question

Parent commit: `d9b2bd3cb5164c651acc8f24a6eddcaf4d935ac8`; tree:
`8acce39b1df31c64c2a4b19a1fc67ac498affb5f`. All seven parent GitHub publication
checks passed, including [CI 34435048257](https://github.com/RoomyRems/momentumbot/actions/runs/34435048257).

The question is what the unchanged hosted accounts earned or lost **conditional
on `strict-observed-quote-entry-gate-v0.1`**. This is a descriptive post-result
analysis, specified after source availability and replay completion were known.
The metric formulas and all-cell population were fixed before calculating the
financial report. This does not establish an unseen-data strategy test, full
market-input coverage, broker equivalence or readiness for live trading.

The exact accepted [hosted run 34362104473](https://github.com/RoomyRems/momentumbot/actions/runs/34362104473)
and its original independent verification remain the mechanical evidence. The
new evaluator reads only committed, hash-pinned hosted/source-binding ZIPs and
accepted observation/coverage documents. It verifies the archived results and
recomputes accounting from their recorded fills. It neither simulates fills nor
executes the original account runner or historical independent checker.

## Entry-policy binding and unchanged history

Before releasing metrics, the evaluator binds all 109 observation rows to their
original opportunity identities, exact decision timestamps, availability
commitments, quote evidence and status evidence. The 23 withhold observations
match all 162 original unavailable path/session references. None has a submitted
order, confirmed fill or other execution event. Every available entry still
requires its original submission and remaining runtime checks.

All 744 opportunity references, 360 session slots, 12 paths and 30 selected dates
remain. Five dates with no Micro decisions are retained. The original gap arrays
and `path_complete=false` values are preserved, including their continued carry
into later sessions. Only this separate conditional report sets
`conditional_financial_metrics_eligible=true`; it does not modify the original
`financial_metrics_eligible=false` or account-backtest-complete flags.

This policy requires an observed quote update inside the original 100 ms
lookback. It does not infer a standing BBO, consolidated NBBO, or the outcome of
trades that were withheld. The source-backed basis and its limitations remain
in the [entry-reference evidence record](sealed_historical_entry_reference_evidence_v01.md).
No Ross labels, transcripts, new market requests or additional source windows
enter this calculation.

## Accounting and metric definitions

- Dollar arithmetic uses Decimal precision 60. Financial ratios are rounded
  half-even to six decimal places; exact monetary values remain lossless strings.
- Each account seed is applied once. Daily equity and buying power carry through
  every selected date. The dates are nonconsecutive research sessions from
  May 30 through July 17, 2025; returns are not annualized.
- The evaluator reconciles 969 confirmed fills into 300 closed position episodes
  across the 12 alternative paths. These counts include overlapping scenarios,
  not 300 independent market trades. Partial sells belong to their entry; a later
  re-entry starts a separate episode even within the same activation.
- Gross P&L comes from confirmed quantities and prices. Every causal incremental
  entry/exit fee is allocated once to its episode and reconciled to the original
  daily fee book, cash, account close and cumulative account carry.
- The original fee model assumes **zero commissions**, with its registered 2025
  regulatory charges and rounding. Reported fees are those modeled charges,
  not a complete real brokerage/operating-cost statement. See the frozen
  [fee implementation](../../src/momentumbot/research/sealed_historical_management_fee_reconciliation_v01.py).
- Win rate, profit factor, average wins/losses and expectancy use **net episode
  P&L**. Zero-net episodes remain in the win-rate denominator. Undefined ratios
  are null with an explicit reason, rather than fabricated infinities or zeros.
- Drawdown compares the initial seed and subsequent **session-close** equity
  peaks. It does not measure intraday mark-to-market drawdown.
- Entry fill rate divides confirmed buy shares by submitted entry-order shares.
  Unfilled or cancelled shares do not become trades, and blocked/withheld entries
  do not enter the submitted-order denominator.

The stress paths filled fewer positions and shares and lost less in total here.
Their negative P&L and profit factors below one still offer no profitability
support. The low main-account share fill rates also limit how much the modest
percentage drawdowns say about behavior at larger executed size. Do not promote
an execution assumption or select a horizon from these results.

The useful next development step is a loss-attribution diagnostic on these fixed
records: separate entry price/size, partial exits, terminal exits and account
blocks. Preserve this losing baseline. Any later policy change needs its own
causal specification and evaluation beyond this already inspected sample.

## Artifacts and reproduction

- [Metric and scope registration](../../research/strategy/sealed-historical-account-conditional-evaluation-v0.1.json):
  `aac233a9b18eb5145c2c0bf8f6ab50f5bb72636afd1c748bd9edf94ce91ec2f1`.
- [Report with all daily histories and closed positions](../../research/data-audits/sealed-historical-account-conditional-evaluation-v0.1/report.json):
  `23fb88bcb2a8cb95dafe7059e0d99c54deed423c7d30a24b280b95d6b00144d8`.
- Runtime content remains
  `a429f6723668fe9614ba6366de44b27d016ef939a5361d323bf58dceef250e91`.
- [Implementation verification](../../research/data-audits/sealed-historical-account-conditional-evaluation-v0.1/implementation-verification.json)
  retains test results and report provenance.

Use a new directory for an offline recalculation. This command reads the saved
results; it is not a historical replay:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts python \
  scripts/evaluate_sealed_historical_account_conditional_v01.py \
  --expected-contract-sha256 aac233a9b18eb5145c2c0bf8f6ab50f5bb72636afd1c748bd9edf94ce91ec2f1 \
  --output-directory /tmp/new-conditional-account-report
```

The CLI rejects an existing output directory and denies network/subprocess I/O.
Tests cover partial exits, re-entry, fee allocation, exact cash continuity,
seed-based drawdown, zero-trade dates, undefined ratios, forged withheld-entry
execution and byte-equivalent recomputation of the committed report. No
full local historical replay is required or performed.

Validation passed **27 focused tests**, **27 optimized tests** and the full
**2,429-test suite** with zero skips in 276.315 seconds on CPython 3.12.14.
Compilation of `src` and `tests` and the final registration check also passed.
