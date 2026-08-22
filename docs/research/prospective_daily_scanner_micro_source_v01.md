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
eligible candidate fails the date. None is converted into a zero. A genuinely
complete date with no broad candidates or no Micro triggers is retained as an
explicit zero-decision source.

## Union scanner semantics

The acquisition superset covers $1.50 through $20.00, at least 10% gain, and
same-time relative volume of at least 5. It has no top-N filter. Full-session
high is used only to avoid downloading obvious non-candidates; it is never a
strategy feature.

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
