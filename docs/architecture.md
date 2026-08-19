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

The AI shadow reviewer sits between contextual candidate/setup assessment and the risk governor. It receives structured, time-causal features only. The risk governor remains authoritative.

## Deterministic and AI responsibility

The intended system is hybrid, but not every uncertain task belongs to AI.

| Layer | Deterministic owner | Possible AI contribution |
|---|---|---|
| Data availability | exchange/provider timestamps, completed bars, causal joins | none |
| Scanner facts | gain, RVOL, price, float, volume, rank | none |
| Catalyst | publication chronology and evidence packet | substance, specificity, credibility and theme interpretation |
| Market attention | cross-sectional rank, volume/velocity and leadership transitions | contextual judgment about the obvious leader and theme saturation |
| Chart/setup | VWAP, EMA, MACD, pullback geometry and trigger state | bounded shadow judgment for ambiguous cleanliness/context |
| Level 2/tape | event capture, book/tape statistics, latency and liquidity checks | interpretation of structured absorption/conflict summaries after validation |
| Orders/risk | sizing caps, max loss, order state, broker reconciliation and lockouts | none; AI cannot submit orders or raise risk |
| Review | immutable journal and outcome calculation | explanation, error taxonomy and evidence synthesis |

An AI response must use a versioned structured schema, cite the causal evidence it received, express confidence, support `abstain`, and expire after a bounded time. While AI is shadow-only or advisory, missing, late, malformed or unavailable output leaves the deterministic path unchanged. If a future promoted policy makes AI approval mandatory, the same failure means no trade. It never creates a more aggressive fallback.

## Live latency path

Large-model inference is not placed inside every quote or tape update. Streaming code continuously derives deterministic summaries from Level 2 and time-and-sales. Slower contextual AI work begins when a candidate activates so that catalyst, theme, history and leadership assessments can be ready before a technical trigger arms. Any later real-time AI model must prove that its bounded response time fits the decision window before paper use.

```text
live feeds -> deterministic event state -> causal structured snapshot
                                             |              |
                                  AI context assessment   fast setup/trigger
                                             |              |
                                             +-- validated --+
                                                     |
                                          deterministic risk/order gate
```

## AI authority progression

1. **Offline research:** compare structured AI judgments with documented evidence.
2. **Historical shadow:** record decisions on frozen, label-blind replays; no trade changes.
3. **Live shadow:** consume live feeds and measure latency, stability and calibration; no orders.
4. **Paper advisory:** AI may rank or veto within deterministic eligibility, never loosen risk.
5. **Paper authority:** only a versioned, validated policy may affect orders inside deterministic limits.

Live-money authority requires a later explicit safety and promotion decision. It is not implied by historical or paper success.

## Named profiles, not config sprawl

The first two strategy profiles are:

- `current-general-2026`: $2-$20, >=10% gain, >=5x RVOL, float <10M, fresh news for A-quality.
- `current-small-account-2026`: the documented challenge variant, tightened toward $1.50-$6, >=25% gain, >=5x RVOL, float <10M, and top-three gainer rank.

The paper risk policy is deliberately separate from Ross's account-sizing examples. `paper-safe` currently risks 0.25% of starting/current equity per trade, caps position value at 50% of equity, and locks after a 1% daily loss or 50% profit giveback. This is a project safety policy, not a claim about Ross's exact risk size.

## Campaign and account-state boundary

`campaign-portfolio-account-state-v0.1` is the standalone event-state foundation between frozen opportunity/execution evidence and a future portfolio replay. It groups repeated plan emissions by candidate activation while binding campaign identity to the unique account, main/small class and policy version. It reconciles caller-supplied fills against held lots, buying power, notional, open risk, entry-role, halt, position-count, daily-P&L and terminal-lock state.

The ledger has no account-limit defaults and is not wired to the baseline runtime. It does not choose among equal-time opportunities, create or size orders, or synthesize fills. A simultaneous capital collision remains explicitly unresolved until a deterministic priority is separately registered. This keeps position/account mechanics deterministic without smuggling in an untested selection or aggression policy.

`paper-account-scarcity-policy-v0.1` supplies the first separately registered limits. Main and small accounts retain distinct IDs and scanner profiles while sharing the existing project `paper-safe` envelope: 0.25% maximum open campaign risk, 1% daily loss, 50% position value and 50% profit giveback, all materialized from causal session-start equity and buying power. A one-position/two-entry cap is classified as conservative paper engineering, not a Ross-authored rule. Same-account capacity collisions reuse the existing candidate ranking; cross-account attention remains unresolved and fails closed.

## Causal setup translation

The first deterministic setup is the current first-pullback confirmation entry. It requires a fresh session-high impulse, <=50% pullback, volume contraction, VWAP/EMA9 support, positive 12/26/9 MACD, limited topping-tail rejection, and >=2R room back to the prior high. The trigger is armed from completed data for the next bar.

The corpus does not specify a unique machine algorithm for selecting the impulse base. The baseline uses the minimum low of the five completed bars leading into the fresh high. This is explicitly marked for ablation and must never be presented as a verbatim Cameron rule.

## Fill handling

A backtest fill is not automatically accepted just because the planned trigger was good. The simulator recalculates stop distance and reward/risk from the actual simulated fill. A gap/slippage fill that no longer offers the required 2R opportunity is rejected. If an OHLC minute touches both entry and stop, the simulator assumes the adverse order: entry first, stop second.
