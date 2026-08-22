# Microstructure behavioral/execution bridge v0.1

## Purpose

This child carries the verified behavioral-cohort aggregate into the already
registered prospective execution assumptions without turning the aggregate
into a signal. It is a readiness matrix, not a backtest and not a trading rule.

The bridge binds the permanent behavioral-cohort v0.2 success audit and
`prospective-management-execution-v0.1`. It consumes no provider data, creates
no broker order, and cannot alter Micro-v0.1, account sizing, risk, management,
or execution assumptions.

## Complete matrix

Every registered behavioral horizon is crossed with both frozen execution
scenarios:

| Behavioral horizon | Conservative L1 | Stress L1 |
| ---: | --- | --- |
| 1 second | pending causal quote/halt inputs | pending causal quote/halt inputs |
| 5 seconds | pending causal quote/halt inputs | pending causal quote/halt inputs |
| 10 seconds | pending causal quote/halt inputs | pending causal quote/halt inputs |

The two cells at a given horizon receive the same sanitized aggregate evidence.
The bridge does not infer per-opportunity values, score a cell, rank a cell, or
select the better result. Unavailable data remains unavailable.

## Input and authority boundary

Allowed now:

- the frozen cohort identity and opportunity count;
- aggregate direction and unavailable counts by horizon;
- exact comparison and artifact digests; and
- the two already frozen execution-assumption records.

Prohibited now:

- raw MBO records or per-opportunity feature values;
- Ross actions, labels, recaps, later prices, or P&L;
- a preferred metric, direction, horizon, scenario, threshold, or exception;
- provider spend or another one-shot workflow;
- paper or live orders; and
- runtime authority or policy promotion.

## Next gate

Prospective execution cells can be populated only after the registered account
snapshot and causal top-of-book and halt-state inputs exist. Both scenarios
must use identical opportunity inputs. Missing inputs remain pending or
unavailable; the frozen SIP print proxy cannot be substituted.

Files:

- Contract: `research/strategy/microstructure-behavioral-execution-bridge-v0.1.json`
- Mechanics: `src/momentumbot/research/microstructure_behavioral_execution_bridge.py`
- Tests: `tests/test_microstructure_behavioral_execution_bridge.py`
