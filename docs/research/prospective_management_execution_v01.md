# Prospective management and execution v0.1

## What is frozen

This child freezes one management translation and two execution-assumption
scenarios before the August 24–September 4 account panel. It does not alter
Micro-v0.1, reopen July labels, or place a paper or live order.

The contract content SHA-256 is
`14812b9f25b5ea7230254ed86b1e0eaa30fffe3dc13b1ee141b19770706090f9`.
It binds the unchanged Micro policy, account integration, completed July
management sensitivity, and Level 2 feasibility registration.

## Management selection without July fitting

The July result was already visible when this child was registered, so July
P&L and R are explicitly prohibited selection inputs. The chosen rule is
`half-2r-breakeven-first-red-1m` because the current normative training:

- permits realizing half at the first target while retaining a runner; and
- explicitly teaches the completed red-candle exit on a one-minute chart.

This is not the least-negative July main-account cell. That adverse fact is
recorded to make the non-optimization boundary auditable.

The first target is the confirmed average fill plus twice the original
per-share risk. Only after that target actually fills is half realized and the
remainder stop moved to the confirmed average fill. The runner exits on the
first completed one-minute red candle or its active stop. An unresolved runner
stays unresolved; no end-of-data liquidation is invented.

## Marketable-limit simulator

`execution_realism.py` is a standalone provider-neutral simulator. It consumes
complete top-of-book states ordered by receive time. A pre-arrival quote is
eligible only while fresh; halted states cannot fill. A fill occurs at the
displayed contra price only when it crosses the order's limit.

Displayed size is not treated as queue position. The simulator applies the
fixed participation haircut, floors to whole shares, consumes that state once,
and cancels any remainder. It gives no later queue credit and invents no hidden
liquidity. Unavailable, unfilled, halted, partial, and complete outcomes remain
distinct.

Two fixed scenarios must be reported on identical opportunities:

| Scenario | Arrival | Quote age | Cancel request | Cancel ack | Size haircut | Limit offset |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `l1-conservative-v0.1` | 100 ms | 100 ms | 250 ms after arrival | 100 ms | 25% | 5 ticks |
| `l1-stress-v0.1` | 250 ms | 50 ms | 150 ms after arrival | 150 ms | 10% | 2 ticks |

These values are engineering assumptions, not measured Alpaca latency or Ross
behavior. The better outcome cannot be selected. Broker acknowledgements,
venue routing, hidden liquidity, queue position, and market impact remain
unmodeled.

## Fees

The research schedule uses the Alpaca brokerage fee schedule effective July
20, 2026: SEC transaction fees on sells at `$0.0000206` per dollar, FINRA TAF
on sells at `$0.000195` per share capped at `$9.79` per trade, and CAT fees on
buys and sells at `$0.000003` per executed equity share. Each fee type is summed
by account-day and then rounded up to the nearest cent. The direct API equity
commission assumption is zero, but it must be reconciled against the actual
account agreement or statement before an economic claim.

Official references:

- [Alpaca Brokerage Fee Schedule](https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf)
- [SEC 2026 fee-rate advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2)
- [FINRA 2026 fee adjustment schedule](https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule)

## Authority and next gate

The simulator can be mechanically tested without buying data, but it cannot
create a portfolio result from missing quotes. Prospective integration requires
the registered account snapshot plus causal top-of-book and halt states. It may
not fall back to the frozen SIP print proxy when those inputs are absent.

Databento remains behind the metadata/cost gate. A successful quote still does
not authorize a download. Level 2 or tape-derived features remain inactive
until the separately registered completeness and reconstruction gates pass.

Files:

- Contract: `research/strategy/prospective-management-execution-v0.1.json`
- Simulator: `src/momentumbot/research/execution_realism.py`
- Tests: `tests/test_execution_realism.py`
