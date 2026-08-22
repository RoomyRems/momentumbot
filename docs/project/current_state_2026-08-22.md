# Current project state — 2026-08-22

This checkpoint extends `docs/project/current_state_2026-08-21.md`. Earlier
checkpoints remain immutable provenance. This child controls only for work
completed and independently verified after the August 21 checkpoint.

## Plain-English position

The repaired behavioral-cohort attempt succeeded on its first and only GitHub
Actions attempt. All five frozen `XNAS.ITCH` MBO requests completed, covering
the same 10 accepted-panel opportunities, seven symbol-dates, and five trading
dates that were registered before any behavioral values were opened.

The result is engineering evidence. It says the label-blind mechanics executed
deterministically and produced a sanitized aggregate across every frozen one-,
five-, and ten-second window. It does not select a horizon, metric, threshold,
hidden-order label, execution scenario, strategy rule, or policy. It contains
no per-opportunity feature values, Ross labels, later prices, P&L, or broker
authority.

## Verified behavioral-cohort success

- Workflow `32575593240`, attempt 1, completed successfully at execution head
  `0687093a778bd6ac0973889e788886df8cd48cbf`.
- The sole authorization was a direct child of
  `fed2b11c9a55ad45e340d80a4dbee8326ae193a3`; every workflow step succeeded.
- All five requests were quoted before the first download. The aggregate quote
  was `$0.078219142556` and `69,989,304` billable bytes, below the fixed `$0.25`
  and `225,000,000`-byte ceilings. Actual billing remains unknown.
- The five downloads contained 1,096,506 records and 864,767 atomic
  per-instrument events. Every request matched its frozen metadata and replayed
  exactly in an independent feature engine.
- The cohort aggregate contains 10 opportunities and all three registered
  horizons together. Its exact comparison-sequence digest is
  `1b6c228496669c780813e51c08510ec900ed7d0c9068b22bbe007368e12ee5d4`.
- No retry, partial-cohort substitution, raw-data persistence, raw upload,
  feature-value persistence, retrospective input, threshold selection, broker
  change, strategy change, or runtime authority occurred.
- The permanent success audit is
  `research/data-audits/databento-microstructure-behavioral-cohort-v0.2-run-32575593240-success-2026-08-22.json`.

## Consumed authority

The v0.2 execution authorization and workflow attempt are consumed. Workflow
`32575593240` must not be rerun, and its authorization file must not be reused
to obtain more data. The raw DBN files were deleted by the workflow; the only
retained provider-derived artifact is the sanitized aggregate bound by the
permanent audit.

## New unarmed development

`microstructure-behavioral-execution-bridge-v0.1` freezes the threshold-free
handoff from the sanitized cohort aggregate to the already registered
prospective execution assumptions. It creates the complete six-cell readiness
matrix: all one-, five-, and ten-second horizons crossed with both the fixed
conservative and stress scenarios.

Every cell is pending the same causal top-of-book, halt-state, and registered
account inputs. The bridge carries aggregate direction and unavailable counts,
not per-opportunity feature values. It cannot score, rank, select, download,
trade, or create runtime authority, and it authorizes zero Databento credit.

`prospective-market-input-capture-v0.1` now freezes the missing provider-neutral
capture mechanics before the prospective panel opens. After a registered
date's label-blind opportunities are frozen, it derives exactly one `mbp-1`
and one `status` request per symbol-date from fixed receive-time windows. It
preserves explicit halt and unknown states, reconciles every acquired record
to its frozen request, and refuses the SIP print proxy as a substitute.

The capture registration makes no provider call and authorizes zero Databento
credit. `XNAS.ITCH` remains explicitly single-venue Nasdaq evidence rather than
a consolidated NBBO or broker-fill claim.

## Active gates, in order

1. Preserve the completed cohort and all earlier real-data audits without
   rerunning their one-shot workflows.
2. Let the account snapshot workflow capture both paper accounts on each
   registered August 24–September 4 date. Keep both accounts flat and unreset.
3. Freeze each date's label-blind opportunity manifest before deriving or
   quoting its exact `mbp-1` and `status` request pair per symbol-date.
4. Require separate parent-bound authority for metadata quotes and later for
   any download. Preserve missing or unknown quote and status inputs as
   unavailable without SIP-print substitution.
5. Populate all three horizons and both fixed execution scenarios together on
   identical opportunity inputs without scoring, ranking, or selecting a cell.
6. Complete the prospective panel and a larger representative walk-forward
   before any policy-promotion or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- No feature horizon or threshold is selected.
- The behavioral result is a 10-opportunity accepted-panel aggregate, not a
  representative multi-regime validation or a profitability result.
- No consolidated multi-venue book, calibrated queue/impact model, live
  capture/reconnect path, or broker integration exists.
- AI remains shadow-only, paper accounts remain research-only, and live-money
  trading is out of scope.

## Verification

- Behavioral cohort v0.2 success-audit tests: deterministic and provider-free.
- Behavioral cohort v0.2 execution tests remain provider-free after the
  consumed run.
- Prospective market-input capture registration tests are deterministic,
  provider-free, and require zero credentials.
- Complete repository suite is required before this checkpoint is published.
