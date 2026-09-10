# Conditional account results — strict observed-update policy v0.1

These results use the unchanged accepted hosted replay and all 30 selected dates
from May 30 to July 17, 2025. Each row is a separate account history. Seeds are
$30,000 and $2,000, applied once. No return is annualized or combined across rows.

| Account | Horizon | Execution | Final equity ($) | Gross P&L ($) | Fees ($) | Net P&L ($) | Return (%) | Max close drawdown ($) | Max close drawdown (%) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| main_account | 1s | l1-conservative-v0.1 | 29735.23 | -264.02 | 0.75 | -264.77 | -0.882567 | 264.77 | 0.882567 |
| main_account | 1s | l1-stress-v0.1 | 29760.22 | -239.28 | 0.5 | -239.78 | -0.799267 | 239.82 | 0.799399 |
| main_account | 5s | l1-conservative-v0.1 | 29735.23 | -264.02 | 0.75 | -264.77 | -0.882567 | 264.77 | 0.882567 |
| main_account | 5s | l1-stress-v0.1 | 29760.22 | -239.28 | 0.5 | -239.78 | -0.799267 | 239.82 | 0.799399 |
| main_account | 10s | l1-conservative-v0.1 | 29735.23 | -264.02 | 0.75 | -264.77 | -0.882567 | 264.77 | 0.882567 |
| main_account | 10s | l1-stress-v0.1 | 29760.22 | -239.28 | 0.5 | -239.78 | -0.799267 | 239.82 | 0.799399 |
| small_account | 1s | l1-conservative-v0.1 | 1964.25 | -35.48 | 0.27 | -35.75 | -1.787500 | 35.75 | 1.787500 |
| small_account | 1s | l1-stress-v0.1 | 1986.25 | -13.53 | 0.22 | -13.75 | -0.687500 | 13.79 | 0.689486 |
| small_account | 5s | l1-conservative-v0.1 | 1964.25 | -35.48 | 0.27 | -35.75 | -1.787500 | 35.75 | 1.787500 |
| small_account | 5s | l1-stress-v0.1 | 1986.25 | -13.53 | 0.22 | -13.75 | -0.687500 | 13.79 | 0.689486 |
| small_account | 10s | l1-conservative-v0.1 | 1964.25 | -35.48 | 0.27 | -35.75 | -1.787500 | 35.75 | 1.787500 |
| small_account | 10s | l1-stress-v0.1 | 1986.25 | -13.53 | 0.22 | -13.75 | -0.687500 | 13.79 | 0.689486 |

| Account | Horizon | Execution | Closed positions | Active dates | Net win rate (%) | Net profit factor | Net expectancy ($) | Entry shares filled/requested | Share fill rate (%) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| main_account | 1s | l1-conservative-v0.1 | 42 | 21 | 28.571429 | 0.299884 | -6.304048 | 2297/16783 | 13.686468 |
| main_account | 1s | l1-stress-v0.1 | 31 | 18 | 22.580645 | 0.072776 | -7.734839 | 1132/20650 | 5.481840 |
| main_account | 5s | l1-conservative-v0.1 | 42 | 21 | 28.571429 | 0.299884 | -6.304048 | 2297/16783 | 13.686468 |
| main_account | 5s | l1-stress-v0.1 | 31 | 18 | 22.580645 | 0.072776 | -7.734839 | 1132/20650 | 5.481840 |
| main_account | 10s | l1-conservative-v0.1 | 42 | 21 | 28.571429 | 0.299884 | -6.304048 | 2297/16783 | 13.686468 |
| main_account | 10s | l1-stress-v0.1 | 31 | 18 | 22.580645 | 0.072776 | -7.734839 | 1132/20650 | 5.481840 |
| small_account | 1s | l1-conservative-v0.1 | 15 | 13 | 13.333333 | 0.158824 | -2.383333 | 369/440 | 83.863636 |
| small_account | 1s | l1-stress-v0.1 | 12 | 11 | 25.000000 | 0.345861 | -1.145833 | 217/542 | 40.036900 |
| small_account | 5s | l1-conservative-v0.1 | 15 | 13 | 13.333333 | 0.158824 | -2.383333 | 369/440 | 83.863636 |
| small_account | 5s | l1-stress-v0.1 | 12 | 11 | 25.000000 | 0.345861 | -1.145833 | 217/542 | 40.036900 |
| small_account | 10s | l1-conservative-v0.1 | 15 | 13 | 13.333333 | 0.158824 | -2.383333 | 369/440 | 83.863636 |
| small_account | 10s | l1-stress-v0.1 | 12 | 11 | 25.000000 | 0.345861 | -1.145833 | 217/542 | 40.036900 |

## Scope and interpretation

- All 109 opportunity observations bind to the original sources. The 23 strict-policy
  withhold decisions match all 162 original unavailable path references, with no entry
  submitted or filled for those decisions. Original gap history remains unchanged.
- All 360 session slots remain, including dates with no decisions or no filled trades.
- Position statistics combine partial exits; a later re-entry starts a new position.
  Win rate, profit factor and expectancy use P&L after the original charged fees.
- Drawdown measures seed/session-close equity only. It is not intraday mark-to-market risk.
- This evaluates a single-venue observed-update policy. No standing BBO or NBBO is inferred.
  Source availability was known when this conditional scope was specified. These are
  descriptive research results, not an unseen-data validation or evidence of a live edge.
- Captured positions and orders finish flat; full market-input coverage and the original
  account-backtest-complete flags remain false. No runtime, source window or threshold changed.
- No historical replay, provider request, Ross-label access or broker order was executed.

[Machine-readable results, all daily equity histories and closed positions](report.json).

Contract: `aac233a9b18eb5145c2c0bf8f6ab50f5bb72636afd1c748bd9edf94ce91ec2f1`.  
Report: `23fb88bcb2a8cb95dafe7059e0d99c54deed423c7d30a24b280b95d6b00144d8`.  
Runtime: `a429f6723668fe9614ba6366de44b27d016ef939a5361d323bf58dceef250e91`.
