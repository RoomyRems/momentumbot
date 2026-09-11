# Early-pullback selection v0.1 — registered, not evaluated

## Question and frozen parent

Does admitting only causal pullbacks one and two improve paired net P&L against
unchanged Micro-v0.1 on a separately fixed panel? The parent is
`b37c75a04057ba51e2fefde93e31f61239aa2455`, tree
`ac2d6c16b02c72ffa619c5a94ced7d9bdaaa4e25`.

This is one experimental interpretation of `MB-ENT-006`'s preference for early
pullbacks. The source does not prescribe a hard cutoff of two. The previous
30-date baseline and its ordinal cohorts were already inspected: first and
second cohorts also lost. Those results cannot establish this hypothesis, and
none of those dates is used as holdout evidence here. The current-era policy
is being applied retrospectively; this is not a claim that every current rule
was known at each historical date.

## One change, isolated from the existing trading path

The child may admit an otherwise valid original trigger only when the unchanged
`causal_active_pullback_number` returns one or two on the original activation's
completed plan prefix. It counts confirmed running-high resumptions, not fills
or retrospectively labelled Ross pullbacks. Withholds, fills, re-entry and new
peaks do not reset the original activation anchor. Original profile activation
semantics are retained.

The new helper accepts only high/low/volume and causal clocks. It requires a
unique ordered ten-second prefix ending at the original source bar and a
decision inside the original armed/expiry window. Invalid or future evidence
fails unresolved; it is not converted to a strategy withhold. The result binds
the ordinal-input hash, ordinal, disposition and reason. It authorizes no order.

This helper does **not** authenticate the original setup or trigger by itself.
A future source-binding adapter must recompute and verify the original plan,
activation, completed support and full causal-prefix hash, compare the ordinal,
and retain both-arm dispositions for every original trigger. That adapter and
the paired historical account runner are not implemented or activated here.

Scanner thresholds, setup geometry, support, stops, targets, risk, sizing,
fees, execution clocks/freshness, management and continuation remain unchanged.
There is no additional MACD or room-to-peak filter and no symbol exception.

## Sample fixed before opening its market outcomes

The first selection scanned all 1,519 tracked files from the immutable parent.
Every valid interval ISO date in paths and bytes counts as an exclusion,
including nested gzip/ZIP members, source/tests, synthetic cases and calendar
mentions. Only date-shaped bytes and file hashes are projected; record values
are not deserialized or persisted. The scan excludes 176 dates in the original
January 2, 2025–June 30, 2026 interval. Of the frozen calendar's full sessions,
229 remain: seven complete blocks of 30 and an unused 19-session tail.

SHA-256 over the contract ID, parent commit, frozen calendar ID and exclusion
hash selects block index six. The 30 nonconsecutive dates run from March 4 to
May 19, 2026. Their exact list is in the [registration](../../research/strategy/early-pullback-selection-v0.1.json).
The seed is `8046d881bb242d175f1f7e3e50898eee9afc710fcf152d025a35199af9d46d57`.
There is no seed retry, date replacement or relaxed exclusion fallback.

The [exclusion inventory](../../research/data-audits/early-pullback-selection-v0.1/date-exclusions.json)
is pinned at `b9318eabcf7acca2831fc88a7935eeb6854b52992f1689a512fbdfbec3cf2276`.
Independent verification checks the complete parent tree inventory and every
Git blob against the archive before reconstructing the date-only scan.
All old baseline and earlier exclusion dates remain excluded.

These are **repository-unreferenced dates**, not a certification that nobody has
seen their outcomes elsewhere. Any discovered contamination invalidates and
preserves the entire registration; it does not trigger automatic reselection.
The inherited calendar also requires independent provider-session confirmation
before acquisition. No market data or attached transcript records were opened
to evaluate this new panel during registration.

## Evaluation fixed in advance

Both arms use the same common source and retain all source triggers. Each arm
has independent once-seeded $30,000 and $2,000 account paths, crossed with the
original three horizons and two execution scenarios: 12 paths per arm and
720 dated records in total. Cash, scarcity, fees and campaign state must evolve
independently after eligibility diverges. Subtracting excluded fills from the
old baseline or reusing control balances is not a valid counterfactual.

The primary comparison is child minus control terminal net P&L for the main
account, conservative execution, one-second horizon. A positive difference with
at least one closed child entry is descriptive directional support only; a
nonpositive difference does not support the hypothesis. No child entries is
inconclusive. Loss reduction is not profitability, and no formal significance,
Ross-replication or policy-promotion claim is authorized.

All 24 paths must be reported separately, including absolute/paired P&L,
activity/withhold/unavailable counts, exposure, fill fractions, fees, session-
close drawdown, win rate/profit factor, exit attribution, daily paired deltas
and best-closed-trade-removed arithmetic sensitivity. Shared dates, horizons
and accounts are not independent confirmations. No best-cell selection.

Both runtime chains must be frozen before outcomes are joined. Every date is
retained. Verified zero-opportunity dates remain zeros; failed/unavailable dates
remain unavailable and are not replaced. Aggregate financial conclusions require
all paired paths verifiable and flat-complete under the unchanged strict
observed-update policy. Source-proven strict-quote withholds preserve their
unavailable-source history; unresolved gaps cannot be disguised as those
withholds. A mere helper pass cannot open this evaluation gate.

## Verification and next gate

Registration hash:
`980d7f3c8ab122fcee5f35d9da8d9a03633feb50b4e00f7287a85a0b58dd10fb`.

Focused tests cover ordinal boundaries and resets, clock/grid/data rejection,
future/label rejection, timestamp resolutions, immutable input hashes, recursive
date exclusion, exhausted samples, manifest tampering, original date exclusion
and closed authority. The provider-free verification command is:

```bash
PYTHONPATH=src python -O scripts/register_early_pullback_selection_v01.py --verify-parent
```

All 25 focused tests pass with pandas 2.2.3/NumPy 2.3.5 and with assertions
disabled under pandas 3.0.5/NumPy 2.5.3. The independent optimized parent-inventory
check passes. All 2,499 local full-suite tests pass in 269.451 seconds with zero
skips, and compilation passes. The [verification record](../../research/data-audits/early-pullback-selection-v0.1/implementation-verification.json)
binds the retained full and compatibility logs. Hosted results are the separate
publication commit checks, not assumed from local success. The losing
baseline, successful setup/stop audit and explicit hosted-only local-replay
waiver remain unchanged. No historical account replay is being repeated here.

Next: freeze and synthetically verify the paired source-binding/account adapter
and a bounded availability/cost plan for these exact dates. Provider calls,
paid acquisition, historical account execution, paper/live orders and policy
promotion remain closed in this registration. A separate bounded authorization
is required before crossing those gates; this commit schedules nothing.
