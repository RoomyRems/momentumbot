# MomentumBot agent routing

MomentumBot is a research-first, historically causal approximation of Ross Cameron's small-cap momentum process. The active branch is `phase-3-historical-snapshot`; no live-money trading is in scope.

## Non-negotiable boundaries

- Runtime order is market data -> label-blind replay -> frozen artifact -> retrospective Ross comparison.
- Never expose Ross fills, actions, recap labels or later price outcomes to runtime reconstruction.
- Do not tune thresholds case by case or promote a policy from the diagnostic seed suite.
- Measurable facts, timestamps, order mechanics and every risk limit remain deterministic.
- AI begins shadow-only, uses time-causal structured inputs, may abstain, cannot submit orders and cannot increase deterministic risk.
- Preserve failed experiments and their provenance.
- Interpret interim financial results as evidence about the components actually integrated. The intended project includes crucial discretionary/context components; an incomplete deterministic baseline does not settle the full hybrid strategy's edge. Completing the hybrid remains a research goal, not a profitability guarantee.
- Transcripts may clarify offline, versioned strategy design. Keep recap actions, fills, later outcomes and evaluation-case narratives out of replay and runtime AI prompts; do not use registered evaluation cases to tune a frozen experiment.

## Route by task

| Task | Open first | Source of truth |
|---|---|---|
| Integrated repaired census capture | `docs/research/census_repaired_capture.md` | same-code CI-gated one-pass capture, safe failure retention, frozen repaired protocol in collector and verifier, automatic original-ZIP replay |
| Census provider-order repair | `docs/research/census_order_repair.md` | verified mixed-case ordering fault, repaired pure projection/state, unchanged identity/schema/cursor rules and remaining collector/verifier wiring |
| Census rejection diagnostic and streamlined delivery | `docs/research/census_payload_diagnostic.md` | one exact request after same-commit full CI, independent durable consumption, safe raw retention, fixed rejection reason and no runtime promotion |
| Early-pullback consumed census failure and public pricing | `docs/research/early_pullback_census_hosted_v02.md` | verified two-request HTTP-200 payload rejection, unavailable rejected body, permanent consumption, unknown billing and a separate diagnostic gate |
| Early-pullback census hosted execution safeguards | `docs/research/early_pullback_census_hosted_v01.md` | unarmed sole-file execution launcher, explicit owner approval/entitlement, create-only consumption and independent preflight pin before credential reads |
| Early-pullback bounded census capture and archive verification | `docs/research/early_pullback_census_v01.md` | unarmed one-pass adapter, 30-date strict exhaustion, raw-byte and sanitized receipt retention, independently pinned archive replay and closed origin/identity/runtime gates |
| Early-pullback scheduled calendar and capture planning | `docs/research/early_pullback_capture_plan_v01.md` | official scheduled-session projection, unarmed 31-root / 601-maximum census plan, strict pagination mechanics and explicit unresolved complete-capture/cost gates |
| Early-pullback provider availability and transport provenance | `docs/research/early_pullback_provider_check_v01.md` | exact four requests, tested sole-file execution child, durable consumption before credentials, bounded sanitized receipts and explicit remaining historical source gates |
| Early-pullback new-panel account execution | `docs/research/early_pullback_panel_accounts_v01.md` | isolated 2026 account and fee-date context, 24 independent synthetic paths, exact carry, unchanged engine mechanics and explicit remaining provider/capture gates |
| Early-pullback new-panel source catalogue | `docs/research/early_pullback_panel_sources_v01.md` | fixed new-date identities, byte-verified synthetic archives, frozen scanner/normalization/Micro reconstruction, explicit provider-provenance and account-context limits |
| Early-pullback source binding and paired mechanics | `docs/research/early_pullback_paired_adapter_v01.md` | normalized causal trigger reconstruction, independent synthetic account arms, immutable old-date guards, exact unarmed new-panel probe plan and full-hybrid interpretation |
| Early-pullback selection experiment | `docs/research/early_pullback_selection_v01.md` | first-two causal shadow gate, pinned new date inventory, paired evaluation plan, unarmed source/account integration and unchanged losing parent |
| Historical setup, stop and source audit | `docs/research/sealed_historical_setup_stop_audit_v01.md` | original causal-prefix reconstruction, unchanged Micro plans and stops, descriptive geometry and quote alignment, all fixed account alternatives retained |
| Historical losses by entry, size and exit | `docs/research/sealed_historical_loss_attribution_v01.md` | fixed conditional results, exact price/fee bridges, recorded exit reasons and order authority, all original decisions retained, no causal policy-change claim |
| Conditional historical account performance | `docs/research/sealed_historical_account_conditional_evaluation_v01.md` | unchanged hosted fills, explicit strict-quote withholds, all 12 paths and 30 dates, exact net accounting and preserved losing baseline |
| Historical entry-reference evidence and observation policy | `docs/research/sealed_historical_entry_reference_evidence_v01.md` | exact original stream evidence, explicit strict observed-update entry gate, unchanged unavailable history and separate conditional evaluation scope |
| Hosted historical acceptance and input completeness | `docs/research/sealed_historical_account_hosted_acceptance_v01.md` | user-approved hosted-only acceptance, unchanged successful replay, exact archived results, preserved local interruption and explicit unavailable-input history |
| Historical terminal exit continuation | `docs/research/sealed_historical_account_terminal_continuation_v01.md` | immutable two-order parent prefix, acknowledged sequential continuation within original windows, exact account arithmetic and independent continuation authority checks |
| Historical residual runtime reproduction | `docs/research/sealed_historical_account_residual_exit_reproduction_v01.md` | separate preserved local/hosted attempts, unchanged producer and corrected verifier, exact original runtime bytes and retained incomplete states |
| Historical residual cancellation-status correction | `docs/research/sealed_historical_account_residual_exit_status_verification_v01.md` | verified saved runtime with identical local/hosted child reports, unchanged original checks, retained failure and separate runtime-reproduction gap |
| Historical residual cancellation-check failure | `docs/research/sealed_historical_account_residual_exit_cancellation_diagnostic_v01.md` | preserved failed checker, source-proven no-quote status, diagnostic-only regression and separate verifier-correction gate |
| Historical bounded residual exit | `docs/research/sealed_historical_account_residual_exit_v01.md` | one additional terminal order after acknowledged cancellation, strict causal print/window bounds, retained liquidity identity and independent residual authority checks |
| Historical causal exit waiting | `docs/research/sealed_historical_account_exit_waiting_v01.md` | isolated unsubmitted-exit waiting, original windows and attempt ceilings, immutable parent fills/risk and independent source-witness verification |
| Historical exact open-risk projection | `docs/research/sealed_historical_account_risk_projection_v01.md` | isolated public decimal risk projection, unchanged internal execution, strict failed-parent parity and frozen independent account checks |
| Historical original account replay | `docs/research/sealed_historical_account_replay_v01.md` | verified original source bindings, frozen chronological account mechanics, all original slots and explicit failed or blocked carry with financial metrics closed |
| Historical original source binding | `docs/research/sealed_historical_source_binding_v01.md` | exact five original archives, activation-row candidate priority, all original context/stream identities and explicit unavailable carry dependencies with account execution closed |
| Current checkpoint / next gate | `docs/project/current_state_2026-08-31.md` | immutable parent checkpoints plus linked frozen manifests and audits |
| Sealed historical walk-forward | `docs/research/sealed_historical_walk_forward_v01.md` | opaque corpus commitment, prior-date exclusions, deterministic 30-session selector and provider-free registration audit |
| Historical execution/status input plan | `docs/research/sealed_historical_execution_inputs_v01.md` | exact completed Micro checkpoint, 109 frozen decisions, 90 unquoted requests, and independent input/quote gates |
| Historical execution-input metadata quote | `docs/research/sealed_historical_execution_quote_v01.md` | exact 90-request plan, pinned metadata-only transport, parent-bound execution child and durable one-shot consumption |
| Historical execution/status acquisition | `docs/research/sealed_historical_execution_acquisition_v01.md` | independently verified quote, unchanged exact requests and normalization, hard re-quote ceilings and separate one-shot consumption |
| Historical execution/status acquisition v0.2 | `docs/research/sealed_historical_execution_acquisition_v02.md` | frozen record-order adapter, unchanged 90 requests/ceilings, durable separate consumption, complete byte verification and retained partial evidence |
| Historical remaining execution inputs v0.3 | `docs/research/sealed_historical_execution_acquisition_v03.md` | immutable 24 completed tapes, diagnosed unavailable JVA, exact 65-request suffix, separate consumption and explicit unavailable receipts |
| Historical opportunity input availability | `docs/research/sealed_historical_execution_availability_v01.md` | exact verified v0.3 artifact chain, unchanged 109 opportunities, frozen quote/status mechanics, explicit unavailable inputs and provider-free window composition |
| Historical account and management inputs | `docs/research/sealed_historical_account_inputs_v01.md` | user-approved $30,000/$2,000 once-only seeds, 360 session dependencies, exact prior-state handoff, 56 frozen management windows and retained unavailable inputs |
| Historical management source reuse | `docs/research/sealed_historical_management_reuse_v01.md` | exact retained SIP/minute ZIPs, complete file/tape verification, unchanged normalization, 51 covered windows and ten exact missing tail resources |
| Historical missing management capture | `docs/research/sealed_historical_management_capture_v01.md` | exact ten-resource tails, unchanged normalization, exhausted empty receipts, no-retry bounded transport, separate durable consumption and complete artifact verification |
| Historical complete management inputs | `docs/research/sealed_historical_management_inputs_v01.md` | verified original prefixes plus exact captured tails, byte-identical tapes, original ordinal lineage, opportunity-bound reader and closed account/execution gates |
| Historical causal management mechanics | `docs/research/sealed_historical_management_projection_v01.md` | synthetic parity with frozen external-fill SIP management, completed-bar timing, exact lineage and conditional executable-exit dependencies with historical runtime blocked |
| Historical entry binding and fill feedback | `docs/research/sealed_historical_management_fill_feedback_v01.md` | recomputed single-entry evidence, whole-share reservations, confirmed-fill stop feedback, bounded executable sell attempts and synthetic verification with historical runner/account gates closed |
| Historical position runner and exit-input scope | `docs/research/sealed_historical_management_runner_v01.md` | causal streaming scheduler, frozen context resolution, 41 common source pairs, exact XAGE reuse candidate and 80 new bounded requests with historical activation and account dependencies unresolved |
| Historical management exit reuse and quote | `docs/research/sealed_historical_management_exit_quote_v01.md` | exact retained XAGE bytes, unchanged 80-request suffix, pinned metadata transport, parent-bound execution and separate durable consumption |
| Historical management exit acquisition | `docs/research/sealed_historical_management_exit_acquisition_v01.md` | verified 80-request quote and individual ceilings, unchanged native/order mechanics, retained unavailable/failed evidence and separate unarmed one-shot consumption |
| Historical complete management exit inputs | `docs/research/sealed_historical_management_exit_inputs_v01.md` | all 82 byte-identical original sources, stable execution payload identities, original opportunity bounds, explicit unavailable entries and closed historical account/runtime gates |
| Historical campaign re-entry and account continuation | `docs/research/sealed_historical_account_continuity_v01.md` | frozen two-entry campaigns, exact per-entry basis and campaign totals, replay-verified checkpoints within original windows and explicit expired-window/historical dependencies |
| Historical chronological account scheduling | `docs/research/sealed_historical_account_scheduler_v01.md` | frozen parent with one causal intraday clock, private entry outcomes, scarcity, net-risk exits and preserved incomplete state |
| Historical causal account valuation | `docs/research/sealed_historical_account_valuation_v01.md` | replay-verified preceding state, fixed session-start bid marks, explicit share-unit continuity, preserved orders and closed continuous-execution/historical gates |
| Historical account-state producer and session continuity | `docs/research/sealed_historical_account_state_producer_v01.md` | once-only seeds, externally committed source-program replay, exact flat-cash continuity, preserved incomplete state and closed valuation/integration/historical gates |
| Historical fees and confirmed-fill reconciliation | `docs/research/sealed_historical_management_fee_reconciliation_v01.md` | explicit 2025 regulatory/customer-fee assumptions, persistent account-day accrual, causal confirmed sells, exact net guard checks and closed producer/valuation/runtime gates |
| Historical execution-input normalization diagnostic | `docs/research/sealed_historical_execution_diagnostic_v01.md` | immutable failed v0.1, single exact GITS request, bounded diagnostic projection, unchanged validator and separate one-shot consumption |
| Historical empty execution input | `docs/research/sealed_historical_execution_empty_diagnostic_v01.md` | immutable v0.2 JVA failure, exact 650 ms request, native DBN versus mapped evidence, and separate three-call diagnostic |
| Historical quote record ordering | `docs/research/sealed_historical_record_order_v01.md` | verified GITS diagnostic, lossless native fields plus original record ordinal, frozen capture/execution equivalence and separate future acquisition gate |
| Sealed historical provider availability | `docs/research/sealed_historical_provider_availability_v02.md` | permanent v0.1 routing failure, one-call main-credential child repair and unchanged acquisition boundary |
| Sealed historical source acquisition | `docs/research/sealed_historical_source_acquisition_v02.md` | permanent v0.1 request-budget failure, request-ceiling-only v0.2 child and unchanged causal acquisition graph |
| Sealed historical scanner runtime failure | `docs/research/sealed_historical_scanner_runtime_v01_failure.md` | exact provider-free replay, mixed price-basis diagnosis and blocked normalization-only child gate |
| Sealed historical normalization repair | `docs/research/sealed_historical_source_acquisition_v03.md` | split/split gain and rank, raw price/volume, immutable v0.2 success/failure parents and one-shot child authority |
| Sealed historical source recovery | `docs/research/sealed_historical_source_acquisition_v13.md` | permanent v0.12 missing-import failure, exact v0.10 checkpoint, mandatory end-to-end verification, non-final intermediate retention, and unarmed provider-free v0.13 final-freeze boundary |
| Runtime and hybrid architecture | `docs/architecture.md` | executable code under `src/momentumbot/` |
| Current Ross-derived policy | `docs/strategy/current_rulebook.md` | `research/rules/current_rules.json` and policy code |
| Strategy/discretion coverage | `docs/research/strategy_discretion_coverage_v02.md` | immutable v0.1 parent, versioned v0.2 delta and `strategy_coverage_v02.py` |
| Historical-data requirements | `docs/DATA_REQUIREMENTS.md` | validators/loaders under `src/momentumbot/` |
| Level 2/tape feasibility | `docs/research/level2_tape_feasibility_v01.md` | `research/strategy/level2-tape-feasibility-v0.1.json` and `microstructure_contract.py` |
| Databento metadata/cost gate | `docs/research/databento_metadata_quote_v01.md` | child quote contract, `databento_quote.py` and quote workflow |
| Databento bounded acquisition | `docs/research/databento_microstructure_smoke_acquisition_v01.md` | hash-bound smoke contract, `databento_smoke.py` and one-shot acquisition workflow |
| Databento MBO reset repair | `docs/research/databento_microstructure_smoke_acquisition_v02.md` | frozen v0.1 failure, v0.2 child contract, `databento_smoke_v02.py` and one-shot repair workflow |
| Databento reset replication | `docs/research/databento_microstructure_replication_v03.md` | verified v0.2 success, unchanged reset engine, three-case child contract and one-shot replication workflow |
| Microstructure feature mechanics | `docs/research/microstructure_feature_mechanics_v01.md` | v0.3 success audit, threshold-free feature registration and `microstructure_features.py` |
| Databento feature diagnostic | `docs/research/databento_microstructure_feature_diagnostic_v03_success.md` | frozen v0.3 registration plus permanent verified INTJ success audit |
| Databento remaining-case feature coverage | `docs/research/databento_microstructure_feature_coverage_v02.md` | verified INTJ/EQPT parents, unarmed repaired AMC/GMM contract and authorization-only workflow |
| Databento Fill/Cancel identity repair | `docs/research/databento_microstructure_fill_cancel_repair_v01.md` | verified aggregate EQPT classifier audit, unarmed repair contract and deterministic pairing mechanics |
| Databento EQPT repaired feature replay | `docs/research/databento_microstructure_fill_cancel_repaired_feature_v01.md` | verified one-shot EQPT success audit, frozen repair and exact-replay evidence |
| Databento behavioral cohort v0.2 | `docs/research/databento_microstructure_behavioral_cohort_v02_success.md` | immutable v0.1 safe failure, consumed v0.2 success audit and repaired authorization-only harness |
| Behavioral/execution shadow bridge | `docs/research/microstructure_behavioral_execution_bridge_v01.md` | consumed cohort success audit, frozen prospective execution assumptions and threshold-free readiness matrix |
| Prospective daily scanner/Micro source | `docs/research/prospective_daily_scanner_micro_source_v01.md` | two-phase current membership prerequisite, profile-union scanner, causal Micro trigger source and scheduled handoff |
| Prospective opportunity freeze | `docs/research/prospective_opportunity_freeze_v01.md` | causal Micro decision-source boundary, profile-union identity, provider-free daily materializer and exact request handoff |
| Prospective market-input capture | `docs/research/prospective_market_input_capture_v01.md` | frozen label-blind opportunity identity, exact unarmed `XNAS.ITCH` `mbp-1`/`status` request derivation and fail-closed capture mechanics |
| Prospective market-input metadata quote | `docs/research/prospective_market_input_metadata_quote_v01.md` | unarmed exact-bundle validator, dynamic parent-bound authorization, two-method metadata quote and sanitized report workflow |
| Prospective market-input acquisition | `docs/research/prospective_market_input_acquisition_v01.md` | successful-quote-bound dynamic authorization, hard re-quote ceilings, exact one-pass downloads, raw cleanup and minimal normalized capture |
| Prospective daily account runtime | `docs/research/prospective_daily_account_runtime_v01.md` | provider-free four-parent composer, exact 12-cell daily hash chain, account scarcity and explicit open-management boundary |
| Prospective management/execution | `docs/research/prospective_management_execution_v01.md` | child contract and `execution_realism.py` |
| Prospective account evaluation | `docs/research/prospective_account_evaluation_v01.md` | preregistered six-cell component metrics, runtime-before-label join and flat-complete conditional portfolio gate |
| New research experiment | `docs/research/experiment_contract.md` | frozen parent policy + runtime artifact |
| Micro-pullback work | `docs/research/micro_benchmark_suite.md` | `micro_policy.py`, `micro_replay.py`, frozen artifacts |
| Held-out discretionary panel | `docs/research/discretion_heldout_panel_v01.md` | registered panel JSON and runtime manifest |
| Context-assessment shadow | `docs/research/discretion_context_assessment_v01.md` | `research/strategy/discretion-context-assessment-shadow-v0.1.json` and `context_assessment.py` |
| Context held-out panel | `docs/research/context_heldout_panel_v01.md` | `research/strategy/context-heldout-panel-v0.1.json` |
| Daily-chart context shadow | `docs/research/daily_chart_context_v01.md` | `research/strategy/daily-chart-context-shadow-v0.1.json` and `daily_chart_context.py` |
| Theme/regime context shadow | `docs/research/theme_regime_context_v01.md` | `research/strategy/theme-regime-context-shadow-v0.1.json` and `theme_regime_context.py` |
| Context held-out runtime | `docs/research/context_heldout_runtime_v01.md` | `.github/workflows/context-heldout-runtime.yml` and `context_runtime.py` |
| Context semantic shadow | `docs/research/context_semantic_shadow_v01.md` | frozen rubric, artifact manifest and `context_semantic_shadow.py` |
| Context held-out retrospective labels | `docs/research/context_heldout_labels_v01.md` | frozen label audit and `context_heldout_labels.py` |
| Context held-out component comparison | `docs/research/context_heldout_comparison_v01.md` | frozen comparison audit and `context_heldout_comparison.py` |
| Campaign/portfolio/account state | `docs/research/campaign_portfolio_account_state_v01.md` | registered contract and `campaign_portfolio.py` standalone ledger |
| Paper account/scarcity policy | `docs/research/paper_account_scarcity_policy_v01.md` | registered policy contract and `account_priority_policy.py` |
| Account chronological integration | `docs/research/account_chronological_integration_v01.md` | registered panel/contract and `account_chronological_integration.py` |
| Account pre-session capture | `docs/research/account_session_snapshot_capture_v01.md` | registered capture contract, `account_snapshot_capture.py` and scheduled workflow |

## Component route

`historical providers -> causal universe/scanner -> Micro setup/replay -> execution/risk -> retrospective evaluation`

Discretionary context is currently a parallel descriptive shadow artifact. It does not feed the frozen Micro replay or order path.

- Production code: `src/momentumbot/`
- Provider-facing builders and replay entry points: `scripts/`
- Machine-readable research registrations, policies and audits: `research/`
- Explanatory research record: `docs/research/`
- Deterministic verification: `tests/`
- Hosted reproducibility checkpoints: `.github/workflows/`

## Working protocol

1. Read the current checkpoint and the relevant component document; do not load the whole repository by default.
2. State the frozen parent, the one hypothesis being tested and the prohibited retrospective inputs.
3. Make the smallest isolated change and add a deterministic test.
4. Run focused local tests, including optimized-mode checks for new safety gates.
   Publish the code checkpoint for one authoritative full GitHub CI run. Do not
   run the entire suite locally as a duplicate prerequisite. No provider job or
   policy promotion may proceed until CI for its exact code commit passes.
   Documentation/evidence-only follow-ups do not require another local full suite.
5. Record the result even when it fails; policy promotion is a separate explicit decision.

## Local verification

The owner authorized this streamlined process on 2026-09-12. Retain immutable
failed experiments, exact source/CI/artifact provenance, causal input boundaries,
credential protection, bounded spending and single-use provider jobs. Reuse
tested utilities and batch related fixes; do not multiply approval-only commits
or copy entire launchers when a focused extension suffices. A bounded diagnostic
under the owner's current continuation authorization may run after same-commit
CI, without another confirmation turn. New paid subscriptions, expanded datasets
or financial/live-order authority still require a separate explicit decision.

```bash
python -m pip install -e .
python -m unittest tests.test_component_being_changed -v
```
