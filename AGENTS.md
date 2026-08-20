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
| Current checkpoint / next gate | `docs/project/current_state_2026-08-20.md` | immutable parent checkpoint plus linked frozen manifests and audits |
| Runtime and hybrid architecture | `docs/architecture.md` | executable code under `src/momentumbot/` |
| Current Ross-derived policy | `docs/strategy/current_rulebook.md` | `research/rules/current_rules.json` and policy code |
| Strategy/discretion coverage | `docs/research/strategy_discretion_coverage_v01.md` | `research/strategy/strategy-discretion-coverage-v0.1.json` and `strategy_coverage.py` |
| Historical-data requirements | `docs/DATA_REQUIREMENTS.md` | validators/loaders under `src/momentumbot/` |
| Level 2/tape feasibility | `docs/research/level2_tape_feasibility_v01.md` | `research/strategy/level2-tape-feasibility-v0.1.json` and `microstructure_contract.py` |
| Databento metadata/cost gate | `docs/research/databento_metadata_quote_v01.md` | child quote contract, `databento_quote.py` and quote workflow |
| Databento bounded acquisition | `docs/research/databento_microstructure_smoke_acquisition_v01.md` | hash-bound smoke contract, `databento_smoke.py` and one-shot acquisition workflow |
| Prospective management/execution | `docs/research/prospective_management_execution_v01.md` | child contract and `execution_realism.py` |
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
