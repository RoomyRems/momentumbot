# Campaign, portfolio and account-state contract v0.1

## Question and frozen parent

The isolated hypothesis is that a deterministic event-sourced ledger can group repeated Micro-v0.1 plan emissions into one account-scoped candidate campaign and identify mechanically infeasible supplied fills without changing the technical policy or using retrospective behavior.

The frozen technical parent remains `micro-v0.1`, fingerprint `49c27b4a1925da4990095e6ffb82bf7557743d1b58ea38f20eee69bce62618fa`. The completed context comparison remains immutable at content SHA-256 `d93d61ed0ebd5657bbed135beb7fe2d7b0f337d1e3f76720c0f1dcff7908ff54`. Scanner thresholds, Micro setup/trigger logic, execution reconstruction, context shadows, labels and comparison outputs are unchanged.

## Isolated implementation

`CampaignPortfolioLedger` is a standalone research reducer for one account and one session. Candidate activation, not ticker/date alone, is the campaign anchor. Repeated plan IDs under that activation are retained inside one stable campaign ID. The unique account ID, account policy ID and account class are part of the identifier, so main and small accounts cannot silently share state.

The ledger consumes events that another frozen layer has already produced:

- qualified plan emissions;
- execution-approved entry fills with their planned and modeled prices;
- exit fills;
- symbol halt/resume events; and
- explicit account locks.

It tracks FIFO position lots, buying power, total and per-campaign notional and open risk, open-position count, starter/add/re-entry state, realized session P&L, profit high water, irreversible lockout and whether open positions still require flattening. It records simultaneous plan emissions but deliberately does not decide which candidate wins scarce capital.

## Authority and causal boundary

The contract contains no main- or small-account numerical limits. A caller must provide a separately registered deterministic policy. The ledger does not discover candidates, assess context, choose between opportunities, create or resize an order, simulate a fill, or raise risk. Equal-time opportunity collisions remain unresolved until an observed event sequence or separately preregistered deterministic priority exists.

Only information available at the event time is admissible. Raw transcripts, Ross actions or fills, recap judgments, later prices and retrospective outcome labels are prohibited. The JSON artifact emitted by the ledger declares no strategy, selection or size authority and is not promotion eligible.

## Mechanical invariants

- Events are timezone-aware, bounded to the New York trading date and applied in nondecreasing order.
- The first fill in a campaign is a starter, a fill while held is an add, and a fill after flat is a re-entry.
- Adds below the current average entry are rejected under the frozen no-averaging-down rule.
- New entries fail closed when buying power, notional, risk, campaign-entry or open-position limits would be exceeded.
- A halt blocks supplied fills until an explicit resume.
- Daily-loss, giveback and manual locks are terminal for new entries. They never prevent supplied exit fills, and any remaining position is marked for flattening.
- Buying power is a transparent cash-like research ledger: entries reserve fill notional and exits restore sale proceeds. Broker settlement, margin and locate behavior remain a later execution/account integration requirement.

## Validation and next gate

This checkpoint validates the schema and reducer mechanics with synthetic causal fixtures. It does not replay the frozen held-out panel and is not a portfolio backtest. Before integration, the project must separately register numerical main/small account policies and a deterministic rule for scarce-capital collisions, then replay a new chronological panel label-blind and freeze that runtime before opening retrospective evidence.

Decision: retain as a standalone shadow-state foundation. Policy promotion remains false.
