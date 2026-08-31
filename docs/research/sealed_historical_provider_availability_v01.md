# Sealed historical provider availability v0.1

## Purpose

This is the first credentialed gate beneath `sealed-historical-walk-forward-v0.1`.
It asks only whether the frozen 30-session interval can be supported in principle.
It does not acquire a universe, candidates, news, SEC evidence, intraday market data,
or execution data, and it does not start the historical runtime.

The frozen parent contract hash is
`93a4316a4ef785e30ebc393ec140fa02ea23027aa9cd85673d34401b3bca3452`.
The provider-probe authorization hash is
`a985794bc0856aa37d8a79ba43f068994329e4950b60cb1d86ba5436a1f77295`.

## Exact one-shot call budget

The manual probe may make exactly four calls on its first workflow attempt:

1. One Alpaca SIP `SPY` daily-bars request spanning the frozen interval. Its only
   retained facts are response status, row count, the set of matched selected dates,
   missing selected dates, and whether an unexpected next page exists.
2. One Massive/Polygon point-in-time ticker request for `2025-05-30`, limited to one
   active U.S. stock row with no pagination.
3. One identical Massive/Polygon request for `2025-07-17`.
4. One Databento `metadata.get_dataset_range` call for `XNAS.ITCH`.

The quoted incremental cost is `$0`. Automatic retries and reruns are prohibited.
The workflow is manual only and has no schedule.

## Fail-closed behavior

A missing selected session, provider denial, malformed response, unexpected Alpaca
pagination, incomplete Massive schema, or insufficient Databento range makes the gate
fail. The sanitized report is preserved when possible, but a failed gate authorizes
nothing else. A failed date or provider cannot be replaced or silently treated as a
zero-opportunity observation.

The report never persists raw bars, ticker rows, provider response bodies, credentials,
transcript values, or provider error messages. It cannot access either Alpaca account
endpoint and cannot submit paper or live orders.

## Authority boundary

Passing this probe would establish only endpoint entitlement and interval availability.
It would not prove full point-in-time universe completeness or authorize bulk data.
The next permitted step would be a separately frozen acquisition-and-cost contract with
explicit page, byte, request, and dollar ceilings. Transcript titles, captions, actions,
fills, and outcomes remain sealed until all 360 runtime cell records are hash-frozen.
