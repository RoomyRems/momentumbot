# Account session snapshot capture v0.1

## Purpose

`account-session-snapshot-capture-v0.1` supplies the missing causal account
input for the registered August 24–September 4 integration panel. It is a
read-only capture path above frozen `account-chronological-integration-v0.1`,
content SHA-256
`64489aa27fec5eaf8ca12c94f4aeb47344d49a79b14df1bdda706cd23cc9ce73`.
It changes no scanner, Micro-v0.1, execution, sizing or risk rule.

The separately created Alpaca paper accounts are registered as a $30,000 main
fixture and a $2,000 small fixture. Their distinct credentials are repository
Actions secrets. They are never accepted on the command line, written to an
artifact or exposed to another workflow step.

## Validation and capture

The push-triggered mode is validation-only. It confirms that both credentials
resolve to separate active USD paper accounts, that equity matches the two
registered fixtures within one cent, and that neither account has a position,
open order or blocked flag. This validation is not a session snapshot and is
not runtime eligible.

On each registered session, capture is scheduled for 5:15 a.m. New York time,
leaving 105 minutes before the frozen 7:00 a.m. strategy start. The capture
must start and finish on that New York session date by 7:00 a.m. A late,
missing, swapped, duplicate, dirty or unavailable account fails closed and
cannot be replaced by another date. `workflow_dispatch` provides the same
deadline-checked capture as a manual fallback.

GitHub sources scheduled workflows only from the default branch. The workflow
therefore exists on `main` solely as a scheduler and explicitly checks out
`phase-3-historical-snapshot` before installing or executing project code. The
artifact records the default-branch workflow source SHA and the executed
research-branch SHA separately. The scheduled shell gate also requires one of
the ten exact 2026 dates, because GitHub cron has no year field.

## Stored evidence

The source projection retains only status, currency, equity, buying power,
cash, blocked flags, empty position/order counts and capture timestamps. The
provider account ID is replaced with a stable SHA-256 pseudonym. Raw account
IDs, account numbers, credentials and every nonrequired provider field are
omitted.

Each source projection, account snapshot and two-account manifest has its own
canonical content hash. The account snapshot converts directly into the
existing `AccountSessionSnapshot` object, including the pseudonymous unique
account ID, account class, same-day timestamp, equity, buying power, source ID
and source hash. Artifacts are retained for 90 days so successful daily runs
can later be downloaded, independently verified and frozen before any
retrospective comparison.

## Authority boundary

The capture client uses only `GET /v2/account`, `GET /v2/positions` and an
open-order query. It has no write endpoint or broker-order method. A successful
snapshot supplies account input only; it is not a trade, portfolio backtest,
policy-promotion result or evidence of profitability. Raw transcripts, recap
labels, Ross actions and later prices remain prohibited.

The contract is
`research/strategy/account-session-snapshot-capture-v0.1.json`, canonical
content SHA-256
`5e967dbbbe2ee53187940f2ea720bd1937a4391710c97043ec03cc80c9b257b7`.
