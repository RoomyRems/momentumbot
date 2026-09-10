# Historical setup, stop and source audit v0.1

All 109 original causal prefixes and all 300 recorded entry stops reproduce. The baseline and all original coverage flags remain unchanged.

Exact pullback ordinal counts: `{"1": 5, "10": 6, "11": 1, "12": 3, "13": 1, "17": 1, "18": 1, "2": 13, "25": 1, "27": 1, "3": 19, "4": 17, "5": 12, "6": 13, "7": 4, "8": 3, "9": 8}`.
101/109 opportunities have less than 2R room to the original peak at the planned trigger. 4/109 have nonpositive completed-minute MACD; 0/109 have unknown MACD.

These are descriptive checks on the unchanged Micro policy, not newly installed filters or proof that a filter improves returns.

| Account | Execution | Horizon | Episodes | Net P&L | Entries with room <2R | Entries with MACD ≤0 |
|---|---|---:|---:|---:|---:|---:|
| main_account | l1-conservative-v0.1 | 1 | 42 | -264.77 | 40 | 1 |
| main_account | l1-stress-v0.1 | 1 | 31 | -239.78 | 29 | 1 |
| main_account | l1-conservative-v0.1 | 5 | 42 | -264.77 | 40 | 1 |
| main_account | l1-stress-v0.1 | 5 | 31 | -239.78 | 29 | 1 |
| main_account | l1-conservative-v0.1 | 10 | 42 | -264.77 | 40 | 1 |
| main_account | l1-stress-v0.1 | 10 | 31 | -239.78 | 29 | 1 |
| small_account | l1-conservative-v0.1 | 1 | 15 | -35.75 | 13 | 1 |
| small_account | l1-stress-v0.1 | 1 | 12 | -13.75 | 11 | 1 |
| small_account | l1-conservative-v0.1 | 5 | 15 | -35.75 | 13 | 1 |
| small_account | l1-stress-v0.1 | 5 | 12 | -13.75 | 11 | 1 |
| small_account | l1-conservative-v0.1 | 10 | 15 | -35.75 | 13 | 1 |
| small_account | l1-stress-v0.1 | 10 | 12 | -13.75 | 11 | 1 |

The complete JSON retains every opportunity, source binding, original decision, exact-ordinal cohort and path. SIP trade timestamps and single-venue quote receive timestamps are distinct clocks. No standing/consolidated quote, alternate fill or excluded-trade profit is inferred.

Saved geometry witnesses reproduce the setup and stop. Reproducing the complete causal-prefix hash requires the three original source archives. The audit uses the accepted historical execution results; it does not re-simulate management, fills or accounts.
