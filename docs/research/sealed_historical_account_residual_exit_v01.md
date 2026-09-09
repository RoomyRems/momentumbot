# Sealed historical bounded residual exit v0.1

This isolated child starts from verified checkpoint
`1bfb8e84491e3b1e24a642fc6c1df8675a223754`, tree
`63970e9046c7b6dfb01c277948b830c6f19680db`. Its immutable waiting parent is runtime
`7b0a0edd58ea285613a01047963bccb82a8a8df4ef6192f2437da222406d7edb`,
independently verified locally, on GitHub and from the downloaded original
four-member archive `10080992514`. The first cancelled hosted waiting attempt
and all prior failures remain preserved.

## Single registered hypothesis

After the first terminal exit's cancellation acknowledgement, one additional
terminal attempt may manage the confirmed remaining shares. This is the
smallest uniform extension of the original one-terminal-attempt ceiling: no
per-symbol retry budgets, outcome-dependent escalation or target resubmission.
The bound is one target and at most two terminal orders per confirmed entry.
This does not assume that the additional attempt will finish the account path.

- Authorize a replacement only after the frozen reducer has exposed an actual
  terminal cancellation acknowledgement with positive confirmed shares left.
  A pending private execution result cannot authorize it. Partial target fills
  alone never receive replacement authority.
- Keep the original `full_exit_attempted` flag set. Preserve the prior submitted
  intent, order ID and exact acknowledged cancellation as the replacement's
  immutable context. Do not reset the consumed-liquidity set.
- Propose on the first subsequent eligible SIP print strictly later than the
  acknowledgement. Equal-time prints precede feedback and cannot submit a
  replacement. Quotes do not create additional scheduler events.
- Request all and only the current confirmed unreserved shares. Keep the
  terminal signal latched, with the existing stop/account-risk/red priority.
  A later stop may supersede an earlier red-candle or account-risk reason.
- Use the frozen current reference, marketable-limit offset, arrival latency,
  participation, fill selection and cancellation mechanics. Missing/stale or
  known halted references use the unchanged waiting parent. Unknown status,
  malformed evidence or a changed tape still fail closed.
- Spend the single additional attempt only when an actual order is submitted.
  Waiting spends no attempt and reserves no shares. Preserve the original
  signal and current SIP/native quote witnesses through any wait.
- The original 550 ms capture tail plus the final exclusive nanosecond must
  still fit the opportunity window. Otherwise preserve the shares and any
  outstanding intent. No extra source request, window extension or synthetic
  liquidation is permitted.
- After the second terminal cancellation, a positive remainder is an explicit
  exhausted-budget state. There is no third terminal attempt. Any later session
  remains blocked unless the inherited account-continuity requirements pass.

The account retains a chained residual journal after position release and
re-entry: acknowledged readiness, proposal, actual submission, expiry or budget
exhaustion. No-residual paths preserve exact parent objects. Original entry
sizing, candidate order, campaign limits, seeds, fees and decimal risk are
unchanged. Alternative account/scenario/horizon paths are never pooled.

## Verification boundary

The independent stdlib checker reconstructs acknowledgement authority, remaining
shares, the first eligible post-ack print, terminal reason priority and the
replacement's linkage to the original order and any waiting episode. It rejects
omitted authority, changed cancellation quantities, skipped eligible prints and
third terminal orders. Whole-tape source identity and one-use liquidity remain
independently checked.

Completed sessions before the first residual authority must match the parent
exactly. In the first affected session, events through the original cancellation
acknowledgement must match exactly. Later capacity decisions may legitimately
change after a confirmed replacement fill; a two-opportunity regression test
checks this boundary explicitly.

The frozen account arithmetic checker is copied without semantic changes. The
chronology checker changes only its terminal-attempt count from one to two;
the added residual checker must authorize the second. AST regression tests
verify these exact deltas and unchanged session-finisher arithmetic. Waiting
verification retains the original logic, adding the independently checked
residual context to its signal identity. This is not a second fill simulator.

`build_sealed_historical_account_residual_exit_v01.py --build/--verify` is
metadata-only and provider-free. A historical `--replay` requires the separately
committed registration hash, all five unchanged original archives, a fresh
external output directory and an exclusive attempt receipt before source access.
The dedicated GitHub workflow has a preregistered 120 minute job budget, checks
the frozen registration and focused tests in both modes, and always retains
available outputs and failed-attempt evidence. It does not rerun the parent.

All 12 paths, 360 session slots, 744 opportunity references and 162 unavailable
references remain mandatory. Code and registration must be published before
historical execution. A runtime failure or newly exposed blocker is recorded
without changing the consumed implementation. Exact local/hosted byte comparison
and independent rechecking of the downloaded artifact precede completion claims.

The account backtest, financial evaluation, overnight execution, retrospective
Ross comparison and promotion remain closed. Ross attachments remain unopened.

## Current stage

All 2,289 local tests passed with zero skips (277.269 seconds). The 148 focused
tests passed normally (70.019 seconds) and optimized (73.955 seconds), including
36 new residual-exit tests. Static checks found no undefined globals in the
three entrypoints and no production implementation imports in the checker.
The final registration freeze is
`33ced4d6e2069f36a277b3b2025f38e07e2d7a3e9eeecd031345400ed6b54dae`.
All 265 frozen parent files and five implementation files verify unchanged.

The [implementation audit](../../research/data-audits/sealed-historical-account-residual-exit-v0.1-implementation-verification.json)
records exact test-log commitments and resolved synthetic diagnostics before
the freeze. No original-source replay of this child has been run at this
checkpoint. The next gate is the registered original-source replay and direct
local/hosted archive comparison with independent verification of the result.
