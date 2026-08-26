# Prospective daily scanner/Micro source v0.1

## Purpose

This child registers the missing causal producer upstream of
`prospective-opportunity-freeze-v0.1`. On each of the ten already frozen
August 24–September 4, 2026 sessions, it emits one account-neutral decision
source containing every unchanged Micro-v0.1 chart trigger reached by the
union of `current-general-2026` and `current-small-account-2026`.

The frozen checkpoint parent is
`8f8faf3ab551e6774ad677a842cea87ccb183238`, with tree
`e70f3adfc628cb053af14a1355035325b03ccf8b`. The single hypothesis is
mechanical: a current pre-session membership reference and same-session market
responses are sufficient to reproduce the registered scanner/Micro decision
boundary without account scarcity, execution assumptions, fills, exits,
retrospective labels, or later outcomes selecting a row.

## Two-phase causal boundary

The pre-session phase runs at 05:30 New York time and must finish by the 07:00
strategy start. It freezes the current Alpaca US-equity asset census and the
current SEC ticker/CIK/exchange crosswalk. Current reference data is not
misrepresented as a historical asset master: a fresh same-date prerequisite is
required on every panel date, and the post-session phase must check out the
exact full code SHA recorded by that artifact.

The post-session phase starts at 10:20 New York time, after the registered scan
window closes. It may download the date's provider responses in one
reconstruction pass, but each scanner state and Micro trigger is evaluated only
from information causally available at its timestamp. Later records are absent
from the applicable runtime-prefix hash and cannot select a candidate or
trigger.

A missing prerequisite, a provider failure, a rejected frozen membership
symbol, missing required scanner evidence, or missing SIP trades for an
eligible candidate fails the date. None is converted into a zero. A member
whose daily scan basis is absent may be excluded only after separate raw and
split SIP one-minute normalized responses both contain that symbol and both
are empty from 04:00 through 10:01 New York. Both query passes also include one
deterministic positive-control member whose earlier discovery had a valid
same-date daily scan basis; its raw and split minute frames must be nonempty
and have the same bar count. Thus a successful-but-provider-wide-empty
response cannot become a zero, while a day with no member above the broad
acquisition threshold can still be resolved. A genuinely complete date with
no broad candidates or no Micro triggers is retained as an explicit
zero-decision source.

## Union scanner semantics

The acquisition superset covers $1.50 through $20.00, at least 10% gain, and
same-time relative volume of at least 5. It has no top-N filter. The daily-bar
high through the deterministic 10:01 New York historical-data boundary is used
only to avoid downloading obvious non-candidates; it is never a strategy
feature. Any symbol that qualified before the 10:00 entry cutoff necessarily
intersects this bounded acquisition superset.

After reacquiring the exact rank inputs across the complete frozen active
membership, the producer finds the first qualifying minute separately for each
registered profile. A symbol that first satisfies the small-account profile
later than the general profile therefore retains both causal activations.
Profiles first qualifying in the same minute are unioned into one activation.
Point-in-time float evidence is fixed at the broad activation, provider news is
projected only when `published_at` is no later than the decision, and every
candidate-minute scanner disposition is preserved.

## Micro decision semantics

Each activation uses the unchanged Micro-v0.1 policy, completed 10-second bars,
and completed one-minute VWAP/EMA support. The retained decision is the first
chart-price-eligible normalized SIP trade event that crosses the trigger inside
an armed plan window. The source stops there.

It does not simulate a quote, order, fill, partial fill, cancellation, halt
response, exit, P&L, or account quantity. A trigger eligible for both profiles
is emitted once with the non-empty eligible-profile union. Its causal prefix
hash binds the activation, policy, plan, completed bars and support, and SIP
trades through that trigger only.

## Outputs and workflow

The post-session output directory is write-once and contains:

- `scanner-runtime.json`;
- `micro-trigger-runtime.json`;
- `prospective-daily-micro-decision-source.json`; and
- `producer-manifest.json`.

`.github/workflows/prospective-daily-source.yml` provides provider-free push
validation plus the two registered schedules. The 05:30 phase uploads the
same-date prerequisite for 90 days. The 10:20 phase retrieves the latest valid
same-date prerequisite, checks out its exact code SHA, produces the source,
retains it for 90 days, and dispatches the frozen opportunity materializer on
`phase-3-historical-snapshot`.

The scheduler and the dispatched workflow entry must both exist on the default
branch because GitHub schedules and `workflow_dispatch` are discovered there.
Their runtime code and frozen contracts remain on the research branch.

### August 25 operational repair

The first production attempt on August 25 failed closed before emitting a
source because the daily-bar acquisition windows ended at the following UTC
midnight. On the same trading date that timestamp was still in the future, so
Alpaca rejected the explicit SIP query under the existing delayed historical
entitlement. The provider credentials and pre-session prerequisite were valid.

The mechanical repair keeps the SIP feed and every registered threshold,
profile, decision cutoff, Micro rule, and account boundary unchanged. It binds
all same-date historical SIP daily-bar reads to the existing deterministic
10:01 New York acquisition boundary and enforces the registered 10:20
production start so that bound is more than 15 minutes old. Any post-cutoff
daily high admitted by that one-minute acquisition tail remains a superset-only
download filter and never enters a scanner feature. The August 25 attempt
remains a failed panel date; it is not rerun or reclassified as a
zero-opportunity date. The repair first applies to the next normal registered
session.

### August 26 operational repair

The August 26 first-attempt source run failed closed after consuming its valid
same-date prerequisite. Alpaca's active and tradable census included `AAAA`,
an exchange-traded fund for which the discovery response lacked the combined
target-day/prior-close daily scan basis. The shared discovery audit correctly
retained that ambiguity, but the prospective completeness check treated every
missing basis identically. It therefore could not distinguish a member with no
target-session activity from a target-active member missing the required
split-adjusted prior close.

The prospective-only repair leaves the shared historical discovery contract
unchanged. For only the members with a missing daily basis, it makes one raw
and one split SIP one-minute query pass over the already bounded 04:00--10:01
New York window. Each pass also includes the alphabetically first independent
member whose initial discovery had a valid same-date daily scan basis. The
normalized response maps must contain the complete requested set; the
positive control's raw and split minute frames must be nonempty with equal bar
counts. A missing-basis symbol is retained as an explicit
audited noncandidate only when both of its frames are empty. The sanitized
resolution ledger records counts and hashes the complete query set; it retains
no bars or provider messages. If either target frame contains activity, the
frames disagree, a normalized response omits a symbol, no positive control is
available, the positive control fails, the provider rejects a symbol, or a
provider call fails, the date still fails closed. A later rank reacquisition
must also remain empty for every confirmed inactive member.

The repair does not blacklist `AAAA`, filter membership through the SEC
crosswalk, alter security-type policy, change a scanner threshold, change
Micro-v0.1, or reinterpret August 26 as a zero. Run `32986285404`, attempt 1,
remains the sole failed source attempt for that date and is not rerun. The
repair first applies to the next normal registered session.

## Authority and registration status

The producer authorizes only read-only use of the existing Alpaca market-data
subscription and public SEC endpoints. It creates no broker account read or
write authority, submits no paper or live order, and authorizes no incremental
purchase. It makes no Databento quote or request and authorizes $0 of Databento
credit.

At registration, the pre-session, daily-source, and dispatched-freeze runtime
counts are all zero. No provider data was read to create the registration. The
first operational gate is the August 24 pre-session prerequisite; its source
and freeze artifacts must be preserved before any separately authorized quote
or acquisition work.

Files:

- Contract: `research/strategy/prospective-daily-scanner-micro-source-v0.1.json`
- Mechanics: `src/momentumbot/research/prospective_daily_source.py`
- CLI: `scripts/build_prospective_daily_source.py`
- Workflow: `.github/workflows/prospective-daily-source.yml`
- Registration audit:
  `research/data-audits/prospective-daily-scanner-micro-source-v0.1-registration-2026-08-22.json`
- Tests: `tests/test_prospective_daily_source.py`
