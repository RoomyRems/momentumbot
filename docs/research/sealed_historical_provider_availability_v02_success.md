# Sealed historical provider availability v0.2 — passed repair

GitHub Actions run `33348970745`, attempt 1, completed successfully on
August 31, 2026. The provider-free validation and the credential-dependent probe both
passed.

## Confirmed root cause

The stored main paper credential pair was valid. The v0.1 workflow had routed the
generic `ALPACA_API_KEY` / `ALPACA_API_SECRET` GitHub secrets instead of the validated
main-account secret names. V0.2 used the previously proven mapping from commit
`e7db059bf258b4d069c788d6293307737d4cea2e`:

- GitHub secret `ALPACA_MAIN_API_KEY` became runtime variable `ALPACA_API_KEY`.
- GitHub secret `ALPACA_MAIN_API_SECRET` became runtime variable
  `ALPACA_API_SECRET`.

No secret value was changed, viewed, persisted, or regenerated.

## Sanitized result

| Gate | Result |
|---|---|
| Alpaca SIP `SPY` daily-bar calendar | HTTP 200; all 30 selected sessions observed |
| Massive point-in-time reference samples | Passed in v0.1; inherited by exact report hash |
| Databento `XNAS.ITCH` selected interval | Passed in v0.1; inherited by exact report hash |
| Overall provider-availability gate | Passed |

The v0.2 child made exactly one Alpaca request at `$0` incremental cost. It did not
repeat Massive or Databento calls. Across v0.1 and v0.2, five calls were made in total.
The sanitized report is frozen at
`research/data-audits/sealed-historical-provider-availability-v0.2-report-2026-08-31.json`.

No raw bar values, raw provider rows, credentials, account response, transcript value,
or intraday market datum was persisted. No account or broker endpoint was called, and
no order was submitted. V0.1 run `33348067097` remains a permanent safe failure and
was not rerun.

## Consequence

The provider-availability gate is complete. This result authorizes no data download by
itself; the next step is a separate, exact, cost-bounded historical acquisition
registration. Strategy rules, the 30 selected dates, the transcript seal, paper-order
authority, and live-order authority remain unchanged.
