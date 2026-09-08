# Sealed historical account exit waiting v0.1

This isolated child starts from verified checkpoint
`d2266c8cf151a55f705c06c59986eafc590f0422`, tree
`514af4067fae35cecda2ae2682eca5ccd13cfb06`, and decimal-risk runtime
`5986950aab81652970a6318d93b7a6dd3b4b3384b8aa4a92d8578e3e985398e0`.
The prior archive comparison is completed in the additive
`sealed-historical-account-risk-projection-v0.1-archive-comparison.json` audit;
the earlier disconnection record is preserved.

The single hypothesis is that a causally triggered but unsubmitted exit can
wait for a fresh reference within the original opportunity. This is an
execution-mechanics experiment. It does not alter entry selection or assess
profitability. Ross transcripts and retrospective labels remain unopened.

## Registered mechanics

- Reconsider a waiting exit only on subsequent eligible SIP prints, in the
  original timestamp and record order. Quote arrivals do not create new
  scheduler events. Use only a reference timestamp at or before that print,
  with the unchanged inclusive 100 ms freshness bound.
- Keep the original signal and its exact trade/bar witnesses. An unsubmitted
  target stays latched while waiting. At each eligible print the original stop
  priority remains active; account-risk flattening and completed first-red
  signals can supersede a target. A stop remains higher priority.
- Waiting reserves no shares and consumes no order attempt. The one-target and
  one-terminal ceilings are consumed only when the frozen submission routine
  creates an order. Delayed intents bind both their current print and the
  original/effective signal. No resubmission of a filled, partial or cancelled
  order is added.
- Missing/stale or known halted references can wait. Malformed evidence,
  changed tape identities, unknown/incomplete status and other errors retain
  the original fail-closed behavior. The frozen capture still requires status
  coverage through the execution tail; future prices never select a decision.
- Stop reconsidering when the existing 550 ms capture tail plus the exclusive
  final nanosecond cannot fit the original window. Preserve the outstanding
  intent, shares and downstream carry blocker. There is no synthetic end-of-
  window liquidation or extension of a request.

The full native tape is validated before constructing an immutable reference
index. The index changes lookup cost, not eligibility. Actual submission still
revalidates the full original tape through the frozen adapter and uses its
unchanged fill, latency, participation, limit-price, cancellation and one-use
liquidity mechanics. Decimal public risk projection is inherited unchanged.

An optional account journal records wait start, reason supersession, actual
submission and expiry. It survives position release and re-entry. Paths that
do not wait retain byte-identical parent path objects in synthetic parity
tests. The nested original component identifiers remain unchanged; the outer
child registration binds the isolated mechanics and added evidence.

## Verification and execution

`build_sealed_historical_account_exit_waiting_v01.py --build/--verify` is
metadata-only and provider-free. `--replay` requires an independent registration
commitment, all five byte-pinned original archives and a new external output
directory. An exclusive attempt receipt is written before original source
access. Failed attempts and outputs are never overwritten.

The stdlib independent checker retains the frozen account/chronology verifier
and exact rational open-risk checks. It additionally reconstructs waiting
signals, stop/red priority, native reference witnesses and the first eligible
fresh print directly from the immutable management and exit archives. It
checks unconsumed attempts, exact delayed order identities, original window
expiry and preserved failed proposals. It is not an independent second fill
simulator. The first waiting signal and all preceding scheduler events must
match each original failed parent path exactly.

All 12 alternative paths, 360 sessions, 744 opportunity references and 162
unavailable references remain mandatory. Once-only $30,000/$2,000 seeds,
original source windows, strategy, fees and risk limits remain frozen.
Financial evaluation, account-backtest completion, overnight execution,
retrospective comparison and policy promotion remain closed. Any newly exposed
input or execution blocker requires its own isolated registration; outcomes
must not be used to patch this child.
