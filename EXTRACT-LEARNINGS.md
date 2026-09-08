# Extracting what you learned building on Vantiq

Every one of us has a year of Claude Code sessions on disk that recorded platform
behaviour nobody wrote down. This is how we get it out and pool it.

## Before you start

```bash
python mine_sessions.py --out candidates.md
```

Run this first, from anywhere. It walks your Claude Code history and produces a
redacted pile of candidates, and it prints a census of the credentials sitting in
your transcripts. On the machine it was built against that census read: 3,701
Vantiq tokens across 92 transcripts, 63 JWTs, and an Anthropic API key someone
had pasted into a session. **Read that census. Rotate anything live.** The report
the script writes is redacted; your transcripts are not.

Then paste the prompt below into Claude Code in the same directory. Expect twenty
to forty minutes. Send the result to <owner>; it is merged into the shared
harness's `NOTES.md`, which is where the lint rules come from, so an entry you get
right becomes a check that saves the next person the same afternoon.

Re-run every month or two with `--since <date>`.

---

```
You are auditing my Claude Code history to recover what I learned building on the
Vantiq platform, so it can be pooled with the rest of the professional services
team. The deliverable is one file: VANTIQ-LEARNINGS-<myname>.md.


## 1. The material

Start from `candidates.md` in this directory, produced by `mine_sessions.py`. It
has two sections and they are not equally valuable:

  - **User corrections.** A handful. Every one is a moment where something was
    believed, acted on, and a person said it was wrong. Read all of them, and
    read the reply that follows each: that is usually where the learning is.
  - **Marker records.** A few hundred. Assistant messages where a platform noun
    appeared near a failure. Mostly chaff. Skim, do not study.

If `candidates.md` is not there, run `python mine_sessions.py` first. Do not go
at the raw transcripts by hand: they nest three levels deeper than you expect,
most of them are subagent transcripts with no human in them, and 96% of the
records marked "user" are tool output rather than anything a person said.

Then mine the repositories, which are often better per byte because someone
already did the distillation:
  - README.md, NOTES.md, docs/*.md in each Vantiq project, especially anything
    that reads as a defect log
  - comments in .vail source and in build scripts under tools/
  - CLAUDE.md files


## 2. What counts

Only a platform behaviour that surprised someone and cost time. The test: could
a competent developer have predicted this from the documentation? If yes it is a
fact, not a learning. Leave it out.

One project's convention is not a platform behaviour. If you cannot show it
holds outside the project you found it in, say so in the entry.


## 3. The evidence bar, which is the entire point

A lint tool was built on exactly this material. Its first version, run against
three namespaces it had not seen, produced 166 findings and every single one was
wrong. Each was a plausible-sounding rule nobody had actually watched fail.

So: a claim is not a learning until you can point at the failure. Every entry
needs at least one of these, quoted from the source:

  - the actual error text the platform returned, or
  - the code that failed alongside the code that fixed it, or
  - the exact correction I gave

If you cannot produce one, mark the entry unverified or drop it. Do not
reconstruct an error message from memory of how they usually look. Do not
generalise one namespace's quirk into a platform rule. Do not smooth over a gap
to make an entry read better. Twelve of these files are being merged and an
unverified entry will be believed. A short honest file beats a long confident
one, and I will not be disappointed by a thin result.

Note where you can whether the behaviour still holds. Some of this concerns a
platform version that has moved.


## 4. Scrub. Not optional.

`mine_sessions.py` redacts credentials automatically, and that is the easy half.
It cannot recognise a customer. Before a line reaches the output file:

  - No customer or partner names. Replace with a role: "a manufacturing
    customer", "the client's namespace".
  - No namespace names, hostnames, usernames or absolute paths that identify a
    person or an account. dev.vantiq.com is fine; a namespace name is not.
  - No customer data. No records, no volumes attached to a named account.
  - If a credential slipped past the redaction, cut it to <REDACTED> and tell me
    which file it was in so the pattern can be added.

Assume the file will be forwarded outside the team.


## 5. Output format

One file, VANTIQ-LEARNINGS-<myname>.md, using exactly this shape per entry so
the files merge without a human reconciling them:

  ### <the behaviour stated in one line, present tense>

  - **id**: <my initials>-<nn>
  - **area**: VAIL | service interface | types and data | REST and MCP |
    UI and documents | ops and cost | agents and LLM | deploy and export
  - **status**: verified | unverified
  - **cost**: minutes | hours | a day or more
  - **symptom**: what it looks like when it bites, in one sentence, written so
    someone who has hit it recognises it
  - **cause**: what is actually happening
  - **fix**: what to do instead
  - **evidence**: the quoted error, code, or correction
  - **source**: <transcript or repo file>, <date>

Sort by area. No introduction, no conclusion, no advice about how to use the
file.


## 6. Finish with a gaps section

  ## Gaps
  - candidates reviewed: <n> corrections, <n> marker records
  - date range: <first> to <last>
  - could not verify: ...
  - deliberately excluded: ...

If most of my history is one project, say so plainly. A file that presents one
namespace's quirks as platform truth is the failure mode here.


## 7. How to work

Tell me the candidate count and your plan before you start judging. Show me
entries as you confirm them rather than saving everything for the end. If you
find yourself writing an entry you cannot evidence, stop and say so instead.
```

---

## What happens to the merged file

Entries land in one of three places, and the split is deliberate:

- **Enforced.** A check can catch it. It becomes a rule in the harness with your
  evidence quoted in the rule's docstring. A guard whose reason is not written
  down gets deleted the first time it is inconvenient.
- **Convention.** Real, but not statically detectable. It goes in the scaffold or
  the review checklist.
- **Not yet triaged.** Nobody has decided. This list exists on purpose. It shrinks
  or it explains itself.

About a fifth of what has been collected so far turned out to be checkable. That
ratio is normal and is not a reason to file fewer entries.
