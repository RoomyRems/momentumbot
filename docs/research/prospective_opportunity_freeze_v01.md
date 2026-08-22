# Prospective opportunity freeze v0.1

## Purpose

This child closes the deterministic gap between a future prospective
scanner/Micro runtime and the already registered market-input capture. For each
August 24–September 4 panel date, it retains every causal Micro-v0.1 entry
decision from the union of `current-general-2026` and
`current-small-account-2026`, freezes the exact market-input opportunity
identity, and derives the two-schema unquoted request manifest.

The frozen parent is `prospective-market-input-capture-v0.1` at checkpoint
`fa786a79103375d3c67b01240663873e2b5478df`. The single hypothesis is purely
mechanical: an already frozen label-blind daily decision ledger can be reduced
to the exact opportunity schema without letting account scarcity, an execution
scenario, a later outcome, or a retrospective label select the retained rows.

## Causal source boundary

The accepted source is not a completed Micro outcome replay. It is a small
daily ledger emitted at the order-decision boundary. Each row binds an
account-neutral activation, frozen plan, symbol, candidate-qualification time,
causal Micro trigger time, Micro runtime-prefix hash, and the non-empty subset
of the two profiles for which the scanner candidate was eligible.

The decision timestamp is the causal Micro trigger at which the baseline would
decide to send an order. It is not a simulated quote arrival, broker fill,
exit, or later reconstructed outcome. The stable opportunity ID excludes the
eligible-profile list, account identity, account balances, quantities, and
execution scenario. Therefore one decision eligible for both profiles is
emitted once, while a decision eligible for either profile is retained in the
union.

The source must be hash-bound, chronologically sorted, and on one registered
New York trading date. It must declare that account snapshots and scarcity
were not applied, execution scenarios were not applied, no provider quote was
made, and no retrospective labels or later prices/P&L were loaded. Full
outcome, fill, exit, account, and selection fields are rejected even after a
caller recomputes the source hash.

## Deterministic outputs

The materializer writes three JSON files:

- `opportunity-manifest.json` contains only opportunity ID, registered date,
  symbol, decision nanoseconds, and the exact runtime hash;
- `request-manifest.json` is delegated to the frozen
  `prospective-market-input-capture-v0.1` mechanics, producing one `mbp-1` and
  one `status` row per symbol-date; and
- `freeze-manifest.json` binds the source, opportunity, and request hashes and
  records the still-unarmed authority boundary.

Materialization is write-once: the output directory must be absent or empty,
so a later run cannot silently mix with or overwrite an earlier freeze.

A date with candidates but no Micro decisions, or no candidates at all, is
retained as an explicit zero-opportunity freeze with zero requests. It is never
replaced by another date or symbol.

## Workflow and authority

`.github/workflows/prospective-opportunity-freeze.yml` is a provider-free
manual/reusable handoff. It downloads one exact source artifact from a named
same-repository Actions run, requires the registered date to match, runs the
materializer and deterministic tests, and retains the three output manifests
for 90 days. It contains no market-data or broker secret and has only read
permissions.

The workflow is intentionally not scheduled yet: no causal prospective
scanner/Micro producer has been registered. Scheduling an empty materializer
would not create opportunities and could hide a missing source. The next child
must register that producer and have its successful daily run invoke this
handoff.

This registration makes no Databento quote or download, authorizes `$0` of
Databento credit, submits no broker order, creates no runtime authority, and
does not select an account, horizon, execution scenario, threshold, or result.

Files:

- Contract: `research/strategy/prospective-opportunity-freeze-v0.1.json`
- Mechanics: `src/momentumbot/research/prospective_opportunity_freeze.py`
- CLI: `scripts/freeze_prospective_opportunities.py`
- Workflow: `.github/workflows/prospective-opportunity-freeze.yml`
- Tests: `tests/test_prospective_opportunity_freeze.py`
