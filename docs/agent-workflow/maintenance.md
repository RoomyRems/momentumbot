# Maintaining the ICM layer

The [system map](../map/CONTEXT.md) describes the project;
[this workflow](CONTEXT.md) describes how scoped development is carried out.
[Current status](status.md) is the single short current-checkpoint router.
Historical documents and individual run records remain evidence about their
own checkpoint, not competing current instructions.

## After a scoped change

1. Review the changed component's source and actual consumers. Update the map
   card and explicit impact/non-impact boundaries when their facts changed.
2. Update the run product and status link as needed. New working folders require
   a small `CONTEXT.md`; stable template folders hold forms, not run results.
3. From the repository root, refresh derived navigation and check the result:

   ```bash
   python scripts/maintain_icm.py --write
   python scripts/maintain_icm.py --check
   ```

4. Inspect the generated diff. A successful navigation check establishes only
   the checks it reports, not correctness of trading behavior or acceptance of
   market data. Use the existing component tests and exact-commit gates.

## When a linked source changes

A source fingerprint mismatch is a review request, not permission to overwrite
the stored fingerprint. Read the changed source and affected consumers, reconcile
the map's claims and explicitly record unknown impact. Only after that review:

```bash
python scripts/maintain_icm.py --accept-reviewed-sources
python scripts/maintain_icm.py --write
python scripts/maintain_icm.py --check
```

Do not run acceptance merely to make CI green. Record which sources were
re-reviewed and the conclusion in the run's verification product. Inspect the
fingerprint diff so unrelated drift cannot silently be accepted. The command is
documentation maintenance, not research-policy promotion or provider authority.

## Routing and file changes

Use ordinary relative Markdown links for real repository files. Explain dynamic
run/template notation once in the [workflow router](CONTEXT.md); do not represent
a placeholder as a broken live link. Generated indexes must distinguish actual
products from stable templates and planned paths.

Before renaming, moving or deleting a path, inspect source, tests, scripts,
workflows, manifests and references that consume it. Local search cannot prove
the absence of external consumers: keep those unknown unless verified. A move
outside the approved additive scope needs the owner's approval. Preserve frozen
captures, manifests, registrations and historical evidence in place; corrections
use source-linked child artifacts and revised routers rather than mutation of
the original bytes.

## Review budget

Cold-walk only the affected navigation slice: start at the small entry router,
follow a task to its card or stage, and verify that the reader can locate exact
inputs, output and next action without the full archive. Broader restructuring
may warrant multiple representative slices. Record the slices and findings,
including stale or unknown dependencies; do not claim an exhaustive audit from
one successful route.

Keep [shared project rules](../../AGENTS.md) canonical. Remove duplicated
instruction payload from subordinate routers, but never remove a component's
specific frozen acceptance contract. New context files should route to those
contracts rather than override them. The method comes from
[ICM Architect](https://github.com/RinDig/icm-architect); consult the preserved
[upstream metadata](../map/_meta/CONTEXT.md) for the adopted version and license.
