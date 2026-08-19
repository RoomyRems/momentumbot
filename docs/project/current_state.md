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
- The deterministic daily-chart evidence layer is frozen as `daily-chart-context-shadow-v0.1`, contract content SHA-256 `55262a3c6537d1511248577c0e01f0a36775ed98bff9d6839b12e00da3f2fa87`. It uses at most 60 completed pre-decision sessions, split-adjusted to the decision-date share basis, to expose 20/50-session averages, 5/20/50-session levels, raw recent-session fade metrics, and exact overhead-reference distances. It freezes no failed-pop threshold or chart score. A 200-session average is explicitly deferred until identity continuity is extended beyond the current 120-calendar-day gate. Its held-out runtime is now frozen inside artifact `9376599434` with content SHA-256 `e39cc7e606dd34568061d39eb5b1df4706221c5b728813a1b3715f3236a17c30`: 285 records plus 29 explicit unavailable rows, all for exact fail-closed scanner decisions whose completed candidate bar and decision price were absent.
- The deterministic theme/regime evidence layer is frozen as `theme-regime-context-shadow-v0.1`, contract content SHA-256 `e240babc3004c33f2a9fd16ed80f3be24d8a332c48eb603ebfe57a9c795a92e0`. It exposes the exact same-minute ranked candidate cohort, provider-relative news/no-news participation, available cross-candidate headline associations, and up to five earlier completed-session summaries. It freezes no hot/cold threshold, theme taxonomy, theme-fit rule, no-news acceptance threshold, or score. Its held-out runtime is now frozen inside artifact `9376599434` with content SHA-256 `233bd12969c1d327f2c32c6f8a3d1ea1f331f4aeb8bc1b7ab4cb7dd7befa1ce4` and 314 deterministic records.
- The label-blind provider workflow for the registered context panel is bound to `ross-context-heldout-runtime-request-v0.1`, content SHA-256 `9459660565c6c76c4af2fd09fd8362789bfda89fe57601d0f016b189112bbff0`. It rebuilds all market/scanner inputs, materializes daily and theme evidence only at activation or causal provider-news changes, and composes hash-bound context snapshots. It uses the exact prior runtime manifest `2414f7389bf68d5a5e4b3302c646c9111020cb79ce06fc0213f7872062f79c48` only for five already-completed scanner-session summaries. Push-triggered run `32260356870` successfully froze artifact `9376599434`; its final manifest content SHA-256 is `3567619bfb6b7b2c177d02cc69f15423bf605663519017a6638b0394e4153702`.
- The first build attempt, workflow run `32197398999`, completed all ten market-discovery dates and retained 195 candidates, then failed in 2026-08-06 float enrichment because the basis-bar query extended beyond the causal trading date into the provider's recent SIP entitlement window. Its partial artifact `9348281247` is diagnostic only. The acquisition repair caps the exclusive query end at the day after the causal trading date, rejects future measure dates, and leaves SIP, raw/split basis comparison, `asof`, scanner thresholds, and Micro-v0.1 unchanged. No recap or transcript inventory was opened.
- The repaired workflow run `32204337846` has two permanently retained failed attempts. Attempt 1 stopped on Massive HTTP 429 contention while another provider-heavy workflow overlapped; its diagnostic artifact is `9348619522`. The one permitted unchanged retry completed all ten provider/scanner dates and independently replayed the scanner, then failed while freezing the top-level market manifest because `contract_hash` and `request` were not bound in that function; its diagnostic artifact is `9351037605`. Both are partial, label-ineligible, and non-promotable. The repair now loads and validates the frozen panel/request through one shared helper used by both the session gate and final manifest path, with a regression that executes the final manifest binding. Micro-v0.1, scanner thresholds, and the data policy remain unchanged.
- Push-triggered workflow run `32243689589` then completed all ten market/scanner dates, retained all 195 candidates, and passed provider-independent scanner replay before failing in daily-chart materialization on July 28. A valid fail-closed scanner row can preserve `price = null` when the exact completed candidate bar is absent; the downstream materializer incorrectly called `float(None)`. Its partial artifact `9365791454`, ZIP SHA-256 `377d79ef0613ae2b92633883caf00dba447f7567ae8c1e1af1203455788ead77`, is diagnostic, label-ineligible, and non-promotable. The repair now emits explicit unavailable daily-chart evidence with the exact scanner disposition and never substitutes a prior, next, nearest, or later price. Non-null malformed or non-positive prices still fail closed. Micro-v0.1, scanner thresholds, data policy, and semantic-AI authority are unchanged.
- Push-triggered workflow run `32260356870` at exact head `4a9f3512c1a79ae5d0df86f4a83a3864b2aa2ad2` and tree `3659efff5dc9567b4e5da3080bc80cc59ddeb327` succeeded. Artifact `9376599434`, `context-heldout-runtime-v0.1`, has independently recomputed ZIP SHA-256 `a29186eb092752cfafc031360cacf348bea5e607cb19ce326ddaff2ddfedac1a`. All 115 manifest/content SHA-256 claims and parent-child bindings recompute; provider-independent replay reproduces all 195 candidates and 18,954 scanner rows. The artifact covers the exact ten registered sessions, includes no semantic AI, has no strategy authority, and is not policy-promotion evidence. The permanent success audit is `research/data-audits/context-heldout-runtime-v0.1-run-32260356870-success-2026-08-19.json`.
- The label-blind compiled semantic shadow is now frozen as `ross-context-heldout-semantic-shadow-runtime-v0.1`, manifest content SHA-256 `9b3be7a17f29e638b0e1da14b4d050762503bab17c74c3f97e62b99489f25cd4`. It binds all 314 exact snapshots and the parent ZIP/runtime hashes. GPT-5.6 Sol in Work Mode authored the frozen rubric, content SHA-256 `959256aedcc7ed89c8120b19cd1640547a63eb24fcca359c476117ba679f13d3`, before retrospective source inventory; repository code applies it deterministically for exact reproducibility. This is transparently a compiled semantic proxy, not a claim of 314 separately hosted model calls. It assesses headline substance on 314 snapshots, commitment on 254, leadership and chart context on 285 each, and abstains on every credibility/repetition and theme-fit axis because required semantic evidence is absent. It has no aggregate score, selection threshold, order, size, risk, or policy authority. The permanent audit is `research/data-audits/context-semantic-shadow-v0.1-2026-08-19.json`.

Exact provenance lives in:

- `research/data-audits/discretion-heldout-runtime-v0.1-2026-08-17.json`
- `research/data-audits/discretion-heldout-micro-runtime-v0.1-2026-08-17.json`
- `research/data-audits/discretion-heldout-labels-v0.1-2026-08-18.json`
- `research/data-audits/discretion-heldout-comparison-v0.1-2026-08-18.json`
- `research/data-audits/context-heldout-runtime-v0.1-run-32197398999-failure-2026-08-18.json`
- `research/data-audits/context-heldout-runtime-v0.1-run-32204337846-attempt-1-failure-2026-08-19.json`
- `research/data-audits/context-heldout-runtime-v0.1-run-32204337846-attempt-2-failure-2026-08-19.json`
- `research/data-audits/context-heldout-runtime-v0.1-run-32243689589-attempt-1-failure-2026-08-19.json`
- `research/data-audits/context-heldout-runtime-v0.1-run-32260356870-success-2026-08-19.json`
- `research/data-audits/context-semantic-shadow-v0.1-2026-08-19.json`
- `research/strategy/discretion-heldout-panel-v0.1.json`
- `research/strategy/discretion-context-assessment-shadow-v0.1.json`
- `research/strategy/context-heldout-panel-v0.1.json`
- `research/strategy/daily-chart-context-shadow-v0.1.json`
- `research/strategy/theme-regime-context-shadow-v0.1.json`
- `research/strategy/context-semantic-shadow-compiled-rubric-v0.1.json`
- `research/frozen/context-semantic-shadow-runtime-v0.1/manifest.json`
- `docs/research/discretion_heldout_panel_v01.md`
- `docs/research/discretion_heldout_labels_v01.md`
- `docs/research/discretion_context_assessment_v01.md`
- `docs/research/context_heldout_panel_v01.md`
- `docs/research/daily_chart_context_v01.md`
- `docs/research/theme_regime_context_v01.md`
- `docs/research/context_heldout_runtime_v01.md`
- `docs/research/context_semantic_shadow_v01.md`

## Active gate

The preregistered deterministic runtime and label-blind semantic shadow are now frozen. Continue without changing Micro-v0.1:

1. preserve artifact `9376599434` and its permanent success audit as the immutable pre-label parent;
2. preserve semantic-shadow manifest `9b3be7a17f29e638b0e1da14b4d050762503bab17c74c3f97e62b99489f25cd4` as the immutable pre-label semantic parent;
3. inventory the supplied transcript archive only for the ten registered dates without replacing missing dates or converting unavailable/unmentioned evidence into a skip;
4. freeze conservative account-scoped retrospective labels before any component comparison; and
5. keep candidate acquisition, contextual assessment, Micro setup and execution as separate measurable gates with no aggregate score fitted on the prior pilot.

The ten-session result is a component diagnostic, not a portfolio backtest. Repeated plans can belong to one campaign, and buying power, divided attention, Level 2, tape-based management and complete exits are still absent.

## Next gates

1. Freeze account-scoped trade, skip, unclear, unmentioned or unavailable labels for the registered 2026-07-24 through 2026-08-06 panel, then compare each deterministic and semantic component descriptively without fitting.
2. Add campaign/portfolio/account state so repeated Micro emissions are consolidated into decisions Ross could actually take.
3. Add realistic execution and latency, then Level 2/time-and-sales capture and deterministic summaries where historical or live data permits.
4. Validate any AI contribution out of sample and in live shadow before it can affect paper decisions.
5. Run a larger preregistered walk-forward panel before considering policy promotion or interpreting P&L.

## Explicitly not ready

- No claim of exact Ross imitation or comparable profitability.
- No production selection authority for AI.
- No complete Level 2/tape, position-management or broker-execution model.
- No live-money trading.
