# Databento MBO reset repair smoke acquisition v0.2

This child tests one data-plumbing correction after the frozen v0.1 failure. It
does not tune or promote a strategy.

## Why v0.1 failed

The independently verified v0.1 run downloaded and cleaned up all 20 exact
files, but G1 and G2 failed. Each MBO case contained one valid `cleaR` action
and zero clears carrying `F_SNAPSHOT`. The v0.1 implementation required both a
snapshot clear and a later non-snapshot `F_LAST`, so every book remained
unready and no MBO-to-MBP-10 comparison occurred. This is not evidence that
the reconstructed books disagreed; they were never compared.

The failure is preserved in
`research/data-audits/databento-microstructure-smoke-acquisition-v0.1-run-32427326070-failure-2026-08-20.json`.

## Frozen hypothesis and cost boundary

The v0.2 hypothesis is that an MBO request beginning at the UTC session
boundary may initialize an empty book from a valid first `cleaR` action even
when `F_SNAPSHOT` is absent. The clear event, or the next non-snapshot event,
must close with `F_LAST` before the book becomes eligible for comparison.

Only EQPT on July 10 is authorized. It was the cheapest informative v0.1 case
and had 153 mechanical MBP-10 reference samples. The workflow requotes and, if
the quote passes, downloads exactly two files: MBP-10 from 10:50–14:10 UTC and
MBO from 00:00–14:10 UTC. The observed v0.1 quote was $0.005820024014 for
10,810,592 billable bytes. The hard preflight ceilings are $0.02 and
15,000,000 bytes. Exceeding either ceiling makes zero time-series requests.

There is no batch job, live subscription, broad-history request, or automatic
retry. Only the first Actions attempt of the direct push from branch head
`2754a33d2a7deecac6aca7aa7c8cd1ba7c854b98` is authorized.

## Reset and comparison semantics

The first observed action for every publisher/instrument book must be a valid
clear: side `N`, undefined price, zero size, and zero order ID. A snapshot clear
still requires a later non-snapshot `F_LAST`. An unflagged session-boundary
clear becomes ready on its own `F_LAST` or the next non-snapshot `F_LAST`.
Every later valid clear empties both independent books, removes readiness, and
requires a new qualifying `F_LAST` before comparison resumes.

MBP-10 references and MBO sequence alignment remain unchanged from v0.1. Two
independent order-book implementations must agree with one another and exactly
match all ten MBP-10 levels for price, size, and order count at every aligned
sample. At least 95% of the mechanical MBP-10 samples must align.

## Data and claim boundary

Licensed DBN files exist only inside a temporary runner directory. They are
hashed, parsed, deleted, and never committed or uploaded. The retained report
contains only sanitized non-reconstructable counts, booleans, quote totals, and
file hashes.

A pass establishes only that this reset interpretation supports exact replay
for one EQPT session on single-venue Nasdaq depth. A failure is preserved and
stops before any four-case expansion. Neither outcome establishes strategy
profitability, models discretionary trading, represents consolidated national
Level 2, changes Micro-v0.1, or creates paper/live order authority.
