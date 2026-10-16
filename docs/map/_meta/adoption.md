# ICM adoption — approved additive migration

## Method and scope

Adapted from [RinDig/icm-architect](https://github.com/RinDig/icm-architect/tree/e16cafe6a664dcf6d787a726b452adba77d913f4),
revision `e16cafe6a664dcf6d787a726b452adba77d913f4`.
Upstream method: ICM (Van Clief & McDermott); [MIT license](icm-architect-LICENSE.txt)
retained for adapted contracts/templates. No upstream install script is run and
no third-party skill is allowed to override repository safety boundaries.

Owner approved the proposed additive structure on October 15, 2026, 22:10 Chicago.
Baseline: `53989a5f1637e759a3922980b40f24cbfbaab5fb`, 1,945 tracked files.
The inventory found no symlinks or case-folded destination collisions.
No file was classified Dead and no existing file is moved or deleted.

Inventory area dates were checked through GitHub history: AGENTS, source, scripts,
tests, workflows, research and the dated checkpoint last changed at the baseline
commit on September 17. The older current_state.md last changed August 20 at
ced4115107e5ba22b1f9fd6aa9aa7db5d18ec6ef. Runtime completion on September 19 is
separate hosted evidence, not a later source commit.

## Approved migration map

| Before | After | Role and referrers |
|---|---|---|
| AGENTS.md (171 lines, 28,710 bytes) | Same path, compact mandatory rules and routes | Catalog/constraints; README, historical records and five validation workflows retain this path |
| 111 AGENTS task triples | [task-routes.md](../task-routes.md), extracted without alteration | Historical catalog; all original destinations remain |
| README cold-start direction | Root CONTEXT and new status route | Catalog; old checkpoint links remain historical |
| Competing docs/project checkpoint files | Unchanged; [status](../../agent-workflow/status.md) is active handoff | Historical products; never rewrite provenance |
| Source, tests, workflows, research archives | Unchanged paths and bytes, except additive maintenance script/tests | Factory/product; source cards cite rather than relocate |
| No system map or work templates | docs/map and docs/agent-workflow | New catalog/contracts/factory; run records are separate products |

The extraction is verified against the baseline route table. Original root safety
boundaries remain verbatim; streamlined verification/authorization rules remain binding.

## Reference integrity

AGENTS.md is named by README, two checkpoint/handoff documents, the early-pullback
paired-adapter document, three historical audit JSON records, a retained publication
ZIP, and five legacy workflow path filters. Its path is retained. Those workflows'
provider jobs require workflow_dispatch; editing navigation cannot authorize them.

The dated checkpoint has seven text referrers and a retained ZIP reference.
It and all earlier documents remain byte-identical. The historical exposure scanner
in [sealed_historical_walk_forward.py](../../../src/momentumbot/research/sealed_historical_walk_forward.py)
scans research, docs/research and docs/project. Several archived Markdown files are
also hash-pinned by Python registrations. New map/workflow records stay outside
those scan roots.

External consumers/bookmarks are unknown, not presumed absent. The approved
change retains all existing paths. Before any future move, ask the owner about
external consumers, enumerate local/relative/symlink references, check case-fold
collisions, copy, verify byte parity, then remove only under explicit approval.

## Applying all ten ICM invariants

| Invariant | Implementation |
|---|---|
| One folder, one job | Map shelves and workflow stage CONTEXT contracts |
| Small entry | Root AGENTS and map CLAUDE under 60 lines; map twins generated |
| Sequence in names | Four numbered development stages; objects are not falsely ordered |
| Explicit contracts | Working/reference inputs, process, outputs and concrete review |
| Factory/product split | Stable _templates separate from runs and immutable research products |
| Editable outputs | New scope/change/review drafts are editable; frozen research needs a child artifact |
| Layered loading | Catalog → selected card → selected cited source; no transcript/runtime mixing |
| Plain, linked state | Markdown frontmatter, relative links, JSON evidence and source locks |
| Filesystem status | Run records distinguish pending/passed/blocked; existence alone is not success |
| Copy to instantiate | Work-item and object/process templates; never invent completed evidence |

## Deliberate safety adaptations

This is a System Map with a development Pipeline, not a replacement trading runtime.
ICM explicitly excludes high-concurrency/event-driven serving from its sweet spot.
Existing tests, risk/order state machines, CI and consumed provider jobs keep their
orchestration. Human gates govern scope/new authority; ordinary authorized internal
slices can use the upstream cold-walk alternative without adding approval-only commits.
Binary source archives and signed/hash-bound artifacts remain immutable. Their
plain-text status/provenance is the editable interface, not their source bytes.
