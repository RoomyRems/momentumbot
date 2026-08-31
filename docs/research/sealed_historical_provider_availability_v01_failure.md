# Sealed historical provider availability v0.1 — safe failure

The only authorized run was GitHub Actions run `33348067097`, attempt 1, on
August 31, 2026. Provider-free validation passed before the four-call probe.

## Sanitized result

| Gate | Result |
|---|---|
| Massive point-in-time sample, 2025-05-30 | HTTP 200; required reference fields present |
| Massive point-in-time sample, 2025-07-17 | HTTP 200; required reference fields present |
| Databento `XNAS.ITCH` dataset range | Passed; selected interval covered |
| Alpaca SIP session-calendar request | HTTP 401; failed |

The overall gate therefore failed. An HTTP 401 is an authentication failure, not
evidence that the selected sessions are absent or that the Alpaca subscription lacks
SIP entitlement. All four permitted calls were consumed. The workflow uploaded the
sanitized report and failed at the final enforcement step as designed.

No raw provider row, provider error body, credential, account response, transcript
value, or intraday market datum was persisted. Incremental provider cost was `$0`.
No order was submitted.

## Consequence

Run `33348067097` must not be rerun. The failed gate authorizes no universe pagination,
bulk market-data acquisition, runtime replay, or provider substitution. Massive and
Databento capability cannot compensate for an invalid required Alpaca credential under
the frozen v0.1 authorization.

Progress is blocked at the credential boundary. Continuing would require valid Alpaca
market-data credentials and a separately preregistered child authorization; it cannot
alter the 30 selected dates, Micro-v0.1, scanner thresholds, account rules, execution
scenarios, management rule, or sealed transcript boundary.
