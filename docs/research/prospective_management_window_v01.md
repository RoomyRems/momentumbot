# Prospective management window v0.1

## Result

This child closes the last known pre-panel market-data gap without changing the
frozen strategy. For each opportunity in an exact
`prospective-opportunity-freeze-v0.1` artifact, it captures raw-adjusted Alpaca
SIP one-minute bars and eligible historical SIP transaction prints from the
decision through a fixed 15-minute signal window plus a 60-second execution
tail. Overlapping windows for the same symbol are merged before the provider
request.

The provider-free projection then applies the already-selected
`half-2r-breakeven-first-red-1m` rule to exact accepted entry fills from an
immutable `prospective-daily-account-runtime-v0.1` artifact. It reports whether
the fixed transaction path supports a descriptive initial-stop, 2R partial,
breakeven-stop, or first-red-one-minute exit observation.

## Causal and authority boundaries

The opportunity manifest is frozen before any management-window request. The
request begins at the decision's UTC minute, but the projection ignores every
trade at or before the exact modeled L1 entry fill. It does not load Ross
actions, fills, skips, recaps, transcripts, later labels, or prices outside the
registered window. A provider failure fails the capture closed; a missing bar
or eligible post-fill transaction remains unavailable. The fixed window is
never extended after seeing a case, and there is no end-of-window liquidation.

SIP prints are transaction evidence, not broker fills. This child does not
model exit-side quotes, spread, queue position, displayed liquidity, routing,
latency, market impact, halts, or broker acknowledgements. It therefore does
not mutate the parent ledger, mark the account flat, calculate sell fees or
realized P&L, or make portfolio metrics eligible. Adds and re-entries are also
outside this registered child; a campaign with multiple accepted entries is
retained as unavailable.

No account read or order endpoint is used. The capture needs only the existing
Alpaca market-data credentials. Paper and live orders remain unauthorized.

## Daily operation

The workflow `.github/workflows/prospective-management-window.yml` has two
fixed 19:00 New York schedules covering only the ten registered 2026 dates. A
resolver requires exactly one successful same-date opportunity-freeze artifact
on `phase-3-historical-snapshot`, checks out that run's exact commit, and rejects
a second capture attempt for the date. The yearless cron cannot run the data
path in another year because the resolver requires one of these exact dates:

- August 24–28 and August 31, 2026;
- September 1–4, 2026.

The capture artifact contains only the request manifest and normalized,
hash-bound management capture. Credentials, provider messages, and raw provider
payloads are not persisted. All third-party GitHub actions in this workflow are
pinned to immutable commit SHAs.

A manual capture is allowed only for an exact registered date, exact successful
opportunity-freeze run/attempt/artifact, and exact research commit. It is a
first-attempt recovery path, not permission to repeat a completed or failed
provider request based on its outcome.

After the corresponding daily account runtime exists, dispatch `project` with
the exact successful daily-runtime and management-capture parents. The command
used by the provider-free step is:

```bash
python scripts/run_prospective_management_window.py project \
  --daily-runtime prospective-daily-account-runtime/daily-account-runtime.json \
  --management-capture prospective-management-window-capture/management-window-capture.json \
  --expected-trading-date 2026-08-24 \
  --output-dir prospective-management-window-projection
```

The resulting projection retains all 12 account/horizon/scenario cells and
hash-binds each cell to its flattened decisions and session summary. A closed
descriptive exit can coexist with an open parent-ledger position by design;
that distinction prevents transaction evidence from being mislabeled as a
portfolio result.

## Verification and next gate

Provider-free verification is:

```bash
python -m unittest tests.test_prospective_management_window -v
```

Synthetic tests cover exact request derivation, zero-opportunity dates, SIP/raw
provider parameters, transaction-condition filtering, odd-lot retention,
management projection, unavailable inputs, write-once output, tamper rejection,
and flattened-cell consistency.

With this child registered and published, pre-panel strategy development is
frozen. The next gate is evidence collection across all ten dates. No setup
family, AI layer, microstructure feature, threshold, or architecture expansion
is authorized before the complete label-blind panel runtime is assembled and
the preregistered retrospective comparison is run.
