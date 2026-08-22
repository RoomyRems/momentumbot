# Prospective market-input capture v0.1

## Purpose

This child freezes the missing causal market-input path for the registered
August 24–September 4 account panel. It accepts only a future hash-bound,
label-blind opportunity manifest and derives the exact receive-time quote and
status requests needed by the already frozen prospective execution simulator.

The frozen parent is the threshold-free behavioral/execution bridge at commit
`392fb0d1fff322bc6ff38d5e416ff9e2b8926fab`. The capture cannot alter
Micro-v0.1, the two execution scenarios, management, account sizing, risk, or
the behavioral aggregate.

## Frozen source scope

The registered source is Databento Historical API dataset `XNAS.ITCH`, schemas
`mbp-1` and `status`, using `ts_recv` as the causal clock. `mbp-1` carries every
Nasdaq TotalView top-of-book update; `status` carries trading, halt, pause, and
unknown states. This is a Nasdaq single-venue view, not consolidated NBBO and
not a claim about an Alpaca-routed fill.

For each registered symbol-date, the offline request manifest contains exactly
two rows:

- `mbp-1` begins 100 milliseconds before that symbol's earliest frozen
  decision and ends 550 milliseconds after its latest decision, plus a
  one-nanosecond exclusive-end pad; and
- `status` begins at midnight UTC on the registered date and shares the same
  exclusive end.

The 100-millisecond lookback covers the larger of the two frozen maximum quote
ages. The 550-millisecond tail covers the longest decision-to-arrival,
cancel-request, and cancel-ack sequence. Both fixed execution scenarios receive
identical market inputs.

## Fail-closed capture mechanics

The implementation validates the opportunity manifest before it can derive a
request. Only opportunity ID, date, symbol, decision timestamp, and frozen
runtime hash are accepted. Ross actions, labels, recaps, later prices, P&L,
outcomes, chosen horizons, and chosen scenarios are rejected even if a caller
rehashes the manifest.

Already acquired records must reconcile exactly to the frozen request rows and
their provider record counts. Quote and status records remain in receive-time
order. A quote is usable only when both sides have positive prices and sizes
and the book is neither locked nor crossed. Missing initial status or the
provider's unknown `~` trading state keeps that opportunity unavailable; the
capture never assumes that trading is active. Status evidence is isolated to
the same registered symbol-date, so an earlier session cannot seed a later
session. Original provider order breaks ties among status records. Because the
separate quote and status schemas provide no cross-schema ordering at an equal
`ts_recv`, a quote at the exact receive timestamp of a status event is unusable.
A valid capture converts directly to the existing `TopOfBookEvent` simulator
input while retaining status changes as separate causal evidence.

## Authority boundary

This registration is unarmed. It includes no provider client, credential,
workflow, metadata quote, time-series download, broker call, or order method.
It authorizes `$0` of Databento credit and creates no paper, live, runtime,
selection, promotion, or profitability authority. The consumed behavioral
cohort workflow remains consumed and must not be rerun.

## Next gate

After a registered date's label-blind runtime opportunities are frozen, build
and freeze the exact two-schema request manifest. A separate authorization may
then run metadata-only availability and cost quotes. A quote does not authorize
a download; any bounded acquisition requires another explicit, parent-bound
authorization.

Files:

- Contract: `research/strategy/prospective-market-input-capture-v0.1.json`
- Mechanics: `src/momentumbot/research/prospective_market_input_capture.py`
- Tests: `tests/test_prospective_market_input_capture.py`
