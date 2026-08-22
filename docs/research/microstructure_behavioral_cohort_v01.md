# Microstructure behavioral cohort v0.1

## Purpose

This registration freezes the first representative slice for the label-blind microstructure behavioral comparison. It is exhaustive only within a precise existing scope: every `entry_accepted` event from the frozen main-account Micro-v0.1 replay across the ten registered July sessions. It is not a claim that ten opportunities represent the full market or every Micro candidate.

No new market-data value, microstructure feature, Ross action, retrospective label, P&L, or later price selected the cohort.

## Mechanical selection

The source is the immutable historical-account diagnostic built from the immutable held-out Micro runtime. The rule is:

1. take the main account only, because its $30,000 policy supplies the primary general-profile prospective quantity;
2. include every accepted entry event in all ten sessions;
3. keep starters and reentries as distinct opportunities when their plan and opportunity IDs differ;
4. exclude nonaccepted events and the small-account copy of an identical causal anchor;
5. order by date, receive-time anchor, symbol, and plan ID.

This yields ten opportunities, seven symbols, five active dates, seven starters, three reentries, and 5,558 prospectively sized shares in total. Each opportunity freezes its exact activation, opportunity, and plan IDs; causal trigger time; trigger print; breakout and minimum-new-high prices; stop; plan lifetime; internal runtime path and hash; and main-account quantity.

## Exact future request surface

The future provider surface is five date-grouped `XNAS.ITCH` MBO requests. Each begins at midnight UTC so provider reset/snapshot semantics can establish the book. Each ends one nanosecond after the latest selected anchor on that date plus the maximum registered ten-second horizon. Symbols are sorted and grouped by date:

- July 10: GMM;
- July 13: PLSM and VEEE;
- July 14: NXTC and SHPH;
- July 20: BIYA;
- July 23: NEUP.

The registration itself is unarmed. It makes no metadata quote and no time-series request, spends no Databento credit, and has no execution file or workflow. A later direct-child execution file would have to quote all five exact requests before any download and stop with zero downloads if the aggregate quote exceeds either `$0.25` or `225,000,000` bytes. Retries, partial-cohort substitution, batch/live endpoints, raw-data publication, and feature-value publication remain prohibited.

## Quantity and comparison boundary

Each depth walk uses the already-frozen main-account accepted quantity for that opportunity. The same quantity must be used for pre versus post windows and for primary versus stress execution scenarios. No later liquidity observation may resize, replace, or suppress an opportunity.

All one-, five-, and ten-second horizons and all registered feature families remain mandatory. Results remain descriptive shadow evidence. They cannot create a threshold, confirmation, veto, hidden-order label, strategy change, broker action, profitability claim, or live-money authority.

## Files

- Cohort and request contract: `research/strategy/microstructure-behavioral-cohort-v0.1.json`
- Validator: `src/momentumbot/research/microstructure_behavioral_cohort.py`
- Focused tests: `tests/test_microstructure_behavioral_cohort.py`
- Registration audit: `research/data-audits/microstructure-behavioral-cohort-v0.1-registration-2026-08-21.json`
