# Prospective market-input acquisition v0.1

## Purpose

This child registers the missing exact-download boundary between a successful
prospective metadata quote and the provider-neutral market-input capture. It is
unarmed at registration: no per-date acquisition authorization exists, no
Databento credential has been loaded, no provider call has been made, and zero
Databento credit is authorized.

The frozen parents are `prospective-opportunity-freeze-v0.1`,
`prospective-market-input-capture-v0.1`, and
`prospective-market-input-metadata-quote-v0.1`. Micro-v0.1, the ten-date account
panel, both account scopes, all three behavioral horizons, both execution
scenarios, and every management rule remain unchanged.

## Exact successful-quote gate

An acquisition authorization can be built only after validating all of the
following together:

- the exact three-file opportunity-freeze bundle;
- the exact metadata-quote authorization that names the successful freeze run;
- the exact sanitized metadata-quote report from its first workflow attempt;
- complete availability for every frozen `XNAS.ITCH` `mbp-1` and `status`
  request; and
- recomputed content hashes throughout the source, freeze, quote, and request
  chain.

An unavailable, partial, rehashed, substituted, or failed quote cannot create
download authority. A valid zero-opportunity date remains explicit and creates
an authorization with zero metadata and zero time-series calls.

## Separate dynamic authorization

The provider-free `authorize` command creates one deterministic child bound to
the successful quote report, quote authorization, daily source, opportunity
manifest, request manifest, freeze manifest, repository, registered date, and
named immutable quote artifact. Its cost and byte ceilings equal—not exceed—the
successful quote totals. Its call ceilings are exactly two metadata re-quote
calls and at most one historical time-series call per frozen request.

The authorization applies only to the first attempt of one manually dispatched
workflow. The workflow reconstructs the exact authorization, refuses an
existing same-authorization consumption artifact, and writes the one-shot
consumption marker before exposing the provider credential. Static concurrency
prevents two acquisitions from passing that check together. It cannot be reused
or retried. It permits no request selection,
symbol or venue substitution, broader window, batch job, live subscription,
raw-data persistence, account decision, order, threshold selection, horizon
selection, scenario selection, policy promotion, or runtime authority.

## Re-quote-before-download behavior

The authorized runner first calls `get_billable_size` and `get_cost` for every
exact request in manifest order. No time-series request is made unless every
re-quote is complete and available and the aggregate cost and byte estimates
remain within the authorization's hard ceilings. A provider error, zero size,
cost increase, size increase, incomplete total, or credential/SDK failure
closes the gate without downloading anything.

After a successful preflight, the runner calls historical
`timeseries.get_range` once for each unchanged request in manifest order. It
validates the returned dataset, schema, mapped symbol, receive-time boundary,
and required fields. The first failure stops all later downloads. Partial
captures are never emitted.

## Minimal normalized capture and cleanup

Each request may use one temporary DBN file while its response is normalized.
That file is hashed as ephemeral completion evidence and deleted immediately.
The temporary directory is removed before the sanitized report is finalized;
neither raw DBN nor raw provider records are uploaded or retained.

Only the already registered minimal capture may persist. It contains normalized
receive-time top-of-book updates and trading-status evidence, preserves original
provider order for equal status timestamps, reconciles every record to exactly
one frozen request, and is validated again against the opportunity and request
hashes. Both execution scenarios later receive this identical capture.

Provider exception messages and credentials are discarded. Reports retain only
safe exception-class codes, exact request completion rows, preflight totals,
ephemeral file hashes, cleanup flags, and the normalized capture hash. Actual
billing remains unknown.

## Workflow boundary

Pushes run only provider-free unit tests and compilation. Acquisition requires a
manual dispatch naming the full authorization commit SHA, authorization path,
quote-authorization path, successful freeze run and artifact, and successful
quote run and artifact. The workflow checks out the exact research-branch
commit, verifies both source workflow runs, downloads both immutable artifacts,
pins Databento SDK `0.83.0`, and exposes `DATABENTO_API_KEY` only to the final
acquisition step.

The artifact upload includes the sanitized report and, only after complete
success, the minimal normalized capture. It never includes a DBN file. Known
credential, SDK, preflight, provider, mapping, and capture failures preserve a
sanitized fail-closed report, after which the final completeness gate fails.

## Registration result and next gate

This registration exercised fake provider clients only. It created no per-date
authorization and performed no provider request. After a real registered date
has a successful exact metadata quote, independently verify its chain, publish
one acquisition authorization as a separate child commit, and run only its
first manual workflow attempt. A complete capture may then feed all six
prospective runtime cells without ranking or selecting one; missing inputs stay
unavailable.

Files:

- Contract: `research/strategy/prospective-market-input-acquisition-v0.1.json`
- Mechanics: `src/momentumbot/research/prospective_market_input_acquisition.py`
- CLI: `scripts/acquire_prospective_market_inputs.py`
- Workflow: `.github/workflows/prospective-market-input-acquisition.yml`
- Tests: `tests/test_prospective_market_input_acquisition.py`
