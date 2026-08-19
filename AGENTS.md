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
| Current checkpoint / next gate | `docs/project/current_state.md` | linked frozen manifests and audits |
| Runtime and hybrid architecture | `docs/architecture.md` | executable code under `src/momentumbot/` |
| Current Ross-derived policy | `docs/strategy/current_rulebook.md` | `research/rules/current_rules.json` and policy code |
| Historical-data requirements | `docs/DATA_REQUIREMENTS.md` | validators/loaders under `src/momentumbot/` |
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
