# Entry-reference evidence and strict observed-update gate v0.1

The original source tapes explain the 23 unavailable entry references. All 22
`unavailable_no_fresh_decision_quote` opportunities have **zero original quote
updates** in the inclusive 100 ms before their decisions. No qualifying rows
were lost by the window filter. Thirteen have older updates already retained in
the original requests; nine have none at or before the decision in those
requests. Acquiring an earlier prefix cannot supply an update inside an already
complete interval that contains none.

JVA is different: its exact original quote response contains zero records. Its
saved diagnostic establishes complete native decoding, exact request metadata,
valid symbol/date mapping, no record limit, and zero native records. The empty
response remains the original unavailable request, without manufacturing an
empty normalized tape or repeating the download.

Parent: `ae3711e8f248e28754166ba580d9c7b6bfd3e8ef`, tree
`c5b31a3536422d0092dfeafdd322d4e76e83bac8`. All seven parent publication workflows
passed, including [CI 34432958144](https://github.com/RoomyRems/momentumbot/actions/runs/34432958144).

## Explicit observation policy

`strict-observed-quote-entry-gate-v0.1` requires a usable update on the original
XNAS.ITCH feed in the unchanged inclusive 100 ms lookback. This is a separate
research observation layer; it is not installed in the trading/account engine.
It specifies the entry implication of verified absence, which the original
availability classification deliberately did not specify.

| Verified evidence at the decision | Observation-layer result |
|---|---|
| Usable quote update within the original lookback | Reference present; all other entry, status, account and risk checks still apply |
| Complete source with no qualifying update, including an exactly verified empty response | Withhold entry under this explicitly stated observed-update policy |
| Missing, failed, partial, truncated, mismatched or unverified source | Unresolved; cannot claim a known absence or a known policy abstention |

Decisions use receive timestamps and original record order. Both lookback
endpoints are inclusive. Later quotes and later status events cannot authorize
or rewrite an earlier observation. Older updates are counted as evidence only;
their ages do not relax the frozen threshold. A reference, including one
associated with a halt, never authorizes an order by itself.

Databento describes MBP-1 as event-based top-of-book data, carrying updates and
trades rather than a regularly refreshed snapshot. An absence of updates in a
short interval therefore does not establish that no standing quote existed.
See [the provider's MBP-1 schema documentation](https://databento.com/docs/schemas-and-data-formats/mbp-1).
Our strict update-age policy remains a modeling choice; this work does not claim
to reconstruct a persistent BBO or consolidated NBBO.

## Source verification and result

The offline inspector checks the exact original acquisition and consumption
ZIPs, embedded completed prefix and JVA diagnostic, CRCs, request receipts,
compressed and normalized tape hashes, complete row counts, original ordinals,
all 30 availability date files and all 109 opportunity identities. It reads no
Ross labels or financial metrics and runs no account, fill or historical replay.

The result preserves all 86 original available reference ordinals and ages.
There are 23 verified no-update observations under the new explicit policy:
22 from nonempty original requests and one from the verified empty JVA request.
The report preserves the original reason, evidence hashes and all 162 affected
path/session references. Original unavailable flags, account gap histories,
runtime bytes and independent verification results are unchanged.

This is a source-informed diagnostic and policy specification made after source
availability was known. It is not an unseen-data strategy test or a policy
promotion. No parameter was selected using P&L or later trade outcomes.

- Registration: `6025d10ad774b1edd9dc2101241efe4df575b9a329ce042ebe58739d5e4b9a62`.
- Result: `b47ba35fa6bed02db623faa6ded834447557d776fc3b35cd506632218d8760ce`.
- [Registered scope](../../research/strategy/sealed-historical-entry-reference-evidence-v0.1.json).
- [Source-backed result](../../research/data-audits/sealed-historical-entry-reference-evidence-v0.1/report.json).

## Next development scope

The next useful step is a bounded **conditional evaluation of this strict
observed-update policy**, using all 30 dates, all original account paths and
once-only seeds. It must explicitly bind these 23 withhold decisions to the
unchanged hosted runtime before reporting returns, drawdowns or trade metrics.
Earlier unavailable history remains visible; neither dates nor opportunities
may be discarded to improve results. Such an evaluation would describe a
single-venue observed-data policy, not a full-coverage Ross strategy backtest.

If the intended policy instead uses standing quotes or waits for a subsequent
update, that requires a separately specified causal policy and adequate source
evidence. Neither changing the quote-age rule nor extending captures is part of
this child. No duplicate local replay is needed to inspect the saved evidence.

## Reproduce the evidence inspection

Use a new output path; an existing report cannot be overwritten:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts python \
  scripts/audit_sealed_historical_entry_reference_evidence_v01.py \
  --expected-contract-sha256 6025d10ad774b1edd9dc2101241efe4df575b9a329ce042ebe58739d5e4b9a62 \
  --result-zip /exact/result-34084113393-1.zip \
  --consumption-zip /exact/consumption-34084113393-1.zip \
  --output /tmp/new-entry-reference-evidence.json
```

All 28 focused tests passed normally and with Python optimization. The full
suite passed 2,402 tests with zero skips in 278.658 seconds on CPython 3.12.14.
Final registration verification and the complete original-source audit passed.
The CLI denies network and subprocess I/O. Validation details and test-log
commitments are retained in the [implementation verification](../../research/data-audits/sealed-historical-entry-reference-evidence-v0.1/implementation-verification.json).
