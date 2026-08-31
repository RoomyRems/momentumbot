# MomentumBot agent routing

MomentumBot is a research-first, historically causal approximation of Ross Cameron's small-cap momentum process. The active branch is `phase-3-historical-snapshot`; no live-money trading is in scope.

## Non-negotiable boundaries

- Runtime order is market data -> label-blind replay -> frozen artifact -> retrospective Ross comparison.
- Never expose Ross fills, actions, recap labels or later price outcomes to runtime reconstruction.
- Do not tune thresholds case by case or promote a policy from the diagnostic seed suite.
- Measurable facts, timestamps, order mechanics and every risk limit remain deterministic.
- AI begins shadow-only, uses time-causal structured inputs, may abstain, cannot submit orders and cannot increase deterministic risk.
- Preserve failed experiments and their provenance.

## Route by task

| Task | Open first | Source of truth |
|---|---|---|
| Current checkpoint / next gate | `docs/project/current_state_2026-08-31.md` | immutable parent checkpoints plus linked frozen manifests and audits |
| Sealed historical walk-forward | `docs/research/sealed_historical_walk_forward_v01.md` | opaque corpus commitment, prior-date exclusions, deterministic 30-session selector and provider-free registration audit |
| Sealed historical provider availability | `docs/research/sealed_historical_provider_availability_v02.md` | permanent v0.1 routing failure, one-call main-credential child repair and unchanged acquisition boundary |
| Sealed historical source acquisition | `docs/research/sealed_historical_source_acquisition_v02.md` | permanent v0.1 request-budget failure, request-ceiling-only v0.2 child and unchanged causal acquisition graph |
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
4. Run the narrow tests, then the full suite before publishing.
5. Record the result even when it fails; policy promotion is a separate explicit decision.

## Local verification

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```
