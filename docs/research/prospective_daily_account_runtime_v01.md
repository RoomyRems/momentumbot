# Prospective daily account runtime v0.1

## Result

This layer is the first provider-free end-to-end composer for the registered
August 24–September 4 prospective account panel. It consumes four already
frozen artifact families for one date:

1. the complete scanner/Micro daily source bundle;
2. the opportunity and exact-request freeze bundle;
3. the normalized receive-time L1/status capture; and
4. both pre-session Alpaca paper-account snapshots.

It emits exactly 12 independently hash-bound session records per date:

- main and small accounts;
- 1, 5, and 10 second equal-report behavioral horizons; and
- conservative and stress marketable-limit execution scenarios.

Across ten dates, the later panel assembler must therefore receive exactly 120
session records. A zero-opportunity date still emits all 12 sessions. A
qualified candidate with no Micro plan is retained as a zero-plan,
not-submitted decision rather than disappearing.

## Frozen causal boundary

The composer rebuilds the daily source from its scanner rows and Micro trigger
records, validates the opportunity/request derivation, verifies the normalized
market capture, validates both account snapshots, and recomputes every content
hash and cross-binding before creating output. A missing, late, mismatched, or
tampered parent fails closed without a runtime artifact.

Runtime inputs do not include Ross actions, transcripts, recaps, later prices,
P&L, or retrospective labels. The implementation has no provider client,
credential loader, or broker order path. The GitHub workflow uses only
`actions: read` and `contents: read` permissions and downloads four explicitly
named successful first-attempt artifacts.

## Account chronology and entry execution

Each account and execution scenario has its own frozen campaign ledger. Plan
emissions are recorded chronologically. Exact-time plan collisions use the
registered account-local scarcity ordering. To avoid unsourced buying-power
reservation behavior, v0.1 permits only one in-flight entry attempt per account;
it remains in flight through cancel acknowledgement, including after a partial
fill.

The entry reference is the latest complete top-of-book ask at or before the
decision, no more than 100 ms old. A halted reference is not submitted. Missing
status or a missing causal reference is retained as unavailable; there is no SIP
or trade-print fallback.

Order quantity is the maximum positive whole-share quantity inside the frozen
paper-safe buying-power, notional, and risk ceilings. The marketable limit—not
a later fill—is used as the sizing price. Because a buy fill can only occur at
or below that limit, the sizing calculation is conservative and causal. The
actual filled quantity, including a partial fill after the registered displayed
size haircut, is then applied to the unchanged account ledger. Executed equity
fees are aggregated with the registered August 2026 schedule.

## Why exits remain open

The normalized market-input capture ends 550 ms after an entry decision. The
registered management rule needs one-minute bars to model half off at 2R,
breakeven-stop movement, and the runner's first completed red one-minute candle.
Those inputs do not exist in the current parent chain.

Accordingly, every accepted entry is represented as `open`, with no invented
exit price, time, reason, or P&L. The evaluation contract will correctly withhold
conditional portfolio metrics while a cell has open positions or unavailable
inputs. Entry alignment can be measured once retrospective labels are opened,
but exit alignment and portfolio performance cannot be interpreted until a
separately preregistered management-window capture is implemented.

## Behavioral horizons

The 1, 5, and 10 second horizons remain separate equal-report cells, but the
frozen parents contain no preregistered per-opportunity rule that lets a horizon
change an entry. v0.1 therefore gives them identical account and execution
mechanics within a scenario. They may be compared later; none may be selected as
the winner or used to retune the strategy.

## Local provider-free rehearsal

```bash
python -m unittest tests.test_prospective_daily_account_runtime -v
```

The test builds a real synthetic parent chain through the existing source,
freeze, market-capture, account-capture, execution, ledger, fee, and evaluation
types. It verifies fills, scenario separation, unavailable status, zero
opportunities, write-once behavior, hash binding, and retrospective-key
rejection without network access.

## Daily materialization

After the four real parent artifacts exist, dispatch
`.github/workflows/prospective-daily-account-runtime.yml` with their exact run
IDs, attempts, artifact names, the registered date, and the exact research
commit. The provider-free CLI used by that workflow is:

```bash
python scripts/build_prospective_daily_account_runtime.py \
  --source-dir prospective-daily-source \
  --freeze-dir prospective-opportunity-freeze \
  --market-input-dir prospective-market-input-acquisition \
  --account-dir account-session-snapshot \
  --expected-trading-date 2026-08-24 \
  --output-dir prospective-daily-account-runtime
```

The resulting `daily-account-runtime.json` must remain unopened by any
retrospective label process until its hash is frozen. The next engineering gate
is a deterministic ten-date panel assembler plus the longer management-window
capture; neither changes the already registered strategy or evaluation cells.
