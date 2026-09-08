"""Build NOTES.md: every recorded learning, and what in the harness enforces it.

The knowledge from seven demos is scattered across three places that nobody
reads together:

  Supply Chain Mgt/docs/platform-notes.md   47 numbered platform behaviours
  Defense/README.md section 13              24 numbered defects
  Logistics/README.md                       a defect log in prose

This generates the index rather than transcribing it, so a note added to any of
those sources shows up here as uncovered on the next run instead of being
silently forgotten.

COVERAGE is the only hand-maintained part, and it is deliberately honest: most
notes are NOT enforceable, and saying so is more useful than implying the
harness has them covered.
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
UP = os.path.dirname(HERE)

# Where the demo series might sit relative to this file. The harness used to
# live INSIDE the demo series, so `..` was enough; it now also gets copied into
# a workspace of its own beside it, and a single hardcoded parent made
# notes_index refuse with "none of the source documents are present" when the
# documents were one directory over. Resolution is by search, and an
# unresolvable source is simply skipped.
ROOT_CANDIDATES = [UP, os.path.join(UP, "Flagship Demo Series"), HERE]


def _find(*parts):
    for root in ROOT_CANDIDATES:
        path = os.path.join(root, *parts)
        if os.path.exists(path):
            return path
    return os.path.join(ROOT_CANDIDATES[0], *parts)


SOURCES = [
    ("platform", _find("Supply Chain Mgt", "docs", "platform-notes.md"),
     r"^#{1,4}\s*(.+)$"),
    ("defense", _find("Defense", "README.md"),
     r"^#{2,5}\s*(13\.\d+\s+.+)$"),
]

# note key -> (what enforces it, where)
# "convention" means it cannot be checked and lives in the scaffold or a review.
COVERAGE = {
    "return` inside a block":            ("lint", "indented-return"),
    "Reserved words":                    ("lint", "reserved-var"),
    "`update` is a reserved word":       ("lint", "reserved-var"),
    "no `while` loop":                   ("lint", "while-loop"),
    "sort()` takes a field NAME":        ("lint", "sort-closure"),
    "A map is a Groovy":                 ("lint", "map-keys"),
    "date()` compiles":                  ("lint", "date-call"),
    "DELETE` requires a WHERE":          ("lint", "delete-no-where"),
    "in-block `return` trap":            ("lint", "indented-return"),
    "clean push does NOT mean":          ("push", "smoke"),
    "vailErrors: null` on a procedure":  ("push", "drift + vailErrors, both levels"),
    "interface trap is worse":           ("push", "drift + smoke"),
    "Procedures carry their own":        ("client", "vail_errors, both levels"),
    "hides from a filter":               ("client", "procedures() filters on serviceName"),
    "ars_dontExport` persists":          ("publish", "export policy follows the credential"),
    "ways an export lies":               ("publish", "verify by read-back"),
    "13.3":                              ("uilint", "hardcoded-endpoint"),
    "13.9":                              ("uilint", "swallowed-refusal"),
    "13.19":                             ("uilint", "grid-min-width"),
    "13.22":                             ("lint + uilint", "mojibake"),
    "13.15":                             ("convention", "replay must not reproduce uuid()"),
    "13.20":                             ("convention", "a derived measure must not go negative"),
    "13.13":                             ("convention", "a race that survives its own fix"),
    "sort()` throws on an empty array":  ("convention", "guard every sort and slice"),
    "similaritySearch":                  ("convention", "positional signature"),
    "confidence floor":                  ("convention", "retrieval needs a floor"),
    "semantic index cannot be repointed": ("convention", "replace, never update"),
    "scheduledevents":                   ("opscheck", "required fields, interval in ms"),
    "idle browser tab":                  ("opscheck", "idle cost per day"),
    "O(n^3) scan":                        ("opscheck", "polled procedure cost"),
    "wakes all four monitoring":         ("opscheck", "handler fan-out"),
    "namespace LOAD":                    ("opscheck", "load, not activity"),
    "schedulers that ignore":            ("opscheck", "schedulers while stopped"),
    "once per cluster node":             ("opscheck", "per-node multiplication"),
    "stops itself":                      ("convention", "watchdog sized to the slowest heartbeat"),
    "errors in the namespace were thrown": ("convention", "do not let the checker be the top error"),
    "Read-then-insert dedup":            ("convention", "a unique index, not a read"),
    "Concurrent mutations tore":         ("convention", "serialise mutations"),
    "Threshold state survives a reset":  ("convention", "reset must clear derived state"),
    "identical HTML is not free":        ("uilint", "setHTML guard, see the console"),
    "felt slow because it re-asked":     ("convention", "cache and diff before painting"),
    "overflow-x: auto` does not":        ("uilint", "grid-min-width"),
    "hidden` does nothing on a bare":    ("convention", "svg needs display:none"),
    "Visibility must never depend":      ("convention", "state, not animation"),
    "Chart colours are computable":      ("convention", "validate contrast, do not eyeball"),
}


# ---------------------------------------------------------------------------
# The pooled professional-services corpus, 2026-09.
#
# Three developers audited their own Claude Code history independently, using
# the prompt in EXTRACT-LEARNINGS.md, and filed 140 entries between them. Unlike
# SOURCES above, these files SHIP with the harness in learnings/, so this half
# of the index regenerates anywhere.
#
# Keyed by entry id, because the entries have one and a substring match on a
# title is how you cover the wrong thing.
POOLED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learnings")

POOLED_COVERAGE = {
    # --- lint ---------------------------------------------------------------
    "NR-03": ("lint", "chained-procedure-call"),
    "NR-05": ("lint", "reserved-var"),
    "NR-06": ("lint", "reserved-var"),
    "NR-07": ("lint", "bare-array-type"),
    "NR-08": ("lint", "modifier-on-standalone"),
    "NR-09": ("lint", "instant-method"),
    "NR-12": ("lint", "where-method-call"),
    "NR-17": ("lint", "unimported-system-service"),
    "NR-18": ("lint", "unimported-topic"),
    "NR-22": ("lint", "dollar-operator-collapse"),
    "PS-02": ("lint", "rule-topic-package"),
    "PS-04": ("lint", "instant-method + missing-builtin"),
    "PS-13": ("lint", "private-cross-service"),
    "DM-01": ("lint", "dynamic-source"),
    "DM-04": ("lint", "exception-placeholder"),
    "DM-05": ("lint", "missing-builtin"),
    # --- client -------------------------------------------------------------
    "NR-30": ("client", "_path_trap, system. prefix"),
    "NR-31": ("client", "put(), POST then PUT compiles"),
    "NR-33": ("client", "is_not_found"),
    "NR-35": ("client", "document() uses /docs/"),
    "NR-36": ("client", "strip_server_fields"),
    "NR-48": ("client", "procedures() filters ars_namespace"),
    "NR-51": ("client", "namespace() / assert_namespace"),
    "DM-16": ("client", "_path_trap, custom/ not types/"),
    "DM-21": ("client", "namespace() / assert_namespace"),
    "DM-18": ("client", "procedures() reads `script`"),
    "NR-01": ("client", "vail_errors, both levels"),
    "DM-06": ("client", "vail_errors, both levels"),
    # --- opscheck -----------------------------------------------------------
    "NR-38": ("opscheck", "scheduled_faults"),
    "PS-14": ("opscheck", "scheduled_faults"),
    "PS-15": ("opscheck", "service_schedule_faults"),
    "PS-16": ("opscheck", "dead_schedules"),
    "NC-01": ("lint", "missing-return-colon + end-terminator"),
    "NC-02": ("lint", "public-modifier"),
    "NC-04": ("lint", "bare-array-type"),
    "NC-05": ("lint", "when-alias"),
    "NC-07": ("lint", "insert-object-literal"),
    "NC-06": ("client", "body_trap"),
    "NC-08": ("client", "strip_server_fields"),
    "NC-11": ("client", "body_trap"),
    "NC-09": ("push", "vailErrors is the gate, not validateVAIL"),
    # --- uilint -------------------------------------------------------------
    "NR-20": ("uilint", "topic-subscription"),
    "PS-22": ("uilint", "topic-subscription"),
    # --- push ---------------------------------------------------------------
    "NR-02": ("push", "vailErrors is the gate, not validateVAIL"),
    "NR-23": ("push", "drift + vailErrors, both levels"),
    "NR-24": ("push", "drift + vailErrors, both levels"),
    "DM-08": ("push", "drift + vailErrors, both levels"),
    "PS-09": ("push", "drift + vailErrors, both levels"),
    "PS-10": ("push", "drift + vailErrors, both levels"),
    # --- convention: real, and no check can see it --------------------------
    "NR-13": ("convention", "alias a parameter before using it in WHERE"),
    "NR-14": ("convention", "gate on a flag; return does not exit"),
    "NR-15": ("convention", "SELECT ONE throws on 2+; use LIMIT = 1"),
    "NR-26": ("convention", "an encrypted property cannot be queried at all"),
    "NR-27": ("convention", "mint a token at the point of use"),
    "NR-41": ("convention", "pass the correlation id in; do not reply"),
    "NR-42": ("convention", "run a GenAI flow once before calling it done"),
    "NR-43": ("convention", "export a live instance; do not extrapolate"),
    "NR-49": ("convention", "quotas are per Manager"),
    "NR-50": ("convention", "copy quota keys from the default JSON exactly"),
    "PS-06": ("convention", "the platform lint gate has known false positives"),
    "PS-12": ("convention", "fan out on a Topic, not an outbound service event"),
    "PS-17": ("convention", "address records by _id, not your natural key"),
    "PS-18": ("convention", "no data-generator sourceimpl; fake the feed"),
    "PS-20": ("convention", "never pass an empty `service` to executeProcedure"),
    "PS-23": ("convention", "call the GenAI procedure directly or lose streaming"),
    "DM-02": ("convention", "a SELECT of count() is a one-row list"),
    "DM-10": ("convention", "confirm the version before using Concurrent.*"),
    "DM-11": ("convention", "initialise service state; wrap the tick in try/catch"),
    "DM-14": ("convention", "unwrap pythonCallResults"),
    "DM-35": ("convention", "a deploy deletes what the target has and the source does not"),
    "DM-36": ("convention", "the connector script is a document, not a file on the host"),
    "DM-37": ("convention", "client event subscriptions are IDE-only"),
    "NC-03": ("convention", "retry a PROCEDURE header with the short service name"),
    "NC-10": ("convention", "restart before trusting a subagent's MCP tool list"),
}


# Titles are lifted verbatim out of documents written for internal readers, and
# NOTES.md ships publicly. Anything here that names a deployment, a namespace or
# a customer is replaced on the way through, so a regeneration cannot quietly
# put it back. Add to this rather than editing NOTES.md by hand.
REDACTIONS = [
    ("dev.US", "<deployment>"),
]


def redact(title):
    for needle, replacement in REDACTIONS:
        title = title.replace(needle, replacement)
    return title


def classify(title):
    for key, (where, what) in COVERAGE.items():
        if key.lower() in title.lower():
            return where, what
    return None, None


def collect():
    rows = []
    for label, path, pattern in SOURCES:
        if not os.path.exists(path):
            continue
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for title in re.findall(pattern, text, re.M):
            title = title.strip()
            if len(title) < 6:
                continue
            title = redact(title)
            where, what = classify(title)
            rows.append((label, title, where, what))
    return rows


def collect_pooled():
    """Every entry in learnings/, as (author, id, title, status, where, what).

    Parses the format EXTRACT-LEARNINGS.md asks for, so a colleague who runs
    that prompt and drops their file in learnings/ appears in the next NOTES.md
    as uncovered, which is the point.
    """
    rows = []
    if not os.path.isdir(POOLED_DIR):
        return rows
    for fn in sorted(os.listdir(POOLED_DIR)):
        if not fn.startswith("VANTIQ-LEARNINGS-") or not fn.endswith(".md"):
            continue
        author = fn[len("VANTIQ-LEARNINGS-"):-len(".md")]
        text = io.open(os.path.join(POOLED_DIR, fn),
                       encoding="utf-8", errors="replace").read()
        title = None
        for line in text.splitlines():
            head = re.match(r"^###\s+(.+?)\s*$", line)
            if head:
                title = head.group(1)
                continue
            ident = re.match(r"^-\s+\*\*id\*\*:\s*([\w-]+)", line)
            if ident and title:
                where, what = POOLED_COVERAGE.get(ident.group(1), (None, None))
                rows.append((author, ident.group(1), redact(title), where, what))
                title = None
    return rows


def build():
    rows = collect()
    pooled = collect_pooled()
    # NOTES.md ships as a generated artifact, so anyone who receives this
    # harness gets the content. Only someone with the original demo series can
    # REGENERATE the SOURCES half, and running this without those documents
    # would silently replace 73 learnings with a shorter file. Refuse instead.
    # The pooled half ships in learnings/ and regenerates anywhere.
    if not rows:
        raise SystemExit(
            "none of the source documents are present, so the demo-series half\n"
            "of the index cannot be rebuilt. NOTES.md already in this folder is\n"
            "the shipped copy: keep it. To add a learning of your own, drop a\n"
            "VANTIQ-LEARNINGS-<you>.md in learnings/ (see EXTRACT-LEARNINGS.md)\n"
            "or point SOURCES at your own records.")
    enforced = [r for r in rows if r[2] and r[2] != "convention"]
    convention = [r for r in rows if r[2] == "convention"]
    uncovered = [r for r in rows if not r[2]]

    p_enforced = [r for r in pooled if r[3] and r[3] != "convention"]
    p_convention = [r for r in pooled if r[3] == "convention"]
    p_uncovered = [r for r in pooled if not r[3]]
    authors = sorted(set(r[0] for r in pooled))

    out = []
    out.append("# What this platform does that surprises you\n")
    out.append("Generated by `notes_index.py` from the places seven demos wrote "
               "things down, plus the pooled professional-services corpus in "
               "`learnings/`. Do not edit by hand: add the note to its source "
               "and re-run.\n")
    out.append("| | demo series | pooled PS | total |\n|---|---|---|---|\n")
    out.append("| recorded learnings | %d | %d | %d |\n"
               % (len(rows), len(pooled), len(rows) + len(pooled)))
    out.append("| enforced by a check | %d | %d | %d |\n"
               % (len(enforced), len(p_enforced), len(enforced) + len(p_enforced)))
    out.append("| convention only, cannot be checked | %d | %d | %d |\n"
               % (len(convention), len(p_convention),
                  len(convention) + len(p_convention)))
    out.append("| not yet triaged | %d | %d | %d |\n"
               % (len(uncovered), len(p_uncovered),
                  len(uncovered) + len(p_uncovered)))
    if authors:
        out.append("\nPooled entries come from %s (`learnings/`), each produced "
                   "independently with the prompt in `EXTRACT-LEARNINGS.md`. "
                   "The id in each row is the entry, where the evidence and its "
                   "provenance live.\n" % ", ".join(authors))

    out.append("\n## Enforced\n\n")
    out.append("| Learning | Layer | Check |\n|---|---|---|\n")
    for _l, title, where, what in enforced:
        out.append("| %s | `%s` | `%s` |\n" % (title.replace("|", "/")[:96], where, what))

    out.append("\n## Convention only\n\n")
    out.append("These cannot be detected statically. They belong in the scaffold, "
               "in review, or in a comment next to the code they govern.\n\n")
    out.append("| Learning | What to do |\n|---|---|\n")
    for _l, title, _w, what in convention:
        out.append("| %s | %s |\n" % (title.replace("|", "/")[:96], what))

    if p_enforced:
        out.append("\n## Enforced, from the pooled corpus\n\n")
        out.append("| id | Learning | Layer | Check |\n|---|---|---|---|\n")
        for _a, ident, title, where, what in sorted(p_enforced, key=lambda r: r[1]):
            out.append("| %s | %s | `%s` | `%s` |\n"
                       % (ident, title.replace("|", "/")[:92], where, what))

    if p_convention:
        out.append("\n## Convention only, from the pooled corpus\n\n")
        out.append("| id | Learning | What to do |\n|---|---|---|\n")
        for _a, ident, title, _w, what in sorted(p_convention, key=lambda r: r[1]):
            out.append("| %s | %s | %s |\n"
                       % (ident, title.replace("|", "/")[:92], what))

    out.append("\n## Not yet triaged\n\n")
    out.append("Recorded, but nobody has decided whether it is checkable. This "
               "list existing is the point: it shrinks or it explains itself.\n\n")
    for _l, title, _w, _x in uncovered:
        out.append("- %s\n" % title.replace("|", "/")[:110])
    for _a, ident, title, _w, _x in sorted(p_uncovered, key=lambda r: r[1]):
        out.append("- %s %s\n" % (ident, title.replace("|", "/")[:106]))

    text = "".join(out)
    io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "NOTES.md"),
            "w", encoding="utf-8", newline="\n").write(text)
    return (len(rows) + len(pooled), len(enforced) + len(p_enforced),
            len(convention) + len(p_convention), len(uncovered) + len(p_uncovered))


if __name__ == "__main__":
    n, e, c, u = build()
    print("NOTES.md: %d learnings, %d enforced, %d convention, %d untriaged" % (n, e, c, u))
