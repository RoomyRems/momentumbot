# Prospective market-input metadata quote v0.1

## Purpose

This child prepares the metadata-only availability and cost gate that follows a
successful prospective opportunity freeze. It remains unarmed at registration:
no future opportunity bundle exists yet, no exact authorization has been
created, no Databento credential has been loaded, and no provider method has
been called.

The frozen parents are `prospective-opportunity-freeze-v0.1` at checkpoint
`8f8faf3ab551e6774ad677a842cea87ccb183238` and
`prospective-market-input-capture-v0.1`. Micro-v0.1, the account panel, both
execution scenarios, management rules, and the previously consumed real-data
workflows remain unchanged.

## Exact parent-bundle gate

A future quote can begin only from the three immutable files emitted by the
opportunity-freeze workflow:

- `opportunity-manifest.json`;
- `request-manifest.json`; and
- `freeze-manifest.json`.

The validator recomputes all three content fingerprints, rejects retrospective
fields, verifies the registered trading date, and deterministically re-derives
the complete request manifest from the frozen opportunities. It then checks the
freeze manifest's source, opportunity, request, count, zero-date, provider-free,
and no-order bindings. The original daily decision source is not silently
reconstructed or replaced; its frozen hash remains explicit in the bundle.

For each opportunity-bearing symbol-date, the bundle must still contain both
registered `XNAS.ITCH` rows: one `mbp-1` request and one `status` request. A
valid zero-opportunity date contains zero requests and remains a successful,
explicit not-applicable quote result with zero provider calls.

## Separate dynamic authorization

Registration does not authorize a quote. After a real bundle is preserved, the
provider-free `authorize` command can create a deterministic child bound to:

- this contract hash;
- the daily source, opportunity, request, and freeze hashes;
- the registered trading date and exact request count;
- the same-repository freeze workflow run, run attempt, and artifact name; and
- at most two metadata calls for every exact request.

That future file permits only
`historical.metadata.get_billable_size` and
`historical.metadata.get_cost`. It is valid only on the first attempt of one
manually dispatched quote workflow and cannot be reused or retried. It grants
no Databento credit, time-series request, batch job, live subscription, raw-data
persistence, request selection, broker action, or policy authority.

## Sanitized quote behavior

The quote runner visits every request in deterministic manifest order and
attempts the two permitted metadata methods for each row. It never exposes a
time-series, batch, live, symbology, or broker client surface. Nanosecond request
boundaries are converted exactly to RFC 3339 without floating-point rounding.

The retained report contains one small row per exact request: request identity,
schema, billable byte estimate, quoted cost, completeness, and availability.
Provider exception messages and credentials are discarded. If either method
fails, aggregate totals are `null` rather than presented as complete. A zero
billable size marks that exact request unavailable and does not permit another
symbol, venue, schema, or time window. A quote report never authorizes a
download.

## Workflow boundary

Pushes to the research branch run only provider-free tests and compilation. A
provider quote can run only by manual dispatch with a full authorization commit
SHA, exact authorization path, and exact successful freeze run provenance. The
workflow checks out that commit, validates that it belongs to the research
branch, downloads the named immutable freeze artifact, pins Databento SDK
`0.83.0`, and exposes `DATABENTO_API_KEY` only to the final quote step.

Successful quotes and sanitized provider failures are retained for 90 days.
The workflow fails its final gate unless all nonempty exact requests are
available; a valid empty request bundle passes as explicitly not applicable.
Neither result selects a horizon or execution scenario.

## Registration result and next gate

This registration created and tested only the unarmed harness. It created no
per-date authorization and ran no Databento quote. After the first successful
prospective opportunity freeze, independently verify the bundle, create exactly
one hash-bound authorization, publish it as a separate child commit, and run at
most the first manual workflow attempt. Any later `mbp-1` or `status` download
requires another bounded authorization and must preserve unavailable inputs
without SIP substitution.

Files:

- Contract: `research/strategy/prospective-market-input-metadata-quote-v0.1.json`
- Mechanics: `src/momentumbot/research/prospective_market_input_quote.py`
- CLI: `scripts/quote_prospective_market_inputs.py`
- Workflow: `.github/workflows/prospective-market-input-quote.yml`
- Tests: `tests/test_prospective_market_input_quote.py`
