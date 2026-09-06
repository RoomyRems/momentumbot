# Sealed historical Micro input acquisition v0.1

## Consumed scanner gate and unchanged hypothesis

After the user's 2026-09-06 authorization to continue development and execute
operational steps, the prepared scanner stage at local commit
`ff9736acb51dfce4d1808d10af9b634519361164` executed once against the independently
verified final v0.13 source. Its tree is identical to published preparation
commit `6aee6d31c911a60a1570091db649efac184142d7`.

Every date manifest was independently hashed and compared with the existing
`build_profile_activations` implementation. The 30 sessions contain 192
activations across 170 symbol/date pairs: 164 general-profile and 55
small-account-profile activations, with 27 exact-time profile ties. Different
first-qualification times remain separate activations. No provider was called,
Micro was not executed, and the v0.13 source tree and request ledger are intact.

The immutable 31-file result is under
`research/runtime/sealed-historical-scanner-activation-v0.2/`. Its manifest
content hash is `764354afcd61c180bc332d247f3bf2035254142006011eeb562bedda86fa704d`
and file hash is `efcfcb7575ca61d5d03c0d0a9cdb5d27348c8699c04d236e77c436024c6f51bb`.
The execution receipt is
`research/data-audits/sealed-historical-scanner-activation-v0.2-execution-2026-09-06.json`.

This child tests only whether the existing historical SIP transport can fill
the exact missing Micro input dependencies. It does not change the frozen
profiles, Micro-v0.1, account assumptions, execution cells, or management rule.
Retrospective labels and transcript values remain excluded from the runtime.

## Exact request scope

The source bundle already preserves same-session raw candidate minute bars and
split rank closes. The child reuses them. It requires 340 logical requests:

- One SIP-trade request per symbol/date, starting at its earliest frozen
  profile activation and ending before 10:00 New York time.
- One split-adjusted one-minute EMA-warmup request per symbol/date, covering the
  registered seven calendar days before that session's 04:00 New York start.

Every request uses that session's explicit `asof` identity date, ascending order,
and a page limit of 10,000. Pagination is exhausted. Because Alpaca's endpoint
end is inclusive, the wire end is one nanosecond before the frozen exclusive
boundary. No IEX substitution, current asset census, SEC refresh, news refresh,
Databento request, brokerage call, or order endpoint is available.

The request list hashes to
`8efb12cdd14496d90da1c39d8d520de0e5163203b8bc3bc201c4bcbd2317c871`.
The capture preserves normalized SIP prints with nanosecond timestamps and
condition/tape fields. Ten-second bars must later be derived by the existing
`aggregate_trade_bars` implementation; they cannot be fabricated from minutes.

Prior split-adjusted warmup prices must be normalized to the raw session price
basis before Micro evaluation, using the already frozen paired raw/split prices
available before activation. That mechanical data-basis validation is a
prerequisite for the later offline runtime; acquisition itself does not run it
or change indicator semantics. Warmup never contributes to session VWAP.

## Bounded one-shot operation

Only the existing Alpaca market-data subscription is used, with zero incremental
provider purchase. The independent child ledger permits at most 18,000 actual
HTTP attempts, including bounded transient retries, and 4,000,000,000 normalized
compressed bytes. Requests are separated by at least 0.35 seconds. The final
v0.13 30,522-request ledger is never reset, extended, or rewritten.

The workflow is dormant until the sole execution JSON is added in a separate
commit. It checks that this is the only added/changed file, binds the exact
tested parent commit/tree and workflow hash, and requires research push attempt
1. After hash-locked CPython 3.12.14 validation and complete verification of the
exact final v0.13 ZIP and source, it atomically creates the consumption ref and
uploads its receipt before the only step receiving the existing main Alpaca
market-data environment values. No dispatcher installation on `main` is needed.

The provider step can make only the derived HTTPS GET requests. Redirects,
wrong identities, records outside bounds, malformed required fields, repeated
records, and invalid pagination fail closed. Every request keeps its normalized
tape; completed requests also have content/file hash receipts. A failure retains
partial tapes, completed receipts, request accounting, and a sanitized failure
report. It is never a zero-trigger result and the workflow is not rerun.

The next prerequisite is independent verification of the captured ZIP and every
normalized tape, followed by provider-free Micro input validation and runtime.
Micro decisions must freeze before candidate-bound execution acquisition,
account evaluation, or retrospective comparison. The user's continuing
operational authorization does not remove these data and causal prerequisites.

Provider semantics: [historical trades](https://docs.alpaca.markets/us/reference/stocktrades-1)
and [historical bars](https://docs.alpaca.markets/us/reference/stockbars).
