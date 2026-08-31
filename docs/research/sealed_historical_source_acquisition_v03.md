# Sealed historical source acquisition v0.3

## Purpose

Source v0.2 completed successfully, but its first provider-free runtime exposed
a price-basis defect: split-adjusted previous closes were divided into raw
intraday closes. The resulting artificial leaders invalidated candidate
discovery and cross-sectional rank. The permanent parent failure remains in
`sealed_historical_scanner_runtime_v01_failure.md`.

v0.3 is the smallest child repair. It preserves the 30 dates, identity rules,
providers, routes, request and retention ceilings, float/news rules, scanner
thresholds, Micro-v0.1, both account policies, and every authority boundary.
It does not reuse or mutate the consumed v0.2 tree.

## Normalization rule

- Actual price and cumulative volume use raw target-session bars.
- Percentage gain uses a split-adjusted target close divided by the
  split-adjusted previous close.
- Cross-sectional rank uses that same split/split ratio for every identity
  member.
- RVOL remains the existing exact same-time split-adjusted ratio.
- Raw and split target-minute timestamps must match; disagreement fails the
  date closed.

Any provider split factor therefore cancels from gain and rank. It cannot alter
the raw price threshold. Candidate discovery and scanner rank are rebuilt
together because both were exposed to the parent defect.

## Authority and execution

Push events run provider-free validation only. Acquisition requires a manual
dispatch pinned to one exact authorization commit, attempt 1, after a distinct
v0.3 consumption marker is persisted. Automatic reruns, provider substitution,
Databento calls, paper/live orders, transcript reads, Ross-label reads, policy
promotion, and account runtime remain unauthorized.

After a successful bundle is independently verified, the next gate is again
provider-free: freeze label-blind scanner and Micro decisions before any
retrospective transcript comparison.
