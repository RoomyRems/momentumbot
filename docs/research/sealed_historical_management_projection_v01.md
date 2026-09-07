# Causal historical management mechanics v0.1

## Frozen parent and scope

This isolated child binds audited checkpoint
`f4a8d98b5ff780a4138ed4eb5628423891e4818d`, tree
`bf3e9dfe4c2d89f5f482f2d0701d8499d6508858`, and the independently verified
management-input freeze commitment
`df00c1aa3e66fbb3040e63df210ef71ead7518858f5bc3ff44fc59067eeb15de`.

The single hypothesis is that the frozen external-fill management legs can be
reproduced with completed-bar causality and exact source lineage. This is a
mechanics registration with synthetic tests, not a historical projection,
account replay, execution trial or policy promotion. No captured price tape is
reopened in this stage. Ross transcripts, fills, actions, recap labels and
retrospective outcomes remain sealed. No provider calls, purchases, brokerage
access, orders, new consumption tags or account seed changes are authorized.

## Descriptive causal primitive

`project_external_fill_proxy` preserves `half-2r-breakeven-first-red-1m` from
the existing `simulate_external_fill_management`. Its external-fill arguments
are explicitly **unverified**: the function cannot select an entry or certify
that an input-available opportunity actually filled. Historical use requires a
separately frozen runner binding an independently verified single accepted
entry, original stop, path, scenario, symbol, session and fill receipt to the
verified `ManagementInputBundle` reader. Multiple-entry/add campaigns remain
unsupported. The CLI exposes metadata registration/build/verification only.

All timestamps stay exact integer nanoseconds. Original opportunity windows
remain 900 seconds plus the 60-second observation tail; a merged later window
cannot extend an earlier opportunity. Records retain original artifact,
request and source ordinals, composed ordinal and a canonical-row commitment.
Source streams are validated without sorting or deduplication. Equal-time SIP
prints preserve source order. Prints at the external fill timestamp are all
excluded; the first eligible print must be strictly later.

Price eligibility is the frozen Micro rule, including otherwise clean odd lots
and fail-closed unknown/disqualifying conditions. No extra size filter is
introduced. Raw minute bars become signals only at bar start plus 60 seconds,
strictly after the fill and no later than signal-window end. The first completed
red bar remains pending until an eligible SIP print is observed.

At each eligible print the priority is active stop, completed first red minute,
then first 2R target. The target retains existing floating-point arithmetic and
10-place rounding. A target proxy realizes fraction 0.5 at the target price,
even when the observed print gaps beyond it; both prices and source evidence
are retained. Only the descriptive stop moves to entry. A stop/red proxy exits
the remaining fraction at the observed print. Repeated target touches cannot
create additional legs. Empty or unfinished paths remain open; there is no
end-of-data liquidation.

The existing tail behavior is preserved: stop/target observations may occur in
the 60-second tail, while new bar signals remain capped at signal-window end.
Decision state stops at a terminal proxy exit. Unlike the old precomputed
diagnostic field, a red bar completing *after* that exit is omitted from the
new terminal metadata. This changes no exit leg, fraction, target or stop.
Full-envelope source-integrity validation is distinct from causal decisions.

These are fractional transaction proxies, not executable whole shares, sell
orders, fill confirmations, fees, cash, P&L or account-close evidence. SIP
event-time and bar-close timing are historical proxies, not measured SIP
receive times or bar-publication latencies.

## Conditional executable-exit requirements

`conditional_exit_envelope` is an unbound calculation, not a request or an
executable decision. Existing `XNAS.ITCH` `mbp-1`/`status`, `raw_symbol`, native
receive-time/sequence/original-ordinal ordering and fail-closed status/tie
rules are preserved. Conditional quote bounds are
`[decision - 100,000,000 ns, decision + 550,000,001 ns)`; status starts at
that date's UTC midnight. The extra nanosecond preserves the frozen capture
adapter's inclusive final observation. Actual execution still uses its
unchanged cancel-ack boundary. If the required end exceeds the original
opportunity end, the requirement is unavailable/censored, not extended.

Both existing scenarios use the same evidence:

| Requirement | Conservative | Stress |
|---|---:|---:|
| Decision-to-arrival | 100 ms | 250 ms |
| Maximum quote age | 100 ms | 50 ms |
| Cancel after arrival | 250 ms | 150 ms |
| Cancel acknowledgement | 100 ms | 150 ms |
| Displayed-size participation | 25% | 10% |
| Sell-limit offset from known bid | 5 ticks | 2 ticks |

The tick remains $0.01. A limit needs a causal, fresh decision-reference bid;
SIP target prices cannot substitute for it. Existing first-eligible-state,
one-use liquidity and cancel-remainder mechanics are dependencies, not a newly
implemented executable exit engine. No native request IDs or actual request
list are generated here; scope and any missing quote/status evidence need
separate registration, cost verification and acquisition authority.

Before executable management, unresolved bindings must be registered: whole-share
half-target rounding and one-share behavior; confirmed target-fill feedback
before executable breakeven activation; partial fills, cancellation, retry and
competing exits; cross-order liquidity/share conservation; causal signal-to-order
clock handling; historically applicable fees (not automatic use of a 2026
prospective schedule); confirmed sell-ledger and session handoffs. A target
touch alone proves none of these.

## Population, reproduction and next gate

The four metadata documents preserve all 109 original opportunity identities
and bounds, 86 available and 23 unavailable entry inputs with unchanged reasons,
30 dates including five no-decision dates, 12 account paths, 360 session slots
and 744 profile/scenario opportunity references. Availability does not imply a
confirmed entry. Once-only seeds and prior-close dependencies remain unchanged.
Historical projection and executable request counts are both zero; every
historical execution, management, account and financial-metric gate stays false.

Registration: `research/strategy/sealed-historical-management-projection-v0.1.json`.
Metadata: `research/runtime/sealed-historical-management-projection-v0.1/`.
The hash-locked environment and read-only hosted workflow reconstruct exact
metadata bytes offline and run synthetic mechanics/dependency tests normally
and optimized. The CLI installs the external-I/O denial hook before imports.

```bash
python scripts/build_sealed_historical_management_projection_v01.py --validate-registration
python scripts/build_sealed_historical_management_projection_v01.py --verify
```

`--build` is for an absent output only; existing evidence is never overwritten.
Next: bind verified confirmed-entry receipts and register executable management
fill feedback before historical projection or exit-data capture. This child
does not authorize either operation. Causal next-session valuation and account
replay remain later dependencies.

## Local verification

All 1,767 tests passed with zero skips. The 90 focused tests passed normally
and with Python optimizations enabled, including 43 new tests. They include
120 seeded synthetic-path comparisons against the frozen external-fill engine,
all frozen condition singles/pairs across all three SIP tapes, exact timestamp
ties, tail edges, source lineage, invalid inputs and write-once metadata.
Static undefined-global checks passed for the module and CLI.

An independent stdlib-only checker verified all four metadata files, every
original opportunity field and date, exact nanosecond bounds, all 744
profile/scenario references and availability reasons, the literal parent
commitments and every closed runtime gate. The registration freeze content
commitment is
`0fef2f3bf29a3439dfa07d58a8fa189294f533197f53d70bc7939e186280960d`.
Hosted verification is the remaining publication check.
