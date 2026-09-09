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

## Start here

**New Vantiq project, first session.** Two commands, once:

```bash
python vq.py init /path/to/my-vantiq-project
```

```bash
cd /path/to/my-vantiq-project && claude
```

`init` vendors the harness into `tools/vharness` **and** writes the `CLAUDE.md`
section that tells Claude it exists. Claude Code reads that on the first turn,
so the doctrine is in context before you type anything — you never have to
remember to mention it.

The only prerequisite is a `.mcp.json` in the project holding a Vantiq server
entry, which the MCP integration already writes. If it is missing, `init` says
so and explains what one is.

**Already have a project and just want to look?** `NOTES.md` needs no install
at all, and `python vq.py check <project>` only reads. Full walkthrough in
[How to use it](#how-to-use-it).

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

## How to use it

In this order. Each step is useful on its own, so stop wherever it stops
paying.

### 1. Set the project up so Claude knows the harness is there.

```bash
python vq.py init <project>
```

Both halves of that matter. Copying the files is the easy one; a harness Claude
has not been *told* about does not get used, and instead re-derives the same
checks badly or trusts a 200.

What lands in your `CLAUDE.md`, so you know before you run it: the four
commands, a pointer to `NOTES.md`, and one paragraph of doctrine. Deliberately
short — a `CLAUDE.md` listing every trap gets skimmed and ignored, and the traps
belong in `NOTES.md` where each carries the error text that earned it. What has
to be in context from the first turn is the habit, not the lookup table.

Safe to re-run, which you will after every upgrade: the section sits between
`<!-- vantiq-harness:begin -->` markers and is replaced rather than stacked, and
an existing `CLAUDE.md` is appended to, never overwritten.

`vq.py install` does the files-only half, if you would rather wire up context
yourself.

### 2. Read `NOTES.md`. Install nothing.

224 behaviours, each with the error text that earned it. This is the highest
value per minute in the repo and it costs one browser tab. Most of what it
records is not something a linter can catch - it is the afternoon you would
otherwise spend finding out why a rule that compiles never fires.

If you only ever do this, the harness has paid for itself.

### 3. Point `check` at a namespace you already have. It only reads.

```bash
python vq.py check <project>
```

`<project>` is any folder holding a `.mcp.json` with a Vantiq server entry -
what the MCP integration already writes. No writes, no config, no arguments:
the application package is discovered from the namespace itself.

Most Vantiq projects have **no local VAIL at all** - three on the machine this
was built from hold 527, 657 and 501 procedures and not one `.vail` file - so by
default this lints what is *deployed*. If a `src/procedures/` tree exists it
lints that instead, and it understands both the hand-maintained layout and the
Vantiq exporter's.

Expect a handful of findings on a healthy project, not hundreds. **If you get
hundreds, that is a bug in this tool rather than a verdict on your namespace** -
please open an issue, because that is exactly how the last 94% of false
positives were found.

### 4. Before a demo, ask what is quietly broken and what it costs.

```bash
python vq.py health <project>
```

```bash
python vq.py ops <project>
```

`health` reports compile state at the procedure *and* service level, because a
procedure reading `vailErrors: null` on a service that declares an interface
proves nothing. `ops` measures what an idle browser tab costs per day and lists
what is scheduled - including scheduled events firing into a topic nothing
subscribes to, which is the failure that reads as healthy.

### 5. Only if you write VAIL locally: push through the gates.

```bash
python vq.py push <project> com.example.app
```

lint, snapshot, drift, push, interface, `vailErrors` at both levels, smoke. It
refuses to write if the lint fails or a signature has drifted from the deployed
interface. `allow_drift=True` is for updating the interface in the same push,
and nothing else.

### Contributing what you learned

```bash
python mine_sessions.py --out candidates.md
```

Walks your own Claude Code history and produces a redacted pile of candidates;
then follow the prompt in `EXTRACT-LEARNINGS.md`. **Read the credential census
it prints and rotate anything live** - the report is redacted, your transcripts
are not. Drop the result in `learnings/` and re-run `notes_index.py`.

Four people have done this so far, and the fourth still found five things the
first three had missed.

### Running the tool on itself

```bash
python selftest.py                      # 125 assertions, run after any rule change
python notes_index.py                   # regenerate NOTES.md
python vq.py install <project>          # vendor into a project's tools/vharness
```

```python
from client import Client
from lint import check_namespace
check_namespace(Client(repo="<project>"), "com.example.app")
```


## What each module does

| Module | What it does |
|---|---|
| `source.py` | Position-preserving view with strings and comments blanked. Everything else builds on it. |
| `lint.py` | 29 static rules on VAIL, one per trap that has actually cost us. Reads a source tree **or a live namespace**. |
| `uilint.py` | 7 rules on a hosted console, all of them defects that shipped. |
| `client.py` | A client that treats an error inside a 200 as an error, and knows the paths that look plausible and are wrong. |
| `push.py` | lint, snapshot, drift, push, interface, vailErrors, smoke, report. |
| `opscheck.py` | What a screen costs per poll, and per day with nobody watching. Also what is scheduled, and what it is firing into. |
| `selftest.py` | Proves every rule fires on the real failure and stays quiet on the near-miss. 125 assertions. |
| `notes_index.py` | Builds `NOTES.md` from the demo series and from `learnings/`. |
| `learnings/` | The pooled corpus: one file per developer, produced with `EXTRACT-LEARNINGS.md`. |
| `sync.py` | Vendors the harness into each demo's `tools/vharness`. |

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

Twelve files plus `learnings/`. **Python 3.6 or later and nothing else** — no third-party packages,
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
- Of the 224 recorded behaviours, 41 are conventions that cannot be detected
  statically and 105 more have not been triaged. `NOTES.md` lists both honestly
  rather than implying coverage: 78 enforced is a third of them, not most.
- `opscheck` measures; it does not tune. The levers are a judgement call.
