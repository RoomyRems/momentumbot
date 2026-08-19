# Account chronological integration v0.1

## Question and registered panel

The isolated hypothesis is that the frozen scanner profiles, unchanged Micro-v0.1 replay, deterministic execution outcomes, paper account policy, scarce-capital order and campaign ledger can be composed into one reproducible account-local event stream without retrospective behavior or outcome knowledge.

The calendar was frozen on August 19 as the ten scheduled U.S. equity sessions from Monday, August 24 through Friday, September 4, 2026. Every session was still future, and August 20–21 are an explicit implementation/authorization buffer for the account-input capture path. Required inputs can therefore be captured before the strategy starts rather than reconstructed after market results exist. No transcript inventory, symbol list, Ross action, later price or result was used to select a date, and a missing source cannot replace one.

## Causal inputs

Each account session requires a separately supplied, hash-bound snapshot containing the unique account ID, main or small class, session date, capture time, starting equity and starting buying power. The capture must belong to that session and occur no later than the frozen profile's 7:00 a.m. New York strategy start. The integration does not invent historical balances; a missing main or small snapshot blocks only that account runtime.

The market runtime must retain the union of candidates admitted by either frozen scanner profile. Main and small scanner dispositions remain separate. Every eligible activation binds its exact causal `CandidateSnapshot`, scanner-record hash, Micro runtime hash and unchanged Micro-v0.1 replay. Rejected or unavailable candidates remain explicit records with no fabricated plan or fill.

## Event order and research sizing

Events are applied by timestamp. Plan emissions precede entry attempts at the same timestamp. Exact-time entry collisions for one account reuse `paper-account-scarcity-policy-v0.1` and its activation-time candidate rank. Entry attempts precede exits at the same timestamp, so ambiguous same-time exits cannot permissively recycle capital. Main-versus-small attention remains unresolved because each account is composed independently.

For a frozen Micro execution fill, the integration chooses the maximum positive whole-share quantity inside every remaining registered ceiling: buying power, starter notional, campaign and total notional, and campaign and total open risk. A zero-share result is recorded as not submitted. This is deterministic project research sizing inside the existing 0.25% paper-risk envelope, not an estimate of Ross's sizing and not a claim that the observed print had enough liquidity.

Accepted entries and their plan-local stop or target exits are applied to the frozen ledger. The accepted synthetic entry quantity—not provider print size—is used for that exit. A `filled_open` Micro outcome remains open; no session-close price or management decision is invented.

## Authority and next gate

The artifact is label-blind and shadow-only. It creates no broker order, cross-account dispatch decision, locate, Level 2 queue, complete management path, portfolio backtest or promotion evidence. Semantic context remains parallel and has no sizing or selection authority.

The implementation is mechanically composable with synthetic fixtures, but the registered market/Micro/account runtime is not yet built. The next valid step is to supply or capture hash-bound pre-decision account snapshots, build the union market runtime for all ten prospective dates, replay Micro-v0.1, and freeze both account artifacts before any retrospective source inventory or comparison.
