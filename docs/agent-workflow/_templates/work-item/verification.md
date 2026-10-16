# Verification — [work-item name]

Status: [passed within stated scope / failed / partial / blocked]

## Inputs and identity

- Scope/change: [relative links to actual run products].
- Code under test: [commit and any uncommitted diff; never imply a clean commit].
- Reference contracts: [only checks needed for this scope].

## Observed checks

| Check / exact command | Code identity | Result | Evidence |
|---|---|---|---|
| [focused test] | [commit/diff] | [pass/fail/skip/interrupted/not run] | [log/path/run URL] |

Record test counts only when observed. CI queued/in-progress is not CI passed.
If a check was not applicable, explain why; do not silently omit a failed gate.

## Cold-walk / impact review

- Starting slice: [entry and stage/card loaded].
- Route tested: [question -> source/consumer -> next action].
- Finding: [what was actually established; unresolved route/source ambiguity].
- Frozen inputs: [preservation check performed, not merely intended].

## Hosted jobs, when relevant

[Exact commit, workflow/run IDs, stage states and original artifact references.
Separate CI, capture, independent verification and later integration. State
not applicable if this change launched no job.]

## Acceptance and unknowns

- Acceptance items satisfied: [evidence-backed list].
- Remaining failures/unrun checks: [explicit].
- External consumers or unavailable evidence: [unknown unless investigated].
- Next action: [handoff, bounded repair, or specific authority decision].
