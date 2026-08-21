# Databento microstructure feature diagnostic v0.1

## Purpose

This child carries the frozen `microstructure-feature-mechanics-v0.1` engine
into a bounded four-case real-data diagnostic without creating a threshold,
strategy decision, broker action, or profitability claim. The input cases stay
in the mechanically selected engineering order: INTJ, EQPT, AMC, and GMM.

The development bundle is deliberately unarmed. Publishing its contract,
adapter, script, tests, documentation, and workflow does not call Databento.
The workflow listens only for a future execution-authorization child that does
not exist in this checkpoint. That child must bind the exact published parent
commit and carry a new explicit user authorization before any provider call.

## Frozen parents

- Feature registration content SHA-256:
  `b048e26fabd163d66297fa57faf011fbb50d9b69377101dbd04337a1cc1eab6a`.
- Frozen feature-engine source SHA-256:
  `07e2db045c9187e4bab46e7d25c546668c2c7b8d01f78c58ec36e88e48f1628e`.
- Four-case reconstruction success-audit content SHA-256:
  `66e16d7481afceaf38dacdf78c0f1974532cdb31f24cf50252ad3c914c8338a3`.
- Verified reconstruction result: 612 of 612 aligned samples matched exactly.

The adapter refuses to run if the feature-engine source changes. The four
engineering cases cannot select a preferred one-, five-, or ten-second window,
and no retrospective Ross action, fill, P&L, recap judgment, or later price is
available to the feature replay.

## XNAS MBO normalization

The adapter follows Databento's documented XNAS normalization rather than
guessing tape direction from book changes:

- records sharing a publisher, instrument, and sequence are buffered through
  `F_LAST` as one atomic event;
- an executed visible order is normalized as `Trade`, `Fill`, then `Cancel`;
- `Trade.side` is the aggressor side and feeds the canonical tape;
- `Fill.side` is the resting-book side and is a marker, not a second mutation;
- a `Cancel` with the same order ID, side, price, and size as an in-group
  `Fill` becomes an executed removal; otherwise it remains a cancellation;
- a non-displayed `Trade` with side `N` remains explicitly unknown;
- an orphan fill marker, incomplete atomic group, undefined mutation price,
  missing required field, or unflagged receive-time reversal fails closed.

Provider record order is preserved when the translated depth and tape events
enter the feature engine. This matters when records within one native event
have increasing capture receive timestamps.

The provider sources pinned by the contract are Databento's MBO schema,
XNAS.ITCH normalization, and common side/flag conventions. XNAS is still one
Nasdaq venue, not consolidated national Level 2.

## Sampling and retained output

The replay samples the last complete `F_LAST` state in each one-second
receive-time bucket plus the final complete state. Every sample emits all three
registered windows and the fixed hypothetical order quantities 100, 500, and
1,000 shares. No causal breakout level is supplied.

The two independent feature engines must emit byte-identical snapshots. The
report retains only counts, availability totals, ephemeral file hashes, a
digest of the complete snapshot sequence, preflight quotes, cleanup status,
and authority booleans. It never retains provider records, order IDs,
instrument IDs, prices, sizes, book levels, or feature values. Temporary DBN
files are deleted before report finalization.

## Cost and execution gate

A future separately authorized attempt is limited to exactly four MBO requests:

- INTJ on July 10, 2026;
- EQPT on July 10, 2026;
- AMC on July 20, 2026;
- GMM on July 10, 2026.

Each spans `00:00:00Z` through `14:10:00Z`. The attempt must requote all four
before any download and stops with zero time-series calls unless the complete
quote is at most `$0.08` and `80,000,000` billable bytes. It cannot redownload
MBP-10, use batch or live endpoints, retry, retain raw data, change orders, or
promote policy.

The future authorization file path is:

`research/strategy/databento-microstructure-feature-diagnostic-v0.1-execution.json`

Only its first GitHub Actions attempt is eligible. Its bound parent SHA must
equal the push's `before` SHA, so an authorization cannot silently authorize a
different code revision.

## Acceptance boundary

A pass means only that the already-frozen, threshold-free mechanics execute
reproducibly on the four verified engineering streams. It does not establish a
predictive feature, a hidden-liquidity truth label, Ross-equivalent discretion,
execution quality, profitability, or generalization. A larger preregistered
walk-forward and prospective paper sequence remain required before any policy
promotion.

## Verification

The focused suite uses synthetic provider records and no network access. It
checks the exact contract and source hashes, the four-request ceiling,
`Trade → Fill → Cancel` ordering, unknown aggressor preservation, incomplete
group failure, deterministic dual replay, budget rejection before time-series
access, all-four-case cleanup, sanitized failures, registration provenance, and
the inert future-authorization workflow.
