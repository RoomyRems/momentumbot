# Alias completion and saved scanner daily inputs

Child of `3397cf7051410d0e39a4a7ba367eb9eef5748768`, registered as
`early-pullback-alias-completion-v0.1`. The owner's September 15 “Okay go ahead”
continues the bounded identity/alias work. Strategy thresholds, membership rules,
account mechanics and dates are unchanged. No transcript labels, recap actions,
fills or evaluation outcomes are used. AI remains shadow-only.

## Saved-source preparation

The original accepted census/identity panel and coverage ZIP were reused offline.
All 165,694 accepted ticker/date memberships have a positive latest-prior-session
split daily close. No symbol is missing a previous close and no provider request
was made. `saved-scanner-daily.json.gz` retains the map for every date, exact dated
membership seals, individual bar timestamps and original body/request/root lineage.
Its content seal is
`3244c96952a5864217eefdcc7577793eb97b8ba8b8391c7c8b65ace8c0474f87`.

The scanner ordinarily requests 21 calendar days. The exhausted retained 14-day
window already contains each latest prior observation; adding seven older days
cannot change that last observation. Target-session closes are excluded, and a
zero last close is unavailable rather than replaced by an older positive value.
Focused tests compare this projection with the frozen scanner helper, including
ordering, timezone, duplicate and missing-value behavior. No split factor is
reapplied and no raw/split gain basis is mixed.

## Exact bounded capture

The prior 31 missing changed-ticker views remain in scope. The four diagnosed
same-ticker/different-FIGI cases need one additional view each: FWDI, BBUC, SNTI
and DMRC. Their comparison dates already occur in the existing 17 request roots,
so adding four symbols does not add any request root. There are 35 missing views
and 105 reusable views across the 35 four-view checks. All 35 earlier-date
comparisons already match.

Requests preserve the earlier asof mapping and later comparison date, raw daily
SIP bars, seven-day query windows and the original seven-field alias comparison.
The exact request union is file-bound in the registration. It cannot become a
new symbol/date search or a retry of captured empty/mismatched observations.

| Bound | Value |
|---|---:|
| Initial roots | 17 |
| Missing symbol/asof/date views | 35 |
| Maximum pages per root | 10 |
| Maximum HTTP attempts | 170 |
| Maximum capture duration | 15 minutes |
| Payload / metadata ceilings | 48 MiB / 16 MiB |
| Minimum request-start interval | 350 ms |
| Retries / redirects | 0 / 0 |

The implementation reuses the original daily parser, safe retention, pacing,
transport and capture report/receipt schema. The smaller child budgets are
enforced before transport and by its output store. Only the two Alpaca secrets
are read, only in the capture job. The frozen transport's unused third credential
field receives a public placeholder; the Massive endpoint is explicitly forbidden.

The reusable hosted gate requires successful full CI for the exact new code,
push attempt 1 on the active branch, a clean checkout with the registered parent,
a separate create-only consumption tag, independently retained preflight and
matching artifact provenance before credentials. Authority expires September 22.
The existing bounded diagnostic authorization is used; no subscription, metered
purchase or new data product is authorized. Incremental API cost is estimated at
zero under the existing account; actual entitlement/billing is not asserted.

## Identity disposition and completed handoff

`conflict-source-views.json` preserves original FIGIs and the 12 captured conflict
views. Captured interval actions include a FWDI name change, BBUC stock-merger
records and a DMRC stock merger; none was found for SNTI in its interval. Those
are source observations, not proof that different security identifiers are
equivalent. Every dated FIGI is retained. Neither matching bars nor a corporate
action authorizes merging identifiers or joining histories across them.

The independent verify job checks the original capture ZIP, inventory, every
request/receipt, pacing, daily-page exhaustion and exact report reproduction.
It then fills exactly the missing views in the immutable prior checks and writes
`completion.json`, binding the verified alias results and saved scanner daily
inputs. Empty observations and mismatches remain explicit failed comparisons.
Successful source capture alone does not imply successful identity comparisons.

The handoff preserves all 188 prior identity quarantines and 107 coverage failures.
Remaining scanner inputs are full-membership split minute rank bars, candidate
raw minute and exact same-time RVOL histories, point-in-time SEC float and
publication-timed news. The completed daily map should be reused. Full scanner,
account and financial evaluation gates remain closed until their inputs are ready.

## Verification record

The focused suite contains 24 tests, including a complete synthetic 17-root
capture/original-ZIP replay and composition with the saved dated source handoff.
Normal and optimized test logs and source-preparation progress are retained with
the audit. Published code `e9cc035bf7b9d2fdb05b0380e0d1e5fd8911b487`
passed full CI `34926971450`: 2,964 tests in 475.272 seconds, 73 optional
skips and successful compilation. Capture run `34926971484` completed all
consume/capture/verify jobs and every step successfully on September 15.

The capture completed all 17 roots in 17 requests, without retries. All 31
changed-ticker checks and all four distinct-FIGI price-view checks match in
both directions. All 165,694 previous closes are ready, with none missing.
Different dated FIGIs remain separate; no membership or policy was changed.

The original consumption, capture and verification ZIPs are retained in the
audit directory with terminal metadata, exact extracted hosted proof and
completion report. `completion-verification.json` binds their archive hashes,
all 54 capture members, successful same-code CI and the completion seals.
The initial local whole-object metadata comparison failed solely because the
plugin's normalized metadata omits the hosted `node_id`; every other field
matches exactly. This diagnostic is preserved in the completion record.
The successful hosted replay was not duplicated and no provider calls were
made during local evidence checks. The permanent consumption tag remains
bound to the code above; this capture must not be rerun.
