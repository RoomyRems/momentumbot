# Corporate-action ordering repair and saved-prefix continuation

Child of `887544eb55de494bcb9cf07d441a3669f2f4b220`. The failed v0.1 source,
registration, code, consumption and receipts remain immutable. The repair tests
whether complete corporate-action pagination can retain unordered provider rows
without relaxing date, identity, cursor or transport checks. No strategy/risk,
transcript, retrospective outcome, scanner runtime or financial gate changes.

## Narrow repair

Only Alpaca corporate-action arrival ordering changes. Process dates must still
be valid and inside each fixed 120-day window, and IDs must be unique within and
across pages. Unrequested groups, malformed responses, duplicate cursors, empty
nonterminal pages and exceeded page limits still fail. Original row order is
preserved; date regressions are retained as page diagnostics. There is no sorting,
deduplication or historical announcement-time inference. Massive split ordering
and all daily-bar checks continue to use the immutable parent behavior.

The original complete HTTP-200 page is tested directly. The parent still rejects
it with `action date regression`; the child preserves all 1,000 unique IDs and
every row in source order, including 157 regressions in the reverse-split group.
The returned cursor becomes exactly page 2. No new provider request is used to
diagnose or test this change.

## Exact saved prefix, remaining suffix only

The original 3,493,487-byte capture ZIP is now preserved at
`research/data-audits/early-pullback-coverage-continuation-v0.2/original-prefix.zip`.
Its SHA-256 is
`1d7edc9a9458b290320b5cd2963d911037d3c2b8d60bd86e01ef001a6528861a`.
It is the exact GitHub artifact `10330669089` from run `34799137954`, not a newly
constructed capture. The previously verified failure proof, original ZIP bytes,
inventory and every member are bound before replay.

The child replays all 47 saved responses: 46 successful March 4 daily roots and
the retained corporate-action page. The completed daily coverage report must
match the original exactly. The new run's first provider request is the retained
action cursor on page 2; completed requests are not downloaded again. No automatic
fallback exists if that cursor is no longer usable.

The original 15,000-attempt ceiling is preserved: 47 reused plus at most **14,953
new attempts**. All response, retention, per-root pagination and provider pacing
limits remain unchanged. An embedded copy of the original prefix accompanies the
new capture archive. The suffix keeps the tested v0.1 intent/receipt schema;
the v0.2 report explicitly separates new, reused and total attempts. Independent
verification checks original ZIP/inventory pins and every suffix intent/receipt,
replays the embedded prefix and suffix, and reproduces the complete final report.

## Hosted execution and verification

The new `coverage-continuation.yml` workflow uses a reusable frozen-runtime action
and shared hosted source gates rather than copying the entire previous launcher.
`consume` requires full CI on its exact new code commit and creates its own durable
consumption ref. `capture` checks the preflight original ZIP, independent metadata,
live ref, runtime, pinned prefix and continuation point before reading credentials.
`verify` fetches the original new ZIP and reproduces all source results without
provider credentials. Capture failures retain safe original evidence and stop once.

Publishing the new registration on the active branch starts this workflow under
the owner's continuation authorization. The original consumption is never reused.
The operational incremental-cost ceiling remains $10 with no metered purchase or
subscription-change mechanism; billing enforcement, entitlement and credit balance
remain unverified. Capture has a 150-minute internal deadline before the 180-minute
hosted timeout. New artifacts request 90-day retention; the saved original prefix
is also committed with this source checkpoint.

## Validation and next milestone

Focused tests exercise the real rejected page, exact original prefix, preserved
daily results, cross-page unordered events, unchanged date/ID/cursor/Massive
checks, artifact tampering, remaining-request bounds, failure retention and shared
hosted gates. Synthetic suffix transport proves the next request uses the saved
cursor and no original daily request repeats; original-archive replay reproduces
the resulting report. Normal and optimized checks precede one full hosted CI run.

All 73 focused tests passed normally in 43.629 seconds and optimized in 44.158
seconds, including 16 new tests. Compilation and whitespace checks passed.
The local verification record is retained alongside the exact original ZIP.

After successful capture and independent verification, the next task is dated
identity/corporate-action resolution and scanner-input integration. This repair
alone does not prove complete source coverage or the full hybrid strategy's edge.
