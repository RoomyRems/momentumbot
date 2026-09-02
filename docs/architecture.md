# Architecture

## Runtime boundary

```text
point-in-time market/news/reference data
              |
      deterministic features
              |
       candidate assessment
       A / conditional / reject
              |
       setup state machine
              |
       fill-quality recheck
              |
      deterministic risk governor
              |
       execution simulator
              |
       campaign + session journal
```

The future AI shadow reviewer will sit between setup assessment and the risk governor. It will receive structured features only. The risk governor remains authoritative.

## Named profiles, not config sprawl

The first two strategy profiles are:

- `current-general-2026`: $2-$20, >=10% gain, >=5x RVOL, float <10M, fresh news for A-quality.
- `current-small-account-2026`: the documented challenge variant, tightened toward $1.50-$6, >=25% gain, >=5x RVOL, float <10M, and top-three gainer rank.

The paper risk policy is deliberately separate from Ross's account-sizing examples. `paper-safe` currently risks 0.25% of starting/current equity per trade, caps position value at 50% of equity, and locks after a 1% daily loss or 50% profit giveback. This is a project safety policy, not a claim about Ross's exact risk size.

## Causal setup translation

The first deterministic setup is the current first-pullback confirmation entry. It requires a fresh session-high impulse, <=50% pullback, volume contraction, VWAP/EMA9 support, positive 12/26/9 MACD, limited topping-tail rejection, and >=2R room back to the prior high. The trigger is armed from completed data for the next bar.

The corpus does not specify a unique machine algorithm for selecting the impulse base. The baseline uses the minimum low of the five completed bars leading into the fresh high. This is explicitly marked for ablation and must never be presented as a verbatim Cameron rule.

## Fill handling

A backtest fill is not automatically accepted just because the planned trigger was good. The simulator recalculates stop distance and reward/risk from the actual simulated fill. A gap/slippage fill that no longer offers the required 2R opportunity is rejected. If an OHLC minute touches both entry and stop, the simulator assumes the adverse order: entry first, stop second.
