"""Pull the candidate learnings out of a local Claude Code history.

This does the plumbing and none of the judging. It produces a pile of candidates
with enough context to rule on; deciding what is a platform behaviour and what is
one project's convention is the part a person or a model has to do.

Four things here were measured against a real history of 22 sessions and 347
subagent transcripts, and each is a mistake that looks fine until you check it:

  * TRANSCRIPTS NEST, AND MOST ARE NOT SESSIONS. `projects/*/*.jsonl` finds the
    22 real sessions and misses the 347 subagent transcripts under
    `<project>/<session>/subagents/`. Their ASSISTANT text is worth mining.
    Their `user` records are prompts written by the parent session, not by a
    person, so the correction pass skips them.

  * "type":"user" IS MOSTLY NOT A HUMAN. 4,406 of 4,600 user records in a sample
    were tool_result blocks. Treating them as user speech buries the 179 real
    turns under a 25:1 noise ratio. A human turn is a string `content`, or a list
    carrying a `text` block.

  * BROAD MARKERS DO NOT NARROW ANYTHING. "actually", "trap", "gotcha" and
    "groovy" are ordinary vocabulary in this work: they matched 14,490 records.
    The markers below are reversals and platform nouns only, and they matched
    1,957. Widen them and you get a pile nobody will read.

  * A HISTORY IS FULL OF CREDENTIALS. See SECRETS below, and the census printed
    at the end of every run. Check it before you trust any file you are about to
    send to someone.

The highest-value output is the smallest: turns where a person said the last
answer was wrong. There are single digits of those in a year of work, and the
learning is usually in the reply that follows.
"""
import argparse
import io
import json
import os
import re
import sys

# Reversals and platform nouns. Deliberately narrow: see the module docstring.
MARKERS = re.compile(
    r"i was wrong|turns out that|that is not what|the real (problem|cause|answer)"
    r"|silently (fail|break|drop|ignor|overwrit|discard)"
    r"|returns? (HTTP )?200 (and|but|while|carrying)"
    r"|vailError|will not compile|stopped compiling|startup failed"
    r"|reserved word|undocumented", re.I)

# A person saying the previous answer was wrong.
#
# Tightened after the first version's top hit was a subagent prompt containing
# "so it still reads well". `it still` on its own is ordinary English; it has to
# be followed by a failure. Loose matching gave 69 hits, nearly all noise. This
# gives single digits, nearly all real, which is the correct shape for a signal
# this valuable.
PUSHBACK = re.compile(
    r"^\s*(no[,.! ]|nope|wrong\b|that.s (wrong|not right))"
    r"|\b(you (were|are) wrong|that.s not (right|correct|what)"
    r"|still (broken|wrong|failing|doesn.t|does not|not working)"
    r"|it still (fails|breaks|doesn|does not|shows|returns|says)"
    r"|doesn.t work|didn.t work|did not work|not what i (asked|wanted|said))", re.I)

# A script cannot recognise a customer name. It can recognise a credential, and a
# credential must not reach a file that gets forwarded to a team.
#
# THIS LIST IS NOT THEORETICAL. Scanned against one engineer's history it found
# 3,701 Vantiq tokens across 92 transcripts, 63 JWTs, and an Anthropic API key
# pasted into a session in plaintext. An earlier version of this file carried
# only the first three patterns and matched none of the API key: a session
# transcript is a place people paste secrets, and the shapes are worth knowing.
#
# The reader is still responsible for names, hostnames, namespaces and paths.
SECRETS = [
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "<REDACTED-KEY>"),
    ("openai key", re.compile(r"\bsk-[A-Za-z0-9]{32,}"), "<REDACTED-KEY>"),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "<REDACTED-KEY>"),
    ("slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}"), "<REDACTED-KEY>"),
    ("aws key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<REDACTED-KEY>"),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "<REDACTED-KEY>"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
     "<REDACTED-JWT>"),
    ("private key block",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     "<REDACTED-PRIVATE-KEY>"),
    ("vantiq token",
     re.compile(r"(?<![A-Za-z0-9_\-])[A-Za-z0-9_\-]{43}=(?![A-Za-z0-9_\-=])"),
     "<REDACTED-TOKEN>"),
    ("auth header", re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]{16,}"),
     "<REDACTED-AUTH>"),
    ("named secret",
     re.compile(r"(?i)(\"?(?:password|passwd|secret|api[_-]?key|access[_-]?token)"
                r"\"?\s*[:=]\s*)\"?[^\s\"',}]{6,}"),
     r"\1<REDACTED>"),
]


def scrub(text):
    for _label, pat, repl in SECRETS:
        text = pat.sub(repl, text)
    return text


def census(root):
    """What credential shapes are sitting in this history.

    Printed before anything is written. Knowing that a key is in the transcripts
    is worth more than the extraction: the file this tool writes is redacted, and
    the transcripts it read are not.
    """
    counts = {}
    for path in transcripts(root):
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for label, pat, _repl in SECRETS:
            n = len(pat.findall(text))
            if n:
                counts.setdefault(label, [0, set()])
                counts[label][0] += n
                counts[label][1].add(path)
    return counts


def transcripts(root):
    """Every .jsonl under root, at any depth. Subagents nest three deeper."""
    out = []
    for dirpath, _dirs, files in os.walk(root):
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".jsonl")]
    return sorted(out)


def text_of(msg):
    """The prose in a message, or None. Tool results are not prose."""
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = [b.get("text", "") for b in c
                 if isinstance(b, dict) and b.get("type") == "text"]
        return " ".join(p for p in parts if p) or None
    return None


def default_root():
    return os.path.join(os.path.expanduser("~"), ".claude", "projects")


def project_of(path, root):
    return os.path.relpath(path, root).split(os.sep)[0]


def mine(root, since=None, width=1400):
    files = transcripts(root)
    pushbacks, markers = [], []
    for path in files:
        proj = project_of(path, root)
        # A subagent transcript carries no human turns: its `user` records are
        # prompts written by the parent session. 347 of 369 files in the history
        # this was built against were subagents, so counting their `user` records
        # as corrections made the pass almost entirely noise.
        sidechain = "subagents" in path.replace("\\", "/").split("/")
        prev_assistant = None
        pending = None          # a correction waiting for the reply that follows
        for line in io.open(path, encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            when = (rec.get("timestamp") or "")[:10]
            if since and when and when < since:
                continue
            kind = rec.get("type")
            if kind not in ("user", "assistant"):
                continue
            body = text_of(rec.get("message") or {})
            if not body:
                continue
            if kind == "user" and not sidechain and not rec.get("isSidechain"):
                if pending is not None:
                    pushbacks.append(pending)
                    pending = None
                if PUSHBACK.search(body[:600]):
                    pending = {"project": proj, "file": os.path.basename(path),
                               "date": when, "said": body[:width],
                               "before": (prev_assistant or "")[:width],
                               "after": ""}
            elif kind == "assistant":
                prev_assistant = body
                if pending is not None:
                    pending["after"] = body[:width]
                    pushbacks.append(pending)
                    pending = None
                hit = MARKERS.search(body)
                if hit:
                    lo = max(0, hit.start() - width // 2)
                    markers.append({"project": proj, "file": os.path.basename(path),
                                    "date": when, "marker": hit.group(0),
                                    "text": body[lo:lo + width]})
        if pending is not None:
            pushbacks.append(pending)
    return files, pushbacks, markers


def quote(text):
    return scrub(text).replace("\n", "\n> ")


def write_report(out_path, files, pushbacks, markers):
    w = io.open(out_path, "w", encoding="utf-8", newline="\n")
    w.write("# Candidate learnings\n\n")
    w.write("Generated by `mine_sessions.py`. Nothing here is a learning yet: "
            "these are places where something was corrected, or where a platform "
            "noun appeared next to a failure. Credentials are redacted "
            "automatically. Customer names, hostnames and paths are NOT, and are "
            "the reader's job.\n\n")
    w.write("| | count |\n|---|---|\n")
    w.write("| transcripts scanned | %d |\n" % len(files))
    w.write("| user corrections | %d |\n" % len(pushbacks))
    w.write("| marker records | %d |\n\n" % len(markers))

    w.write("## User corrections\n\n")
    w.write("Read every one. The user saying the last answer was wrong is the "
            "strongest signal in a transcript, and the learning is usually in the "
            "reply that follows.\n\n")
    for i, p in enumerate(pushbacks, 1):
        w.write("### C%03d  %s  %s\n\n" % (i, p["date"], p["project"][-46:]))
        w.write("- source: `%s`\n" % p["file"])
        if p["before"]:
            w.write("\n**claimed**\n\n> %s\n" % quote(p["before"]))
        w.write("\n**user**\n\n> %s\n" % quote(p["said"]))
        if p["after"]:
            w.write("\n**then**\n\n> %s\n" % quote(p["after"]))
        w.write("\n")

    w.write("## Marker records\n\n")
    for i, m in enumerate(markers, 1):
        w.write("### M%04d  %s  %s  `%s`\n\n"
                % (i, m["date"], m["project"][-40:], m["marker"]))
        w.write("- source: `%s`\n\n> %s\n\n" % (m["file"], quote(m["text"])))
    w.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mine a Claude Code history for "
                                             "candidate platform learnings.")
    ap.add_argument("--root", default=default_root(),
                    help="projects directory (default: ~/.claude/projects)")
    ap.add_argument("--since", help="only sessions on or after YYYY-MM-DD")
    ap.add_argument("--out", default="candidates.md")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print("no Claude Code history at %s" % args.root)
        return 1
    files, pushbacks, markers = mine(args.root, args.since)
    if not files:
        print("no transcripts under %s" % args.root)
        return 1
    write_report(args.out, files, pushbacks, markers)
    print("transcripts scanned : %d" % len(files))
    print("user corrections    : %d   <- read every one" % len(pushbacks))
    print("marker records      : %d" % len(markers))
    print("wrote %s" % args.out)

    # Last, so it is the thing left on screen. The report is redacted; the
    # transcripts it was built from are not, and neither is anything else that
    # has read them.
    found = census(args.root)
    if found:
        print("\ncredentials sitting in this history, in plaintext:")
        for kind, (n, paths) in sorted(found.items(), key=lambda kv: -kv[1][0]):
            print("  %-20s %6d occurrence(s) in %d transcript(s)"
                  % (kind, n, len(paths)))
        print("\nThey are redacted in %s. They are still in the transcripts, and"
              % os.path.basename(args.out))
        print("anything with read access to your home directory can see them.")
        print("Rotate what is live. Do not paste a key into a session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
