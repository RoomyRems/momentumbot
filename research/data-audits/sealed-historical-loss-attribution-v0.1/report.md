# Loss attribution from the saved conditional replay

All rows describe separate original account paths. Reasons and stages are alternative views
of the same exits; they must not be added together. All 30 dates and unavailable histories remain.

## Entry price accounting bridge

The reference component uses actual exit prices and actual quantities with the original decision ask.
It is an algebraic benchmark, not an alternative execution result or attainable profit estimate.

| Path | Reference-to-actual-exit component ($) | Entry shortfall debit ($) | Fees ($) | Actual net P&L ($) |
|---|---:|---:|---:|---:|
| main_account-1s-l1-conservative-v0.1 | -262.61 | 1.41 | 0.75 | -264.77 |
| main_account-1s-l1-stress-v0.1 | -272.15 | -32.87 | 0.5 | -239.78 |
| main_account-5s-l1-conservative-v0.1 | -262.61 | 1.41 | 0.75 | -264.77 |
| main_account-5s-l1-stress-v0.1 | -272.15 | -32.87 | 0.5 | -239.78 |
| main_account-10s-l1-conservative-v0.1 | -262.61 | 1.41 | 0.75 | -264.77 |
| main_account-10s-l1-stress-v0.1 | -272.15 | -32.87 | 0.5 | -239.78 |
| small_account-1s-l1-conservative-v0.1 | -33.07 | 2.41 | 0.27 | -35.75 |
| small_account-1s-l1-stress-v0.1 | -13.69 | -0.16 | 0.22 | -13.75 |
| small_account-5s-l1-conservative-v0.1 | -33.07 | 2.41 | 0.27 | -35.75 |
| small_account-5s-l1-stress-v0.1 | -13.69 | -0.16 | 0.22 | -13.75 |
| small_account-10s-l1-conservative-v0.1 | -33.07 | 2.41 | 0.27 | -35.75 |
| small_account-10s-l1-stress-v0.1 | -13.69 | -0.16 | 0.22 | -13.75 |

## Gross P&L recorded at each exit reason

Entry and exit fees are excluded from this table; the price bridge above includes all fees.

| Path | Initial stop ($) | Breakeven stop ($) | First target ($) | First red candle ($) | Account risk ($) |
|---|---:|---:|---:|---:|---:|
| main_account-1s-l1-conservative-v0.1 | -360.58 | 3.33 | 59.1 | 34.13 | 0 |
| main_account-1s-l1-stress-v0.1 | -218.36 | 0.12 | 10.51 | -20.69 | -10.86 |
| main_account-5s-l1-conservative-v0.1 | -360.58 | 3.33 | 59.1 | 34.13 | 0 |
| main_account-5s-l1-stress-v0.1 | -218.36 | 0.12 | 10.51 | -20.69 | -10.86 |
| main_account-10s-l1-conservative-v0.1 | -360.58 | 3.33 | 59.1 | 34.13 | 0 |
| main_account-10s-l1-stress-v0.1 | -218.36 | 0.12 | 10.51 | -20.69 | -10.86 |
| small_account-1s-l1-conservative-v0.1 | -41.89 | -0.05 | 4.86 | 1.6 | 0 |
| small_account-1s-l1-stress-v0.1 | -20.86 | 0.12 | 4.62 | 2.59 | 0 |
| small_account-5s-l1-conservative-v0.1 | -41.89 | -0.05 | 4.86 | 1.6 | 0 |
| small_account-5s-l1-stress-v0.1 | -20.86 | 0.12 | 4.62 | 2.59 | 0 |
| small_account-10s-l1-conservative-v0.1 | -41.89 | -0.05 | 4.86 | 1.6 | 0 |
| small_account-10s-l1-stress-v0.1 | -20.86 | 0.12 | 4.62 | 2.59 | 0 |

## Sizing and execution

| Path | Entry shares filled/requested | First-entry net ($) | Re-entry net ($) | Initial-stop signed shortfall ($) | Unfilled sell orders |
|---|---:|---:|---:|---:|---:|
| main_account-1s-l1-conservative-v0.1 | 2297/16783 | -251.34 | -13.43 | 31.31 | 19 |
| main_account-1s-l1-stress-v0.1 | 1132/20650 | -152.75 | -87.03 | 47.178 | 47 |
| main_account-5s-l1-conservative-v0.1 | 2297/16783 | -251.34 | -13.43 | 31.31 | 19 |
| main_account-5s-l1-stress-v0.1 | 1132/20650 | -152.75 | -87.03 | 47.178 | 47 |
| main_account-10s-l1-conservative-v0.1 | 2297/16783 | -251.34 | -13.43 | 31.31 | 19 |
| main_account-10s-l1-stress-v0.1 | 1132/20650 | -152.75 | -87.03 | 47.178 | 47 |
| small_account-1s-l1-conservative-v0.1 | 369/440 | -31.85 | -3.9 | 1.84 | 0 |
| small_account-1s-l1-stress-v0.1 | 217/542 | -12.35 | -1.4 | -2.88 | 1 |
| small_account-5s-l1-conservative-v0.1 | 369/440 | -31.85 | -3.9 | 1.84 | 0 |
| small_account-5s-l1-stress-v0.1 | 217/542 | -12.35 | -1.4 | -2.88 | 1 |
| small_account-10s-l1-conservative-v0.1 | 369/440 | -31.85 | -3.9 | 1.84 | 0 |
| small_account-10s-l1-stress-v0.1 | 217/542 | -12.35 | -1.4 | -2.88 | 1 |

[All daily records, decisions, position episodes, sell orders and sell fills](report.json).

Attribution identifies where P&L was booked; it does not establish the causal effect of changing an entry,
size, stop, wait or continuation rule. Blocked/unfilled entries receive no hypothetical P&L.
The original single-venue quote policy, zero-commission fee assumptions and conditional coverage limits apply.
No historical replay, market request, Ross-label access or policy promotion occurred.

Contract: `0a6153ad10b3a97ff13252db6176bdf01bf4c25474a2ee38bec8d5b5b49487ff`.  
Report: `5487f89ae0002b276aee2c051446a862d58ec0afb1ec4c0a6b3fa16b5ff3a7d3`.
