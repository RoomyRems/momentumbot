# Databento safe failure classifier v0.2

## Purpose

The first authorized `databento-microstructure-feature-diagnostic-v0.1` run
failed safely on its first INTJ MBO request. The retained artifact proves that
the four-request preflight passed and exactly one time-series request began,
but v0.1 combined download, file validation, metadata validation, parsing,
normalization, feature replay, and snapshotting behind one `ValueError`
boundary. Because the exception text was correctly discarded, the exact guard
that rejected the stream is not recoverable from that artifact.

This v0.2 child repairs observability only. It leaves the v0.1 adapter and the
threshold-free feature engine byte-for-byte frozen, repeats no provider call,
and creates no strategy, threshold, broker, or runtime authority.

## Permanent parent evidence

The independently verified failure is frozen in
`research/data-audits/databento-microstructure-feature-diagnostic-v0.1-run-32444174639-failure-2026-08-20.json`.
It binds:

- GitHub Actions run `32444174639`, attempt 1;
- workflow head `3efee47b6daf8e27e1ea033da4393caecf237543`;
- artifact `9433488265` and its verified ZIP and report digests;
- a passed preflight of `$0.072135579586` and `64,545,824` bytes;
- exactly one attempted time-series request and no retry;
- no retained or uploaded raw market data; and
- an unresolved `ValueError` in the combined INTJ download-or-extract stage.

The earlier v0.3 reconstruction remains relevant engineering evidence: the
same INTJ request contained 2,090 structurally valid MBO records and matched
59 of 59 independently reconstructed MBP-10 samples. That makes a generic
provider-envelope or ordinary book-reconstruction failure less likely, but it
does not identify the v0.1 guard. Changing semantics now would be guesswork.

## Stage-separated classifier

The child evaluates the same frozen INTJ request through explicit boundaries:

1. preflight quote and hard budget;
2. provider download;
3. nonempty temporary file;
4. dataset and schema metadata;
5. required record fields and receive-time ordering;
6. publisher/instrument/sequence atomic grouping through `F_LAST`;
7. action, side, mutation, and exact Fill/Cancel normalization;
8. canonical book/tape replay;
9. threshold-free feature snapshots; and
10. frozen dual-replay completion checks.

Failures retain only an allowlisted phase, an allowlisted code, and an optional
normalized exception class from a fixed enum. Exception text, tracebacks,
paths, record indices, IDs, prices, sizes, credentials, raw values, and message
hashes are prohibited. Unknown failures become `unclassified_fail_closed`.
The classifier never weakens an invariant to force a pass.

## Unarmed publication gate

Publishing this child cannot call Databento. Its workflow listens only for a
future file that is intentionally absent:

`research/strategy/databento-microstructure-feature-diagnostic-v0.2-execution.json`

A later authorization must bind the exact published parent SHA and explicitly
authorize one first-attempt INTJ MBO request. The workflow also requires that
the authorization be the only changed file in a single direct-child commit.
Even then, the run must requote before downloading and stop with zero
time-series calls unless the quote is at most `$0.001` and `1,000,000`
billable bytes. Automatic retry, MBP-10
redownload, batch/live endpoints, raw-data publication, threshold selection,
strategy changes, and broker actions remain forbidden.

## Interpretation boundary

A classified failure identifies the next code-only repair target. A successful
replay means only that the prior failure was not reproduced under the same
frozen mechanics. Neither result is evidence of predictive value,
Ross-equivalent discretion, execution quality, profitability, or policy
fitness. Real-data feature evaluation still requires a preregistered cohort,
held-out comparison, calibrated execution assumptions, and prospective paper
trading before any promotion decision.

## Verification

The deterministic suite uses synthetic records and fake provider clients only.
It proves the child is unarmed, the frozen sources remain unchanged, early
authorization gates touch no SDK or client, the provider is called at most
once with no retry, temporary data is removed, v0.1/v0.2 success metrics are
identical, atomic and Fill/Cancel failures map to fixed codes, and contaminated
exception strings cannot reach a report.
