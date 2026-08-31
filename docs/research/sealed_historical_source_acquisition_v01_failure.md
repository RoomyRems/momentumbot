# Sealed historical source acquisition v0.1 failure

GitHub Actions run `33350635957` consumed the one-shot v0.1 authorization and
failed safely on August 31, 2026. Validation passed. The acquisition completed
point-in-time membership, instrument/SIP coverage, identity normalization,
market discovery, float, and news. It then exhausted the registered 20,000
HTTP-attempt ceiling while independently reconstructing market discovery for
the scanner snapshot.

The guard blocked request 20,001 before network access. The final accounting
was 18,659 Alpaca attempts, 978 SEC attempts, and 363 Massive attempts. No
credential failure, Databento call, transcript-value read, account access, or
order occurred. The incomplete normalized source tree was not uploaded; only
the consumption marker and sanitized failure artifact were retained.

## Root cause

The 20,000-call ceiling underestimated the registered acquisition graph. The
scanner stage intentionally re-acquires its market inputs independently after
the earlier market-discovery stage, and then acquires the full-membership rank
cross-section. This is provider work required by the frozen scanner-input
contract, not an HTTP retry storm or authentication failure. The v0.1
authorization cannot be rerun.

## Repair boundary

A child may preserve every date, provider, endpoint, request parameter,
strategy rule, candidate ceiling, retention ceiling, and causal boundary while
raising only the zero-incremental-cost HTTP safety ceiling. It must consume a
new authorization before provider access and may run only once. The v0.1
failure remains permanent and cannot contribute runtime evidence.
