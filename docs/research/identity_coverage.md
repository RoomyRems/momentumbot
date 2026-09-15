# Dated identity and coverage handoff

Child of `9dec40ea1b9a2dd77b86faddba08f1fbcfdf5eb1`, registered as
`early-pullback-identity-coverage-v0.1`. This offline integration binds the
completed census and daily/action capture to the existing dated membership and
identity rules. It changes no strategy, risk limit, benchmark date or account
mechanic. It does not read transcript labels, Ross actions/fills or evaluation
outcomes, and it makes no provider requests.

## Completed source build

All 30 registered dates were built from the exact original census ZIP and
completed coverage-continuation ZIP, including its original failed prefix.
The accepted hosted source replay is reused; it is not run again locally.
Every newly consumed member is checked against its original inventory. All
60 identity roots are reconstructed with the already repaired action parser,
and their ordered normalized row commitments must equal the accepted report.

| Result | Count |
|---|---:|
| Dated accepted memberships | 165,694 |
| Post-coverage identity quarantines | 188 |
| Explicit daily-coverage failures | 107 |
| Adjacent-date ticker changes | 31 |
| Same ticker with different nonblank FIGIs | 4 |
| Duplicate accepted identifier groups within a date | 0 |
| Reused raw/asof alias views | 93 |
| Earlier-date alias comparisons matched | 31 |
| Captured name-change paths found | 30 |
| Uncaptured alias views | 31 |
| Remaining alias request roots | 17 |
| Fully matched bidirectional alias checks | 0 |

The action evidence contains 48,660 row references across overlapping 120-day
windows. This is not a count of unique actions across the panel. All 31
earlier-date alias comparisons match; all 31 later-date comparisons are missing
the old-ticker/earlier-asof source query.

The dated membership, exact quarantines, coverage failures, original action
rows and member/request lineage are retained in
`research/data-audits/early-pullback-identity-coverage-v0.1/identity-coverage-panel.json.gz`.
`summary.json` pins that compressed file and summarizes every date.
`local-verification.json` records the saved-file roundtrip, source bindings and
focused tests. `remaining-alias-plan.json` contains the exact unresolved query
union. The implementation and tests are file-bound in
`research/strategy/early-pullback-identity-coverage-v0.1.json`.

## Identity and time semantics

Membership is recomputed independently for each date: original metadata
classifier, actual daily-coverage observations, then composite FIGI or unique
CIK fallback. CIK uniqueness is recomputed after coverage. Missing coverage is
not fabricated, missing identifiers retain the existing quarantine, and
different nonblank FIGIs cannot be merged by a shared issuer CIK.

The cross-date bridge is diagnostic and uses adjacent registered dates. It
cannot replace an earlier date's ticker, identity or membership. Corporate
actions retain all original rows, including records unrelated to that date's
accepted symbols. Symbol matches are relevance links, not proof of security
identity. Provider process/execution dates are not historical publication
timestamps. No historical adjustment factor is applied and no action becomes
runtime news.

For each ticker change, the unchanged alias method requires four distinct raw
daily views: old ticker under the earlier asof and new ticker under the later
asof, each observed at both comparison dates. All seven OHLCV/trade-count/VWAP
fields must match at both dates within the inherited `1e-12` tolerance.
Every field is validated before an empty or mismatch result can short-circuit.

The existing requests supply three views per transition. Their earlier-asof
windows end after the earlier session, so they cannot supply the later-session
old-ticker view. Those 31 scopes form 17 deduplicated roots, grouped by asof and
comparison date. Existing empty or mismatched responses are terminal evidence
and are not scheduled for retry. A name-change path alone does not establish
bar equivalence or clear an alias gap.

## Remaining integration

The 17-root plan is unarmed: zero authorized calls in this artifact, no automatic
retry, and at most ten pages per root if a separate bounded capture is built.
The remaining work is to resolve the explicit alias/FIGI issues, derive the
scanner's previous-close map from retained split daily bars where usable, and
capture the missing full-membership split minute rank bars, candidate raw minute
and exact same-time RVOL histories, point-in-time SEC float and publication-timed
news. Frozen scanner/source adapters already exist and should be reused.

Same-date membership and coverage are bound; full historical identity continuity,
scanner runtime, paired account execution and financial evaluation remain closed.
The unchanged losing old-panel results still describe the components integrated
there, not the unfinished full hybrid strategy.

## Validation and reproduction

The 21 focused tests passed normally and with Python optimization. They cover
post-coverage CIK uniqueness, missing coverage, preserved quarantine, different
FIGIs, action order/lineage, source/date substitution, all seven alias fields,
missing versus empty views, name-change insufficiency and the unarmed query
union. One authoritative full GitHub CI run is required for the published code.

With the package installed, the provider-free CLI is:

```bash
python scripts/build_identity_coverage.py validate
python scripts/build_identity_coverage.py build --census-zip ORIGINAL_CENSUS.zip --coverage-zip ORIGINAL_COVERAGE.zip --output FRESH_OUTPUT
```

Both ZIPs must match the registered byte pins; caller-supplied provenance flags
are not accepted. `verify` can reproduce a saved panel when a concrete remaining
verification need justifies another integration build. Do not rerun the consumed
provider capture or duplicate its full hosted protocol replay as a routine step.
