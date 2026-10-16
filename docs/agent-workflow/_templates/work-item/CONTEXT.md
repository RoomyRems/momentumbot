# Work-item templates

| Template | Concrete run product | Use after |
|---|---|---|
| [scope.md](scope.md) | `01_scope.md` | Scope and authorization have been investigated |
| [change.md](change.md) | `02_change.md` | There is an actual scoped implementation or a recorded blocker |
| [verification.md](verification.md) | `03_verification.md` | Checks have produced observed results, including failures |
| [handoff.md](handoff.md) | `04_handoff.md` | The actual delivery state and next action can be stated |

Copy/adapt only the form needed into a concrete run; see
[path notation](../../CONTEXT.md). Replace prompts with facts or explicit
`not checked`, `not applicable` or `blocked` explanations. Never copy example
states as evidence. Keep products short and link original evidence.

Create a small run `CONTEXT.md` at the same time as its first product. It should
name the purpose, parent and relevant reference inputs, link the products that
exist, state the current stage/blocker, and name the next action. The run router
must not become a second project-wide current-status file.

Stable templates describe **what to record**; per-run products record **what
actually happened**. Immutable captures and manifests are references to both,
never template output destinations.
