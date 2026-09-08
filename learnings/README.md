# The pooled corpus

One file per developer, each produced independently by running the prompt in
`../EXTRACT-LEARNINGS.md` over that person's own Claude Code history. Nobody
reconciled them; the shape is fixed so they merge without anyone having to.

| File | Entries | Ids | Weighted toward |
|---|---|---|---|
| `VANTIQ-LEARNINGS-DM.md` | 62 | `DM-nn` | connectors, Python sources, k8s install and upgrade |
| `VANTIQ-LEARNINGS-NR.md` | 54 | `NR-nn` | VAIL semantics, REST and MCP shapes, GenAI flows |
| `VANTIQ-LEARNINGS-PS.md` | 24 | `PS-nn` | service interfaces, scheduled events, EDA wiring |

Files are named for the id prefix their entries use rather than for their
author. That is deliberate for a public repository: the people who wrote these
agreed to pool them inside the company, not to have their name attached to a
defect log on the open internet. If an author would rather be credited, put the
name back.

`../NOTES.md` indexes all of them by id and says which are enforced, which are
convention, and which nobody has triaged. Run `python ../notes_index.py` after
adding a file.

## Reading an entry

`status: verified` means the author could point at the failure — the platform's
error text, or the failing code beside the fixed code. `unverified` means they
could not, and said so. Both are here on purpose: the prompt asks for the gap to
be stated rather than smoothed over, and each file ends with a `Gaps` section
that is worth reading before trusting the entries above it.

## Before you turn one into a rule

Read the evidence, not the title. Three entries did not survive that step, and
each is recorded in `../lint.py` beside the rule it would have been:

- **DM-03** (`->` never compiles) — the failing line also called a method that
  did not exist, from the same session; the arrow was never tested alone.
- **PS-05** (`state` is reserved) — 68 uses in shipping code across two demos.
- **DM-10** (`Concurrent.*` does not exist) — 11 uses in one demo; the entry's
  own fix line concedes it is version-dependent.

Then sweep it. `check_tree` over a codebase you did not write is what found all
three, and it took one run.

## Adding yours

Drop `VANTIQ-LEARNINGS-<yourname>.md` in this directory. Entries appear in
`NOTES.md` as untriaged until someone maps the id in `POOLED_COVERAGE`, which is
the honest default — most learnings are not checkable, and about a fifth are.

Assume these files get forwarded outside the team: no customer names, no
namespace names, no credentials. `mine_sessions.py` redacts credentials and
cannot recognise a customer.
