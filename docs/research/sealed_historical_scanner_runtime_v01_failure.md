# Sealed historical scanner runtime v0.1: normalization failure

## Result

The exact v0.2 source bundle was independently replayed provider-free across
all 30 registered sessions. Every one of the 66,902 frozen general-profile
scanner rows reproduced exactly from the canonical compressed inputs.

The downstream activation gate nevertheless failed. The provisional pass found
121 general-profile activations but zero small-account activations. This is not
a small-account strategy result. Across 25 sessions, 4,156 scanner row-minutes
passed every small-account pillar except the required top-three rank.

## Root cause

The frozen rank pipeline compares split-adjusted daily previous closes with raw
same-session minute closes. The retained inputs prove the two series are on
incompatible share bases. Representative raw-close/previous-close ratios are
approximately 10 for NFLX and KLAC, 15 for ORLY, 25 for BKNG and 38--41 for
RGC. Those near-integer ratios create mechanically impossible cross-sectional
leaders with gains of hundreds or thousands of percent and permanently occupy
the small-account top-three rank.

The same basis mismatch can affect upstream candidate discovery, so repairing
only the final rank is insufficient. The candidate set and scanner must both be
rebuilt on one time-causal share basis.

## Boundary and disposition

No provider call, Databento call, transcript read, Ross-label read, Micro replay,
account replay or order occurred in this diagnostic. The 121 provisional
general activations are not frozen and cannot be used downstream. Source v0.2
remains an immutable, successfully acquired transport artifact; its runtime
validity is not established.

The next valid step is a new child acquisition registration that changes only
the historical price-normalization basis, preserves all 30 dates and every
strategy/account rule, rebuilds discovery and rank, and cannot reuse or mutate
the consumed v0.2 authorization.
