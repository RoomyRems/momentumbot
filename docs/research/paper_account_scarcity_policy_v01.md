# Paper account and scarce-capital policy v0.1

## Purpose

The frozen campaign ledger required explicit numerical account constraints and a deterministic rule for same-account opportunities competing for limited capital. This contract supplies both without changing the scanner, Micro-v0.1, execution model or completed context work.

The main and small accounts receive separate policy IDs and retain their existing strategy profiles. Their numerical risk envelope is intentionally identical and comes only from the already-active project `paper-safe` policy: 0.25% of session-start equity as maximum open campaign risk, 1% daily max loss, 50% maximum position value and 50% profit giveback. Session-start equity and buying power are causal broker inputs rather than fixed research constants.

## Conservative structural translation

Version 0.1 allows one open position and at most two accepted entries within a campaign. A first entry must be labeled as a starter; a second may be an add or a re-entry, remains inside the same cumulative campaign-risk/notional cap and can never average down. The starter notional ceiling equals the campaign ceiling because the evidence does not define a stable smaller starter fraction.

These are project paper-safety constraints, not claims about Ross's exact behavior. They can be challenged later only as a separately named policy on a preregistered panel.

## Scarce-capital priority

Chronologically distinct execution events remain chronological. If multiple opportunities for one account have the exact same execution time, the policy reuses the existing label-blind `CandidateSnapshot.ranking_key`: candidate quality, gain rank, percent gain, relative volume, cumulative volume and smaller float. Remaining ties use the earlier causal snapshot, symbol, plan ID and opportunity ID.

This is not a top-N scanner rule. It has no effect unless account capacity is contested. Cross-account ordering fails closed because the transcripts show that attention shifted between the main and small accounts across sessions; no universal main-first or small-first rule is supported.

## Offline transcript boundary review

Five pre-held-out records were inspected only to prevent overclaiming. They describe inconsistent operating regimes: a January one-trade/10%-risk challenge, an April beta one-trade exercise, a May starter-first lesson, a later May adjustable buying-power hotkey after a regulatory change, and a June recap in which account attention was deliberately reprioritized. Those observations explain why the project does not fit Ross-style risk or cross-account dispatch values here. Raw captions remain outside runtime, and none of the values or actions from the held-out comparison were used.

## Status and next gate

The contract is registered but not integrated. It creates no order, fill or portfolio result and is not promotion eligible. The next valid step is a newly preregistered label-blind chronological integration that binds exact scanner, Micro, execution, account-policy and ledger inputs before retrospective evidence is opened.
