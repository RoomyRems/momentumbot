# Current project checkpoint

Status applies to the latest validated checkpoint on branch `phase-3-historical-snapshot`.

This file is a routing checkpoint, not a second policy specification. Follow its links to the machine-readable manifests and audits for exact hashes and counts.

## Frozen foundations

- The historical pipeline preserves the decision-time boundary for universe membership, market qualification, float and publication-timed news.
- The causal scanner snapshot and its compact source-input sidecars can be replayed without asking the provider to recreate the scanner features.
- The ten-session held-out panel is preregistered for 2026-07-10 through 2026-07-23. Its label-blind runtime is frozen as artifact `discretion-heldout-runtime-v0.1` (artifact `9305468839`, workflow run `32071946359`).
- That runtime retains all 119 causal market candidates and 12,440 scanner decision rows. No top-N selection, Ross action, trade outcome or later price outcome was used.
- The frozen technical parent remains `micro-v0.1`, fingerprint `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`.
- Its ten-session Micro replay is frozen as artifact `discretion-heldout-micro-runtime-v0.1` (artifact `9310627233`, workflow run `32096497787`, ZIP SHA-256 `3b59e4b1a69e268158f6ccbead1fe9abae425fc249e72b34f466e53ebba56b20`). Of 119 candidates, 118 were replayable, 49 produced at least one plan and 36 produced at least one modeled fill; LIVE was correctly isolated as provider-unavailable rather than counted as a zero-plan case.
- Catalyst timing, catalyst evidence, catalyst interpretation and attention/leadership exist as descriptive shadow context. They have no order, score, threshold or risk authority.
- Retrospective evidence is frozen for all ten dates from the supplied 300-record caption batch. Main and small accounts remain separate, ticker corrections are explicit, and unmentioned candidates remain unknown. The label content SHA-256 is `4dd31df3fcace0bcc0b52045c748a1a91e00130867394e21c605af5f42007204`.
- The frozen component comparison has content SHA-256 `809d4b4a7231b708f9c933c9bf45b58c736f4d3101c8328483c62c1c48bcfb3d`. Micro-v0.1 modeled fills on 6/9 acquired documented trades in each account, but also fired on 2/7 main-account skips and missed three documented decisions per account. The scanner acquired 11/13 unique observed traded symbol-dates. No rule was retuned or promoted.
- The first context-assessment protocol is preregistered as `discretion-context-assessment-shadow-v0.1`, contract content SHA-256 `8205772680ce290d58de1d17fbe43d02c2beb21fd9f0e16d8bd2c7b3a1806f26`. It composes exact causal source rows into a hashed decision snapshot and constrains any AI shadow to evidence-cited, fact/inference-separated, abstaining assessments with a maximum 300-second logical lifetime. It freezes no semantic model, score, threshold, or runtime artifact and explicitly excludes the reviewed ten-session pilot from fitting.
- The next context panel is registered calendar-only as `ross-context-heldout-panel-v0.1`, content SHA-256 `d227792368b3bff5c3c2365cacd204c11b7991daeb557efba450c22f076d8898`. Its fixed dates are the ten sessions from 2026-07-24 through 2026-08-06. No transcript file, source inventory, ticker, Ross action, outcome, later price, or P&L was opened or used for selection; missing source evidence cannot replace a date.
- The deterministic daily-chart evidence layer is frozen as `daily-chart-context-shadow-v0.1`, contract content SHA-256 `55262a3c6537d1511248577c0e01f0a36775ed98bff9d6839b12e00da3f2fa87`. It uses at most 60 completed pre-decision sessions, split-adjusted to the decision-date share basis, to expose 20/50-session averages, 5/20/50-session levels, raw recent-session fade metrics, and exact overhead-reference distances. It freezes no failed-pop threshold or chart score. A 200-session average is explicitly deferred until identity continuity is extended beyond the current 120-calendar-day gate. No held-out daily-chart runtime artifact has been materialized yet.
- The deterministic theme/regime evidence layer is frozen as `theme-regime-context-shadow-v0.1`, contract content SHA-256 `e240babc3004c33f2a9fd16ed80f3be24d8a332c48eb603ebfe57a9c795a92e0`. It exposes the exact same-minute ranked candidate cohort, provider-relative news/no-news participation, available cross-candidate headline associations, and up to five earlier completed-session summaries. It freezes no hot/cold threshold, theme taxonomy, theme-fit rule, no-news acceptance threshold, or score. No held-out theme/regime runtime artifact has been materialized yet.

Exact provenance lives in:

- `research/data-audits/discretion-heldout-runtime-v0.1-2026-08-17.json`
- `research/data-audits/discretion-heldout-micro-runtime-v0.1-2026-08-17.json`
- `research/data-audits/discretion-heldout-labels-v0.1-2026-08-18.json`
- `research/data-audits/discretion-heldout-comparison-v0.1-2026-08-18.json`
- `research/strategy/discretion-heldout-panel-v0.1.json`
- `research/strategy/discretion-context-assessment-shadow-v0.1.json`
- `research/strategy/context-heldout-panel-v0.1.json`
- `research/strategy/daily-chart-context-shadow-v0.1.json`
- `research/strategy/theme-regime-context-shadow-v0.1.json`
- `docs/research/discretion_heldout_panel_v01.md`
- `docs/research/discretion_heldout_labels_v01.md`
- `docs/research/discretion_context_assessment_v01.md`
- `docs/research/context_heldout_panel_v01.md`
- `docs/research/daily_chart_context_v01.md`
- `docs/research/theme_regime_context_v01.md`

## Active gate

Materialize the preregistered context protocol on a new, label-blind panel without changing Micro-v0.1:

1. keep the now-registered 2026-07-24 through 2026-08-06 dates fixed and do not inventory or review their recap material before runtime freeze;
2. materialize the now-frozen daily-chart and theme/regime schemas, preserving explicit missing states when point-in-time evidence is unavailable;
3. generate decision snapshots from scanner, attention, catalyst and new deterministic sources, then freeze them before labels;
4. run any semantic reviewer AI shadow-only through the frozen citation/abstention schema; and
5. keep candidate acquisition, contextual assessment, Micro setup and execution as separate measurable gates with no aggregate score fitted on the prior pilot.

The ten-session result is a component diagnostic, not a portfolio backtest. Repeated plans can belong to one campaign, and buying power, divided attention, Level 2, tape-based management and complete exits are still absent.

## Next gates

1. Register and run the first new held-out context panel; the reviewed ten-session pilot remains excluded from fitting.
2. Add campaign/portfolio/account state so repeated Micro emissions are consolidated into decisions Ross could actually take.
3. Add realistic execution and latency, then Level 2/time-and-sales capture and deterministic summaries where historical or live data permits.
4. Validate any AI contribution out of sample and in live shadow before it can affect paper decisions.
5. Run a larger preregistered walk-forward panel before considering policy promotion or interpreting P&L.

## Explicitly not ready

- No claim of exact Ross imitation or comparable profitability.
- No production selection authority for AI.
- No complete Level 2/tape, position-management or broker-execution model.
- No live-money trading.
