# vantiq-harness

Tooling for building on Vantiq, assembled from what seven flagship demos cost us
to learn, and from what four professional-services developers found when they
audited their own session history for the same thing.

**224 recorded behaviours, 78 of them enforced by a check.** See `NOTES.md`,
which is generated and lists the other 146 honestly rather than implying
coverage.

> Not an official Vantiq release, and not endorsed by or affiliated with Vantiq
> as a product. This is field notes: what a handful of developers observed on
> specific versions (mostly 1.43.x and 1.44.x) while building on the platform,
> with the evidence attached so you can judge each claim yourself. Behaviour
> changes between versions, several entries say so about themselves, and an
> entry marked `unverified` means its author could not point at the failure.
> Nothing here is customer data; see `learnings/README.md` on redaction.

## The problem it exists for

Almost every hour lost on this platform had one shape: **the write returns HTTP
200 and something is broken somewhere else, or later.**

- A parameter added to a procedure on an interface-declaring service. 200. The
  procedure reads `vailErrors: null`. Every *other* procedure in that service
  stops compiling.
- A hyphen in an object key. 200. The procedure never compiles again.
- Duplicate keys in an object literal. Parses, last one silently wins.
- A variable named `it`. Breaks the whole service, every `vailErrors` clean.
- `date()` instead of `toDate()`. Compiles, pushes, returns a String, and throws
  from a different procedure hours later.

The harness exists to replace that 200 with a real answer.

## Layers

| Module | What it does |
|---|---|
| `source.py` | Position-preserving view with strings and comments blanked. Everything else builds on it. |
| `lint.py` | 29 static rules on VAIL, one per trap that has actually cost us. Reads a source tree **or a live namespace**. |
| `uilint.py` | 7 rules on a hosted console, all of them defects that shipped. |
| `client.py` | A client that treats an error inside a 200 as an error, and knows the paths that look plausible and are wrong. |
| `push.py` | lint, snapshot, drift, push, interface, vailErrors, smoke, report. |
| `opscheck.py` | What a screen costs per poll, and per day with nobody watching. Also what is scheduled, and what it is firing into. |
| `selftest.py` | Proves every rule fires on the real failure and stays quiet on the near-miss. 119 assertions. |
| `notes_index.py` | Builds `NOTES.md` from the demo series and from `learnings/`. |
| `learnings/` | The pooled corpus: one file per developer, produced with `EXTRACT-LEARNINGS.md`. |
| `sync.py` | Vendors the harness into each demo's `tools/vharness`. |

## Use

```bash
python selftest.py                      # 119 assertions, run after any rule change
python notes_index.py                   # regenerate NOTES.md
python push.py "<repo>" com.example.app # the full pipeline
python sync.py                          # vendor into every demo
```

Most Vantiq projects have no local VAIL. Of the projects on this machine, one
keeps `src/procedures/` and at least three others are built directly in the
namespace through the MCP server, with 527, 657 and 501 procedures and not a
single `.vail` file. `check_namespace(client, package)` lints what is deployed,
which is the common case:

```python
from client import Client
from lint import check_namespace
check_namespace(Client(repo="<project>"), "com.example.app")
```

`push.py` refuses to write if the lint fails or if a signature has drifted from
the deployed interface. `allow_drift=True` is for the case where the interface is
being updated in the same push, and nothing else.

## Two rules about the rules

**Every rule cites the incident that earned it.** A guard whose reason is not
written down gets deleted the first time it is inconvenient, and each of these
was paid for once already.

**A rule that cries wolf is worse than no rule.** This is not a slogan, it is
the largest source of change in this package.

Run against three Vantiq namespaces it had never seen, the first version produced
**166 findings. Every one was wrong**, and the causes were all in the rules:

| Cause | Findings |
|---|---|
| a `return` inside a closure is correct, not the fall-through trap | 129 |
| the modifier list before `PROCEDURE` is open, not enumerable | 26 |
| `date(now(), "date", "epochMilliseconds")` is a real function | 12 |
| a ternary branch and a dotted path read as object keys | 3 |

Narrowed, it is clean on 439 hand-written procedures across four namespaces, and
every one of those false positives is now a self-test case asserting silence.

A separate rule was written, run against 59 occurrences in working code, tested
against the live namespace, disproved, and deleted. The disproof is recorded in
`lint.py` so nobody adds it back.

The lesson generalises: **a rule is not finished until it has run against a
codebase you did not write.**

## The pooled corpus, and what it cost to trust it

`learnings/` holds one file per developer, each produced independently by
running the prompt in `EXTRACT-LEARNINGS.md` over their own Claude Code history.
151 entries arrived that way in September 2026 across four files. About a
third proved checkable, better than the ratio that file predicts.

Three of them did not survive being made into rules, and the way each died is
worth more than the entry was:

| Entry | Claim | What happened |
|---|---|---|
| DM-03 | `->` is not VAIL's lambda operator and never compiles | The rule fired on an asserted-silent case that is real shipping code. Going back to the evidence, the failing line was `updateAndGet(prev -> cnt)` — and `updateAndGet` does not exist on that instance at all, which is DM-10, from the same session. The arrow was never tested on its own. |
| PS-05 | `state` is a reserved word | A sweep found `var state` **68 times** and `state` as a parameter twice, all in working code across two demos. |
| DM-10 | `Concurrent.*` / `updateAndGet` does not exist | A sweep found **11 uses** in the Retail demo. The entry's own fix line concedes the version dependence, and a static check cannot know the version. |

Two more needed narrowing rather than deleting: `unimported-topic` was reporting
11 topic paths that already carry their own package, and `where-method-call`
matched the property path `pre.where.storeId`. Both were found the same way.

All three deletions and both narrowings are recorded in `lint.py` beside the
rule that would have been, with the evidence that killed them, so the next
person reading the entry does not re-add it.

The sweep is the reason any of this is known. Across **1,757 `.vail` files in
seven demos**, the new rules went from 93 findings to 3, and the 3 remaining are
the shape their entry describes. The console rules ran over 32 hosted pages with
no new finding at all.

**If you add a rule from a pooled entry, sweep it before you commit it.** An
entry is one developer's afternoon; the sweep is everyone else's.

## Sharing this with another Vantiq developer

```bash
python vq.py package <dest>
```

Ten files. **Python 3.6 or later and nothing else** — no third-party packages,
standard library only. The recipient needs a project folder containing a
`.mcp.json` with a Vantiq server entry, which is what the MCP integration
already writes. Nothing is hardcoded to a namespace, a server or a package:
`check` discovers the application package from the namespace itself.

Verified out of the box: a clean copy outside this repo, run against three
Vantiq namespaces it did not own, self-test passing and lint clean.

**What is deliberately left behind.** `sync.py` knows one team's seven demo
folders. Half of `notes_index.py` regenerates `NOTES.md` from documents nobody
else has, and refuses rather than writing a truncated file. `NOTES.md` itself
ships, because the 224 recorded behaviours are the most portable thing here, and
so does `learnings/`, which regenerates anywhere.

**Adding your own.** Run the prompt in `EXTRACT-LEARNINGS.md` over your own
session history, drop the result in `learnings/`, and re-run `notes_index.py`.
Your entries appear as untriaged, which is the honest default; the ones worth
enforcing become rules with your evidence quoted in the docstring.

**What is house style, not platform truth.** One rule: `em-dash` in `uilint`.
It is off by default and needs `--house`. Every other rule is a defect that
shipped. Shipping a style rule as though it were a correctness rule is how a
shared tool earns a reputation for noise.

**What a recipient should change.** The rule docstrings cite incidents from this
team's projects ("Defense 13.3", "note 26"). Those are provenance, not
instructions, and they are worth keeping: a guard whose reason is not written
down gets deleted the first time it is inconvenient.

## What it does not do

- It does not check anything about the runtime behaviour of your agents.
- Roughly 16 of the recorded learnings are conventions that cannot be detected
  statically, and 28 more have not been triaged. `NOTES.md` lists both honestly
  rather than implying coverage.
- `opscheck` measures; it does not tune. The levers are a judgement call.
