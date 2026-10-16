# Development workflow

This is the human/agent development workflow, not MomentumBot's trading runtime
or a replacement for its GitHub capture jobs. Read the shared rules in
[AGENTS.md](../../AGENTS.md), then the small [current-status router](status.md).
Use [the system map](../map/CONTEXT.md) to choose only the affected components.

## Route by next action

| Stage | Contract | Per-run product | Stable template |
|---|---|---|---|
| Establish scope and authority | [01_scope](01_scope/CONTEXT.md) | `runs/<id>/01_scope.md` | [scope](./_templates/work-item/scope.md) |
| Implement the bounded change | [02_change](02_change/CONTEXT.md) | `runs/<id>/02_change.md` | [change](./_templates/work-item/change.md) |
| Check the exact change | [03_verify](03_verify/CONTEXT.md) | `runs/<id>/03_verification.md` | [verification](./_templates/work-item/verification.md) |
| Publish the truthful handoff | [04_handoff](04_handoff/CONTEXT.md) | `runs/<id>/04_handoff.md` | [handoff](./_templates/work-item/handoff.md) |

**Path notation:** `<id>` is one concrete work-item slug, such as
`icm-adoption-2026-10-16`; paths containing it are templates, not existing files
or executable commands. All `runs/<id>/...` paths above and in stage contracts
are relative to this folder. Create products only when the corresponding work
exists, using [the templates](./_templates/CONTEXT.md). Each created working
folder needs a `CONTEXT.md` describing its inputs, products and next action.
The [run index](runs/CONTEXT.md) links actual work; never pre-create empty output
directories or mark a future stage complete.

## Small loading budget

For ordinary work, load this router, current status, the relevant map card(s),
the active stage contract, and the exact files that stage names. The full route
archive and historical records are references, not mandatory startup context.
For a cold restart, follow the same links and reconstruct the handoff from saved
evidence; do not rely on a prior chat's claims of completion.

The four stages are evidence boundaries, not four mandatory approval turns.
Reuse the owner's already-authorized streamlined process. A focused coding fix
can cross all four stages in one turn, recording concise results. Human checks
are for material scope, authority or acceptance decisions; a unit test or
ordinary navigation edit does not create a new permission requirement.

Automatic CI, durable consumption, provider capture and independent verification
retain their existing contracts and entry points. Record their actual runs and
results in the work item; these folders do not launch jobs, grant credentials,
extend expired approvals, or substitute for an exact-commit gate.

For indexes, source review and drift checks, see [maintenance](maintenance.md).
This adaptation follows [ICM Architect](https://github.com/RinDig/icm-architect);
the source/version/license record is under [map metadata](../map/_meta/CONTEXT.md).
