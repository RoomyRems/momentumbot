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

`prospective-opportunity-freeze-v0.1` now freezes the daily materialization
boundary that precedes that capture. It accepts only a hash-bound ledger of
causal Micro-v0.1 trigger decisions from the union of the registered general
and small-account strategy profiles. It emits every decision once before
account snapshots, scarcity, execution scenarios, fills, exits, later prices,
or retrospective inputs can select a row.

The provider-free workflow accepts an exact source artifact from a named
same-repository Actions run and retains the opportunity, request, and binding
manifests for 90 days. An explicit zero-opportunity date is valid; a missing
source is not silently converted to one.

`prospective-daily-scanner-micro-source-v0.1` now registers and implements the
missing upstream producer. Its 05:30 New York phase freezes a same-date current
Alpaca asset census and SEC ticker/CIK crosswalk before the 07:00 strategy
start. Its 10:20 phase checks out that artifact's exact code SHA, reconstructs
the complete union acquisition superset, retains the first qualifying minute
for each registered profile, and emits only unchanged Micro-v0.1 chart
triggers. Every decision is prefix-causal even though same-session provider
responses are reacquired after the scan window.

The producer fails closed on a missing prerequisite, provider failure,
rejected frozen membership symbol, incomplete scanner evidence, or missing SIP
tape for an eligible candidate. A genuinely complete zero-candidate or
zero-trigger date remains explicit. Successful source runs dispatch the frozen
opportunity materializer automatically. Registration made no provider read,
Databento quote/download, account read, or broker order; all runtime counts
remain zero before August 24.

`prospective-market-input-metadata-quote-v0.1` now registers the next unarmed
child. It validates the exact three-file opportunity-freeze bundle, recomputes
all content hashes, and re-derives every `mbp-1` and `status` request before a
future provider call can be authorized. A later authorization must bind the
daily source, opportunity, request, and freeze hashes plus the exact successful
same-repository Actions run and artifact.

The quote surface contains only Databento metadata `get_billable_size` and
`get_cost`, at most two calls per exact request. Push verification is
provider-free; an exact future authorization and manual workflow dispatch are
both required before the credential-bearing step exists at runtime. Reports
discard credentials and provider messages, refuse substitute requests, null
partial totals, treat zero billable size as unavailable, and grant no download
or broker authority. An explicit zero-opportunity date makes zero provider
calls and remains a successful not-applicable result.

This registration created no per-date authorization, loaded no Databento
credential, and ran no metadata quote. Its dynamic execution path remains
unarmed until a real prospective freeze is independently verified.

`prospective-market-input-acquisition-v0.1` now registers the separately
authorized child required after a successful exact metadata quote. Its dynamic
authorization binds the complete source/freeze/quote chain and sets hard cost
and byte ceilings equal to the successful quote totals. Registration itself
created no per-date authorization and made no provider call.

On a future first manual attempt, every exact request must be re-quoted before
the first download. Any provider error, incomplete or zero-size request, or
increase beyond either ceiling stops the run with zero time-series calls. After
a passing preflight, each unchanged request may be downloaded once in manifest
order; the first failure stops all later requests and no partial capture is
retained.

Temporary DBN files are deleted before reporting and can never enter the
Actions artifact. Only the minimal normalized receive-time L1/status capture
may persist after its dataset, schema, symbol, request-window, record-coverage,
and parent-hash checks all pass. Provider messages and credentials are removed,
and the result creates no account, scenario, broker, strategy, or runtime
authority. A valid zero-opportunity date makes zero provider calls and emits an
explicit empty capture.

`prospective-account-evaluation-v0.1` now preregisters the final panel
comparison before the first August 24 session. It binds the unchanged
Micro-v0.1 fingerprint, account integration contract, prospective management
and execution contract, ten fixed dates, two accounts, three behavioral
horizons, and both execution scenarios.

The evaluator reports all six account/cell results separately. Candidate
acquisition, account qualification and fill, explicit trade/skip agreement,
entry alignment, exit alignment, and activity remain separate components. If
the human evidence provides multiple entry or exit references, every
comparison is retained; the nearest reference is never selected. Unmentioned,
unclear, and unavailable actions are not converted into skips or trades, and
there is no best-cell field or weighted imitation score.

Portfolio statistics remain conditional. An account/cell receives financial
outputs only if all ten sessions exist, every runtime is complete, every
session is flat, and no required input is unavailable. Otherwise all financial
fields for that account/cell are null. The label-blind runtime must be frozen
and hashed before the separate retrospective label bundle can be opened. No
panel runtime, label, later outcome, P&L, provider call, credential, or broker
order was loaded by this registration.

## Active gates, in order

1. Preserve the completed cohort and all earlier real-data audits without
   rerunning their one-shot workflows.
2. Let the account snapshot workflow capture both paper accounts on each
   registered August 24–September 4 date. Keep both accounts flat and unreset.
3. Preserve each same-date pre-session membership/CIK prerequisite, exact-SHA
   daily scanner/Micro source, and automatically dispatched opportunity freeze.
   Treat a missing artifact or provider failure as a failed date, not a zero.
4. For each successful source date, verify the frozen opportunity materializer
   and its three-file hash chain before creating the deterministic metadata
   authorization for every exact `mbp-1` and `status` request pair.
5. Publish that per-date authorization as a separate child and run at most the
   first manual metadata-quote workflow attempt. Preserve a successful quote or
   the sanitized unavailable result without treating the quote as download
   authority.
6. Only after a successful exact quote, publish one separately parent-bound
   acquisition authorization. Run at most its first manual attempt, require all
   exact re-quotes to remain within the quote-bound ceilings before downloading,
   and retain only a complete normalized capture. Preserve missing or unknown
   quote and status inputs as unavailable without SIP-print substitution.
7. Populate all three horizons and both fixed execution scenarios together on
   identical opportunity inputs without scoring, ranking, or selecting a cell.
8. After all ten sessions, freeze the complete runtime and account-cell hash
   chain before opening structured retrospective labels. Run the preregistered
   component comparison and release portfolio fields only for complete, flat,
   fully available account-cells.
9. Complete a larger representative walk-forward before any policy-promotion,
   Ross-replication, or profitability interpretation.

## Still not ready

- No full portfolio backtest is complete.
- No prospective account-evaluation result exists; only its outcome-blind
  metric and completeness contract is registered.
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
- Prospective market-input metadata-quote registration tests are deterministic
  and provider-free; they cover exact-bundle re-derivation, zero dates,
  first-attempt authorization, sanitized partial failures, and the two-call
  ceiling without executing a provider quote.
- Prospective market-input acquisition registration tests are deterministic
  and provider-free; they cover successful-quote binding, hard re-quote
  ceilings, exact one-pass requests, first-failure termination, raw cleanup,
  sanitized failures, zero dates, and normalized capture reconciliation without
  executing a provider request.
- Prospective opportunity-freeze tests are deterministic, provider-free,
  preserve zero-opportunity dates, and reject account/outcome leakage.
- Prospective daily source tests are deterministic and provider-free; they
  enforce the two-phase timestamp/code binding, profile-union activation,
  trigger-only Micro boundary, write-once artifacts, and scheduled handoff.
- Prospective account-evaluation tests are deterministic and provider-free;
  they enforce exact six-cell candidate identity, account-scoped labels,
  runtime-before-label timestamps, full pairwise entry/exit references,
  recomputed component aggregates, write-once output, and null-only financial
  interpretation for incomplete, unavailable, or open account-cells.
- Complete provider-free repository suite: 845 tests passed on August 22, 2026.
