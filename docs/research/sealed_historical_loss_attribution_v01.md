# Historical loss attribution v0.1

**Initial-stop exits account for most of the losses in the unchanged conditional
baseline.** First entries and re-entries both lose money in every account and
execution combination. Entry pricing and modeled fees explain a much smaller
part of the conservative losses. The diagnostic also exposes incomplete fills
and repeated sell attempts, without estimating what a different policy would earn.

The 1-, 5- and 10-second horizons have identical financial results within each
account/execution combination. This compact table groups them; the
[complete report](../../research/data-audits/sealed-historical-loss-attribution-v0.1/report.md)
retains all 12 paths. Dollar values are for each separate path, never pooled.

| Original account seed | Execution assumption | Actual net P&L | Initial-stop gross P&L | Entry price shortfall debit | Modeled fees |
|---|---|---:|---:|---:|---:|
| $30,000 | Conservative | −$264.77 | −$360.58 | +$1.41 | $0.75 |
| $30,000 | Stress | −$239.78 | −$218.36 | −$32.87 | $0.50 |
| $2,000 | Conservative | −$35.75 | −$41.89 | +$2.41 | $0.27 |
| $2,000 | Stress | −$13.75 | −$20.86 | −$0.16 | $0.22 |

Initial-stop gross P&L is one portion of actual gross P&L. Other exit reasons
can offset it: in the main conservative path, targets earned $59.10, first-red-
candle exits earned $34.13, and breakeven-stop exits earned $3.33 before fees.
The entry price column is a separate accounting view, not another amount to
subtract from the exit-reason totals. Negative shortfall means entry price
improvement relative to the original decision ask.

## Frozen scope and source binding

Parent commit: `78050eacc330b82387e0b292479e5e576ea0b19a`; tree:
`c05a3915e6a3b17946425a43fb6ada774324720a`. All seven parent publication
checks passed, including [CI 34436921074](https://github.com/RoomyRems/momentumbot/actions/runs/34436921074).

The question is which recorded entry prices, sizes, exit reasons and execution
stages account for the fixed losses. This diagnostic was specified after the
baseline financial outcomes were known. It is descriptive accounting, not an
unseen-data policy experiment or a causal estimate of changing a rule.

The reader first recomputes the prior conditional report from the exact saved
hosted/source-binding archives and requires equality with its frozen result.
It then binds each entry to its original selected quote and source-plan stop,
and each sell fill to its original order, entry receipt, reason and journal.
Residual, continuation and waiting annotations must match the submitted order
and their original authority records. No quote is selected anew.

All 109 source opportunities remain: 86 original decision references and 23
withhold observations. The report retains all 744 path decisions, including
162 unavailable references, all 360 session slots and all 30 selected dates.
It attributes 300 closed episodes and 669 sell fills across overlapping
alternatives, including 870 submitted sell orders and their unfilled attempts.
These totals are not independent market observations.

Original unavailable-input histories, account flags and losing results are
unchanged. The strict observed-update entry gate, single-venue source limits,
once-only $30,000/$2,000 seeds and zero-commission fee model still apply. Full
market-input coverage and full cross-environment historical reproduction remain
unverified. No historical runner, original historical checker, provider request,
Ross transcript/label access or brokerage action was used.

## Exact entry-price accounting

For each fully closed position, using its confirmed entry quantity and actual
exit quantities and prices:

```text
reference component = sum(sold quantity * (actual exit price - original decision ask))
entry shortfall = confirmed entry quantity * (actual entry price - original decision ask)
actual net P&L = reference component - entry shortfall - original entry/exit fees
```

For the main conservative path this is −$262.61 − $1.41 − $0.75 = −$264.77.
For main stress it is −$272.15 − (−$32.87) − $0.50 = −$239.78: improved entry
pricing relative to the recorded ask did not produce a profitable result.

The reference component holds actual exits and quantities fixed. It is an
algebraic benchmark, not an alternative fill simulation or attainable return.
A different entry could change fills, risk, exits and subsequent account state.
No unfilled or blocked entry receives hypothetical profit or loss.

All monetary arithmetic uses Decimal precision 60. Ratios use half-even rounding
to six decimal places. Recorded floating-point stops use `Decimal(str(value))`,
matching their serialized source value. Entry and exit fees are charged exactly
once and reconcile to the original conditional report for every position,
session and path. These are the original modeled regulatory charges, not a
complete real brokerage cost estimate.

## Entry cohorts and sizing

Re-entry means the second confirmed entry for the same activation in the same
account path. Cohort P&L includes all partial exits and fees for each episode.

| Account / execution | First-entry net P&L | Re-entry net P&L | Re-entry episodes | Entry shares filled / requested |
|---|---:|---:|---:|---:|
| $30,000 / conservative | −$251.34 | −$13.43 | 9 | 2,297 / 16,783 (13.686468%) |
| $30,000 / stress | −$152.75 | −$87.03 | 9 | 1,132 / 20,650 (5.481840%) |
| $2,000 / conservative | −$31.85 | −$3.90 | 1 | 369 / 440 (83.863636%) |
| $2,000 / stress | −$12.35 | −$1.40 | 1 | 217 / 542 (40.036900%) |

Re-entry losses do not explain the negative first-entry cohorts. Removing
re-entries cannot be assumed to recover these exact losses, because subsequent
buying power, risk locks and available opportunities could change.

The report retains submitted, confirmed and cancelled shares, fully unfilled
orders, actual entry notional and initial-stop risk against that session's
opening equity. Summed entry notional is turnover, not simultaneous exposure.
Initial-stop risk is a sizing reference, not a guaranteed loss ceiling.
The low main-account fill fractions prevent scaling these dollar outcomes into
a supported forecast for larger fills or account exposure.

## Exit reasons, execution stages and waiting

Exit reasons and execution stages are separate partitions of the same sell
fills. Each view reconciles independently to gross P&L and fees. A partially
exited episode may touch several groups; episode counts must not be added
across reasons. Entry fees remain one separate debit after each grouped view.

| Account / execution | Target gross P&L | First terminal order | Second residual order | Third or later continuation |
|---|---:|---:|---:|---:|
| $30,000 / conservative | $59.10 | −$153.23 | −$121.61 | −$48.28 |
| $30,000 / stress | $10.51 | −$40.89 | −$35.26 | −$173.64 |
| $2,000 / conservative | $4.86 | −$35.57 | −$3.88 | −$0.89 |
| $2,000 / stress | $4.62 | −$10.10 | −$4.91 | −$3.14 |

These columns identify when realized P&L was booked. They do not establish
that continuation caused an incremental $173.64 loss in main stress: an
unfilled earlier order already carried the position and its market exposure.
Waiting is an overlapping annotation, never an additional P&L category.

The main conservative path has 19 unfilled sell orders out of 114; main stress
has 47 out of 132. For example, the main stress HUSA re-entry on June 23, 2025
filled 233 entry shares, submitted 25 sell orders, received five sell fills and
closed at −$72.88 net. Eighteen of those sell orders had a recorded wait before
submission. That evidence shows execution burden without identifying the return
of a different order policy.

Initial-stop price shortfall is calculated only on sells whose recorded reason
is `initial_stop`: shares multiplied by initial stop minus actual sell price.
It totals $31.31 main conservative, $47.178 main stress, $1.84 small conservative
and −$2.88 small stress. Its sign can show improvement; it is not a causal cost
of waiting or a claim that fills at the stop were available.

## Artifacts, validation and next development

- [Registration](../../research/strategy/sealed-historical-loss-attribution-v0.1.json):
  `0a6153ad10b3a97ff13252db6176bdf01bf4c25474a2ee38bec8d5b5b49487ff`.
- [Full report](../../research/data-audits/sealed-historical-loss-attribution-v0.1/report.json):
  `5487f89ae0002b276aee2c051446a862d58ec0afb1ec4c0a6b3fa16b5ff3a7d3`.
- [Implementation verification](../../research/data-audits/sealed-historical-loss-attribution-v0.1/implementation-verification.json)
  records the final test results and exact output hashes.
- The [prior financial report](sealed_historical_account_conditional_evaluation_v01.md)
  remains `23fb88bcb2a8cb95dafe7059e0d99c54deed423c7d30a24b280b95d6b00144d8`;
  runtime content remains `a429f6723668fe9614ba6366de44b27d016ef939a5361d323bf58dceef250e91`.

Recalculate from the saved records into a new directory:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts python \
  scripts/attribute_sealed_historical_losses_v01.py \
  --expected-contract-sha256 0a6153ad10b3a97ff13252db6176bdf01bf4c25474a2ee38bec8d5b5b49487ff \
  --output-directory /tmp/new-loss-attribution
```

The CLI denies network/subprocess I/O and rejects existing output directories.
Focused tests cover partial exits, signed price differences, exact fee/quantity
accounting, missing or forged replacement authority, stage ordering, overlapping
waits, unfilled orders and exact reproduction of the full committed report.

Validation passed **22 focused tests**, **22 optimized tests** and all **2,451
full-suite tests** with zero skips in 301.920 seconds on CPython 3.12.14.
Compilation of `src` and `tests` and final registration verification also passed.

The next useful development step is auditing the time-causal setup evidence,
original stop placement and source alignment behind the stop-heavy entries.
Preserve this baseline and examine all relevant entries before proposing a
separate policy change. This accounting report alone does not justify disabling
stops, widening them, removing re-entry or promoting a policy from this sample.
