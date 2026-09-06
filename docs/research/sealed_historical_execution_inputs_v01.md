# Historical execution/status input registration v0.1

This provider-free registration is the causal child of completed Micro checkpoint
`3d20c7efdcb53b8d3bfa46b550d41001108a8dac`, tree
`1ca85c8377483f6f4cdf50cc51bbfa584c8be807`. Its one mechanical hypothesis is that
all frozen Micro decisions can be projected into exact quote/status requests
without using account scarcity, execution scenarios, later outcomes, or
retrospective evidence to select them. It does not execute Micro again.

## Exact inputs and outputs

The validator checks every file in the immutable 31-file Micro bundle against
inventory commitment
`06b285120bab6acd21836a02b44969b1128dcc182ab7ea0ee444dc4384608f03`, the exact
manifest file/content hashes, the original scanner plan, all 30 daily source
files and their activation coverage, and the frozen policy contracts. The
source Snapshot and both measured Micro input captures remain bound through
the completed runtime manifest. Source data and consumption refs are unchanged.

The plan retains all 109 unique decisions from 48 triggered activations, across
45 symbol/date pairs and 25 dates with decisions. It includes all 30 selected
dates. June 3, 5, 16, 17, and 20 are explicit no-decision sessions, preserving
their valid Micro results; missing or altered source files instead fail closed.
The 144 no-trigger activations and zero unavailable activations remain visible.

There are 99 general-profile and 25 small-profile decision eligibilities, with
15 decisions eligible for both. The stable historical opportunity ID includes
the panel, date, activation, plan, symbol, exact nanosecond trigger, and causal
runtime-prefix hash. It excludes account identity and profile selection, while
the row retains the original profile union. Distinct activations at the same
symbol/time remain distinct. Full source-decision and date hashes bind each
projection, but plan prices and simulated outcomes are not request inputs.

Three write-once files are retained in
`research/runtime/sealed-historical-execution-input-plan-v0.1/`:

- `opportunity-manifest.json`: 109 projected identities and all 30 date records;
- `request-manifest.json`: exactly 90 unquoted requests; and
- `freeze-manifest.json`: exact parent/output bindings and the next input gate.

Validation re-derives the entire projection and request list from the exact
parent and requires identical JSON contents and bytes. Rehashing an altered
symbol, timestamp, profile, request envelope, or retrospective field cannot make
it valid. Symlinks, extra files, missing dates, and attempts to overwrite a
frozen output fail.

## Unchanged input mechanics

The historical adapter imports the frozen prospective capture constants while
retaining separate historical panel and artifact IDs. It does not monkeypatch
prospective date restrictions or reinterpret old authorizations.

Each of the 45 symbol/date pairs has two `XNAS.ITCH` requests with `raw_symbol`
identity and receive-time (`ts_recv`) semantics:

- `mbp-1`: earliest decision minus 100 milliseconds, through latest decision
  plus 550 milliseconds and one nanosecond for the exclusive end;
- `status`: midnight UTC on that date through the identical exclusive end.

Both execution scenarios must receive the same inputs. This remains a Nasdaq
single-venue view, with no consolidated-NBBO or broker-fill claim. Missing or
unknown initial status, crossed/locked/one-sided books, and quote/status events
at an ambiguous equal receive time remain unavailable under the frozen capture
semantics. SIP prints cannot substitute for missing execution quotes.

## Next dependency

This registration makes zero provider calls and exposes no credential or order
entrypoint. It registers no download, spend, simulation, backtest, or policy
promotion. The existing user authority to continue development and operations
persists; it does not replace the machine-verifiable data gates.

Next, prepare the narrow historical metadata-quote adapter and an exact
parent-bound one-shot quote record for these 90 requests. That step may use only
`historical.metadata.get_billable_size` and `historical.metadata.get_cost`, at
most 180 calls, with sanitized failure evidence and no time-series access.
A successful complete quote must precede the separate bounded acquisition and
consumption record. Independently verified execution/status data and registered
management inputs must be available before account/fill simulation can begin.
No dates, symbols, schemas, venues, policies, or account assumptions may be
substituted to pass a gate.

Provider-free validation command:

```bash
PYTHONPATH=src:scripts python scripts/register_sealed_historical_execution_inputs_v01.py \
  --output-root research/runtime/sealed-historical-execution-input-plan-v0.1 --validate-only
```

The focused tests cover the exact nanosecond envelopes, profile-union identity,
same-time separate activations, all zero-decision dates, write-once behavior,
parent/output tampering, and the provider/account/retrospective boundary.
Prepublication validation passed 48 focused tests normally and under optimized
CPython 3.12.14, all 1,450 repository tests, undefined-name checks, and the
provider-free CLI validation. The permanent receipt is
`research/data-audits/sealed-historical-execution-input-registration-v0.1-2026-09-06.json`.
