# Databento three-case reset-repair replication v0.3

This child asks whether the unchanged v0.2 MBO reset engine that passed EQPT
also reconstructs the three remaining mechanically selected engineering cases.
It is a data-plumbing replication, not a strategy or profitability test.

## Frozen successful parent

The one-shot v0.2 Actions run `32435988929`, attempt 1, passed on EQPT. Its
sanitized artifact showed one valid unflagged session clear, 153 of 153 aligned
MBP-10 reference samples, and exact agreement among the incremental replay,
independent replay, and all ten MBP-10 price, size, and order-count levels. Raw
DBN files were deleted and never uploaded. The independently recomputed result
is preserved in
`research/data-audits/databento-microstructure-smoke-acquisition-v0.2-run-32435988929-success-2026-08-20.json`.

The v0.3 runtime imports `databento_smoke_v02.py` without modifying it and
verifies the file's frozen SHA-256 before any provider call. A changed engine
therefore fails closed before quoting or downloading data.

## Exact request and budget boundary

The registered cases are INTJ on July 10, AMC on July 20, and GMM on July 10.
For each case the workflow requests MBP-10 from 10:50–14:10 UTC and MBO from
00:00–14:10 UTC. The order is mechanical and places the least expensive case
first; it was not selected from Ross actions, P&L, or later prices.

All six requests must be successfully requoted before the first time-series
call. The observed prior quote for these exact six files was $0.182469338178
and 365,533,168 billable bytes. The hard ceilings are $0.20 and 380,000,000
bytes. Exceeding either ceiling makes zero time-series requests.

There is no workflow dispatch, rerun, retry, batch job, live subscription,
broad-history request, brokerage call, order submission, or strategy change.
Only attempt 1 of a direct push whose parent is the verified v0.2 commit
`a89f0470e4387d016600cdf7beebd09ae25b3146` is authorized.

## Gate and evidence

Each case independently applies the v0.2 G1 schema/reset/cleanup checks and G2
dual-replay plus exact MBP-10 comparison. A provider or parser failure halts the
remaining requests without retry. A completed G1/G2 mismatch remains recorded
but does not suppress the other registered cases, so the cohort cannot be
silently truncated because of an early result.

Licensed DBN files exist only in a temporary runner directory. Each is hashed,
parsed, and deleted. GitHub receives only a sanitized, non-reconstructable JSON
diagnostic containing counts, booleans, quote totals, and file hashes.

## Claim boundary

A three-case pass would show only that the frozen reset/reconstruction mechanics
generalize across the four-case engineering cohort when combined with EQPT. It
would authorize a separately preregistered causal feature-mechanics experiment,
not a trading rule. A failure is also a valid permanent result and stops that
feature work. Neither result establishes profitability, models Ross Cameron's
discretion, supplies consolidated national Level 2, or grants paper/live order
authority.
