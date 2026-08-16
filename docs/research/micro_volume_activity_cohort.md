# Micro volume activity cohort v0.1

## Purpose

The five labeled Micro seed cases show a potentially useful interaction between bounded prequalification context and removal of the hard lower-pullback-volume gate, but they also show substantial activity inflation. A larger label-free cohort is therefore used to stress the activity consequence before considering any further policy work.

This is not called a negative-outcome or false-positive cohort. No human skip/trade labels exist for its candidates, and its conditional candidate gate omits point-in-time float, news and full cross-sectional rank. It can measure how the four already-frozen cells behave after a causal market qualification; it cannot score imitation or full-scanner selectivity.

## Precommitted design

The design is frozen at `research/benchmarks/suites/micro-volume-activity-cohort-v0.1.json` before market discovery.

- Dates are chosen by calendar alone: the second Wednesday of February, May, August and November 2025, then February and May 2026.
- For each date, the first two symbols to causally satisfy the `current-general-2026` price, gain and exact same-time RVOL gate are selected. Symbol ascending is the only tie-breaker.
- Selection never reads later session high, maximum gain, maximum RVOL, micro plans, modeled fills, P&L or Ross behavior labels.
- A date or candidate is never replaced because its replay is inactive, unavailable or unfavorable.
- All four cells for one candidate share the same SIP trades, derived 10-second bars and completed-minute support inputs.

The cells remain unchanged:

| Cell | Prequalification context | Hard lower-volume gate |
|---|---|---|
| Baseline | Off | On |
| Context only | On | On |
| Volume only | Off | Off |
| Context + volume | On | Off |

## Readout contract

The aggregate readout reports paired plan-count and modeled-fill-count deltas, changes in first plan/fill timing and pullback ordinal, and context/volume interaction counts. The volume contrasts are `volume_only - baseline` and `context_plus_volume - context_only`; the context contrasts are `context_only - baseline` and `context_plus_volume - volume_only`.

Each plan is an independently refreshed diagnostic opportunity. Repeated modeled fills do not represent portfolio position state, buying-power limits, campaign re-entry rules or realized P&L.

The cohort is never scored against retrospective behavior labels and is not policy-promotion eligible. A favorable result could justify a separately designed validation stage; it cannot promote either volume-off ablation by itself.
