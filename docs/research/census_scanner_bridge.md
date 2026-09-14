# Census reference and scanner-source bridge

This additive child of `21af3cd11134f9cd581d1200d8a2fe697adaa589` translates
the completed 30-date census into the existing universe and identity contracts.
It tests one question: can the exact source yield a complete reference inventory
and coverage handoff without inventing market coverage or historical continuity?
No prices, transcripts, Ross actions, outcome labels or account replay enter it.

## Implemented behavior

The reader requires the original 30,807,928-byte ZIP with SHA-256
`38d772b2017c159050c4cef2a678a79af1fd61f243e8131f5112d1ef25b09ded`.
It verifies the independent hosted result and inventory commitments and checks
every original member's bytes. It reuses the already successful hosted protocol
replay instead of repeating that full validation or recapturing the provider.
Each day retains its source hash and every canonical ticker disposition.

The unchanged `classify_ticker_group` receives **absent coverage**. A qualifying
metadata record therefore remains `coverage_record_missing`, never an invented
included security. Only metadata failures that the frozen classifier determines
before inspecting coverage are removed from the future coverage request union.
Identity quarantine is not used to remove coverage requests.

The existing FIGI/unique-CIK rule supplies provisional same-date identities.
It does not prove 120-day continuity, ticker changes, split history, or historical
float ownership. The coverage adapter later reruns the original classifier and
recomputes CIK uniqueness on the post-coverage membership. Its input binds the
exact date and reference hash, requires a complete ticker population, strict
booleans, and internally consistent coverage observations. It emits the existing
resolved membership fields and scanner symbol list while leaving historical
execution disabled. Caller-supplied coverage hashes do not authenticate a vendor;
raw-source/provenance and corporate-action checks remain required downstream.

## Results over the frozen census

All counts below are ticker/date references, not independent securities.

| Result | Count |
|---|---:|
| Original membership rows retained in source | 373,710 |
| Canonical ticker/date dispositions | 373,650 |
| Metadata candidates requiring daily coverage | 165,989 |
| Provisional Composite FIGI identities | 136,814 |
| Provisional unique-CIK fallback identities | 28,984 |
| Provisional identity quarantines | 191 |
| Outside common-type family | 204,240 |
| Explicit instrument-name conflicts | 3,020 |
| Instrument-structure review | 401 |

`BCPC` and `TPC` each have two source records on every date. Their common-stock
records satisfy the existing metadata screen; the other records are a different
debt/preferred instrument. Both originals remain in the exception witnesses.
There is no symbol-specific exception or arbitrary duplicate selection.

The missing March 6 type belongs to `TDOT`. Its missing type remains explicit;
neither its name nor later records supply a fabricated historical code. The
current type dictionary has no historical identity authority.

The new unarmed daily-coverage request inventory has **1,380 initial requests**:
23 batches per date, two adjustments, all 30 dates. It uses the inherited
14-calendar-day UTC lookback through next-day midnight, target-date `asof`, SIP,
raw/split daily bars and batches of at most 250 symbols. This is an exact initial
request population, not a total HTTP ceiling: pagination, safe transport,
resource limits and capture provenance still need integration before execution.
No request, subscription change or charge was made by this step.

## Verification and reproduction

All 47 focused tests pass normally and with assertions disabled, including 30
new bridge tests and 17 existing universe/identity tests. Compilation passed.
Tests cover complete accounting, generic ticker collisions, metadata conflicts,
missing identifiers, post-coverage CIK uniqueness, date/reference substitution,
missing versus failed coverage, raw/split disagreement, future/label fields,
scope/type validation, exact batch unions and original-source admission.

Initial development checks caught the use of a JSON equality helper on Python
sets and tests expecting the wrong exception class. Those were corrected before
source interpretation; the failed development log is retained. Review then
tightened the coverage envelope's date/reference binding. Both source builds
used only fixed reference metadata; no policy threshold or result selection
changed. The final source build ran with Python assertions disabled.

Registration: `f82cf8963e80aea47d27d8c72004d06ca3886cd39de8a513d766617ee7a728d2`.
Panel content: `307c42e4fbfe63967cba943796f13aaa0f836fd7f7fc35f1ef1e925df4c8dcc8`.
The compressed panel, source exceptions, initial request inventory, summary and
logs are in `research/data-audits/early-pullback-census-scanner-bridge-v0.1/`.
The ZIP source remains GitHub artifact `10306971164`, currently expiring
December 11, 2026. No retention beyond that date is claimed.

```bash
PYTHONPATH=src python -O scripts/build_census_scanner_bridge.py build \
  --census-zip /absolute/path/to/original-10306971164.zip \
  --output /absolute/path/to/new-output-directory
```

Next integrate bounded, provenance-preserving daily coverage and 120-day
identity/corporate-action sources, then populate the frozen cross-sectional
scanner inputs. The earlier losing baseline and first-two selection experiment
remain unchanged. Crucial discretionary/context integration is still unfinished;
this reference-data result makes no financial-performance claim.
