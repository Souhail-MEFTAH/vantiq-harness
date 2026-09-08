"""Static checks on VAIL source, one rule per trap that has actually cost us.

Every rule here exists because the platform accepted the code and something
broke somewhere else, or later. None of them is a style preference. The docstring
on each rule records the incident, because a guard whose reason is forgotten gets
deleted the first time it is inconvenient.

Rules run against a position-preserving view with strings and comments blanked
(see source.blank), so a rule never matches its own example in a comment.
"""
import os
import re

from source import blank, line_of, line_text

# --- the signature form, in every declaration style seen in the wild ---------
#
# CASE-INSENSITIVE on the modifiers, and they appear in either order. Hand-
# written code in this series uses `PRIVATE STATELESS PROCEDURE`; the platform's
# own collaboration builder writes `stateless private PROCEDURE`. An
# uppercase-only pattern does not fail loudly on the second form, it reports
# "no PROCEDURE declaration found", which reads as a broken procedure and is
# really a broken regex. That was 26 findings across three projects.
#
# The modifier list is OPEN, not enumerated. Known forms in the wild include
# `PRIVATE STATELESS`, `stateless private`, and `PRIVATE MULTI PARTITION`.
# Enumerating them meant a new combination read as "no PROCEDURE declaration
# found", which blames the procedure for the pattern's ignorance. Whatever the
# modifiers are, the declaration ends with PROCEDURE <name>(.
SIG = re.compile(r"^[ \t]*(?:\w+[ \t]+)*PROCEDURE\s+([\w.]+)\s*\(", re.M | re.I)
PRIVATE_SIG = re.compile(
    r"^[ \t]*(?:\w+[ \t]+)*?private[ \t]+(?:\w+[ \t]+)*PROCEDURE\s+([\w.]+)",
    re.M | re.I)


class Finding(object):
    def __init__(self, rule, line, message, snippet="", note=None):
        self.rule, self.line, self.message, self.snippet = rule, line, message, snippet
        # Which entry in docs/platform-notes.md earned this rule. A guard whose
        # reason is not written down gets deleted the first time it is
        # inconvenient, and every one of these was paid for once already.
        self.note = note

    def __repr__(self):
        return "%s:%d %s" % (self.rule, self.line, self.message)


# ---------------------------------------------------------------- rules -----

def rule_indented_return(text, code, ctx):
    """A `return` inside a block does not exit the procedure.

    VAIL falls through it and the LAST top-level return is what the caller gets.
    Guard clauses written the usual way therefore do the opposite of what they
    say: a validation failure returns success. Proven by probe, not inferred.
    """
    out = []
    for m in re.finditer(r"^[ \t]+return\b", code, re.M):
        stack = _block_stack(code, m.start())
        # If ANY enclosing block is a closure, the return belongs to the closure
        # and is correct, however deeply it is nested inside if/else. Checking
        # only the innermost block flagged this, which is right:
        #
        #   EventHandlerCheckpoint.compute(id, (id, current) => {
        #       if (checkpoint.isEmpty()) { return null } else { return checkpoint }
        #   })
        #
        # The trap is a return inside control flow at PROCEDURE level.
        if "closure" in stack:
            continue
        opener = stack[-1] if stack else None
        if opener not in ("if", "else", "for", "while"):
            continue
        out.append(Finding("indented-return", line_of(text, m.start()),
                           "return inside an %s block at procedure level; VAIL falls "
                           "through it. Rewrite as if/else with one trailing "
                           "return." % opener,
                           line_text(text, m.start()), note=1))
    return out


def _block_stack(code, offset):
    """The chain of block openers enclosing `offset`, outermost first.

    Each frame is "if", "else", "for", "while", "closure" or "object". Closures
    are written both `->` and `=>` in this platform's code, and missing the
    second form is what let a correct closure be reported as the fall-through
    trap in three separate projects.
    """
    stack = []
    for i, c in enumerate(code[:offset]):
        if c == "{":
            before = code[max(0, i - 80):i]
            tail = before.rstrip()
            if tail.endswith("->") or tail.endswith("=>") or tail.endswith("("):
                stack.append("closure")
            else:
                kw = re.search(r"\b(if|else|for|while)\s*\(?[^{]*$", before)
                stack.append(kw.group(1) if kw else "object")
        elif c == "}":
            if stack:
                stack.pop()
    return stack


def rule_groovy_it(text, code, ctx):
    """A variable named `it` breaks the whole service, silently.

    A service is assembled into one Groovy class and `it` is Groovy's implicit
    closure parameter. The collision fails the class assembly while every
    procedure in it reports `vailErrors: null` and the push reports success.
    Every read model on that service then 400s at runtime, which is discovered
    in a browser rather than at push time.
    """
    out = []
    for m in re.finditer(r"\b(?:var\s+it\b|for\s*\(\s*it\s+in\b)", code):
        out.append(Finding("groovy-it", line_of(text, m.start()),
                           "a variable named `it` collides with Groovy's implicit "
                           "closure parameter and breaks the whole service; "
                           "vailErrors will not catch it.",
                           line_text(text, m.start()), note=26))
    return out


# A rule that was written and then DELETED, recorded so nobody adds it back.
#
# `WHERE k == k` where `k` is also a parameter looks like it must shadow the
# column. It does not. Tested against the live namespace by asking the cold-chain
# agent about each of five shipments in turn and checking the row it came back
# with: 5 of 5 correct. The pattern appears 59 times in one demo's shipping code.
# A rule flagging all 59 would have been the guard that cries wolf, and the whole
# linter would have been switched off within a week.
#
# If a shadowing failure is ever reproduced, add the rule WITH the reproduction.


# Statement keywords. Using one as a variable name is a parse error at the USE
# site, not the declaration, and the reported position points at the blank line
# before it. Note 2 and 3.
#
# `match` joins them from NR-06, and the failure is not a parse error at all:
# `var match = ""` then `match.length()` bound as a procedure PATH - "The
# procedure '<pkg>.match.length' referenced by the procedure
# '<pkg>.ReportScraper.stripSectionPrefix' could not be found." Renaming to
# `bestKey` compiled. The reporter notes only `match` was tried, so it is
# unknown which other names collide, and it does not occur in the 1,757 .vail
# files this rule was swept against.
RESERVED = ("update", "rule", "delete", "insert", "select", "publish", "match")

# Rejected at the DECLARATION, and only as a parameter name. NR-05:
# `{"code": "io.vantiq.vail.syntax.error", "message": "illegal parameter name
# 'map'"}`, followed by "use of undeclared variable 'map'" at every reference.
# Renaming to `keyMap` compiled.
RESERVED_PARAM = ("map",)

# NOT reserved, on the evidence, and recorded so it does not come back.
#
# PS-05 reports that parameters named `rule` and `state` did not compile while
# `detectionRule` and `sensorState` did, and lists `state` and `filter` as
# reserved alongside the statement keywords. `rule` is already here on its own
# evidence, but `state` and `filter` were added and then removed: a sweep over
# seven demos found `var state = {...}` 68 times and `state` as a PARAMETER
# twice, all of it in shipping code that works, and `filter` never. PS-05's
# evidence is a task report rather than a platform error, and its own author
# scopes several of that file's entries to one namespace.
#
# So `state` is either version- or namespace-specific, or it was something else
# in that procedure. Flagging it would have produced 70 findings on working code
# the first time anyone ran this.


def rule_reserved_var(text, code, ctx):
    """A variable OR PARAMETER named after a statement keyword breaks the parser.

    `var update = {...}` fails on the NEXT reference with "')' encountered when
    parsing VAIL name" pointing at the previous, blank, line. Expensive to find
    because both the message and the position are misleading.

    Parameters are checked too, because that is where the pooled learnings found
    it: `map` as a parameter name is rejected at the declaration (NR-05). The
    platform's own `createProcedure` lint gate does not detect reserved-word
    identifiers, so nothing upstream of this catches it.
    """
    out = []
    for m in re.finditer(r"\bvar\s+(%s)\b" % "|".join(RESERVED), code):
        out.append(Finding("reserved-var", line_of(text, m.start()),
                           "`%s` is a statement keyword; as a variable name it breaks "
                           "the parser at its use site with an error pointing at the "
                           "wrong line." % m.group(1),
                           line_text(text, m.start()), note=2))
    for name, offset in _params(code):
        if name in RESERVED or name in RESERVED_PARAM:
            out.append(Finding("reserved-var", line_of(text, offset),
                               "parameter `%s` is a statement keyword; the platform "
                               "rejects the declaration ("
                               "\"illegal parameter name\") and validateVAIL does "
                               "not catch it." % name,
                               line_text(text, offset), note=2))
    return out


def _param_span(code):
    """(start, end) offsets of the parameter list in the PROCEDURE declaration.

    `start` is the open paren, `end` its match. Returns None when there is no
    declaration, which is the case for rule text and for a bare fragment.
    """
    m = SIG.search(code)
    if not m:
        return None
    i = m.end() - 1
    depth = 0
    while i < len(code):
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth == 0:
                return m.end() - 1, i
        i += 1
    return None


def _params(code):
    """Yield (name, offset) for each declared parameter.

    Offsets are into the blanked view, which is offset-identical to the source,
    so a Finding can still report against the original text.
    """
    span = _param_span(code)
    if not span:
        return
    start, end = span
    pos = start + 1
    for part in code[start + 1:end].split(","):
        pm = re.match(r"(\s*)(\w+)", part)
        if pm:
            yield pm.group(2), pos + len(pm.group(1))
        pos += len(part) + 1


def rule_while_loop(text, code, ctx):
    """VAIL has no `while`. FOR is the only loop.

    The parser reads the `{` as an object literal and reports "'var' encountered
    when expecting the closing '}' for an object definition", which sends you to
    a perfectly good variable declaration somewhere else.
    """
    out = []
    for m in re.finditer(r"\bwhile\s*\(", code):
        out.append(Finding("while-loop", line_of(text, m.start()),
                           "VAIL has no while loop; the parser reads the block as an "
                           "object literal and blames an unrelated line.",
                           line_text(text, m.start()), note=7))
    return out


def rule_sort_closure(text, code, ctx):
    """`sort()` takes a field NAME, not a closure.

    `list.sort(entry -> entry.expiryDate)` fails at parse time with
    "'-' expression must be in the form <exprs> - <exprs>": the arrow is read as
    a minus. The working form is `list.sort("expiryDate")`, ascending only.
    """
    out = []
    for m in re.finditer(r"\.sort\s*\(\s*[^)\"']*->", code):
        out.append(Finding("sort-closure", line_of(text, m.start()),
                           "sort() takes a field name in quotes, not a closure; `->` "
                           "parses as a minus.",
                           line_text(text, m.start()), note=18))
    return out


def rule_map_keys(text, code, ctx):
    """A VAIL map is a Groovy LinkedHashMap: `keySet()`, not `keys()`.

    Compiles clean, pushes clean, throws MissingMethodException at call time. A
    read model that aggregates into a map passes every health check and dies on
    first use.
    """
    out = []
    for m in re.finditer(r"\.keys\s*\(\s*\)", code):
        out.append(Finding("map-keys", line_of(text, m.start()),
                           "a map is a Groovy LinkedHashMap: use keySet(). keys() "
                           "compiles and throws at call time.",
                           line_text(text, m.start()), note=19))
    return out


def rule_date_call(text, code, ctx):
    """`date(...)` compiles, pushes, reports no vailErrors, and returns a String.

    The parser is `toDate(...)`. The wrong one surfaces much later as
    "No signature of method: java.lang.String.toEpochMilli()", thrown from a
    different procedure than the one containing the bug.
    """
    out = []
    # Only the single-argument form. `date(now(), "date", "epochMilliseconds")`
    # is a real three-argument VAIL function, and matching a bare `date(`
    # flagged it twelve times in one unseen codebase, every one of them correct.
    # The mistake is `date("2026-08-12T06:00:00Z")` used where toDate belongs,
    # so the signature is: one argument, and it is a string.
    for m in re.finditer(r"(?<![\w.])date\s*\(\s*\)", code):
        out.append(Finding("date-call", line_of(text, m.start()),
                           "`date()` returns a String; the parser is `toDate()`.",
                           line_text(text, m.start()), note=10))
    for m in re.finditer(r"(?<![\w.])date\s*\(", text):
        # the raw text here, because the argument being a STRING is the signal
        j = m.end()
        depth, arg = 1, []
        while j < len(text) and depth:
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if not depth:
                    break
            arg.append(text[j])
            j += 1
        a = "".join(arg).strip()
        if a.startswith(("\"", "'")) and "," not in a:
            out.append(Finding("date-call", line_of(text, m.start()),
                               "`date(<string>)` returns a String and fails much later "
                               "somewhere else; the parser is `toDate()`.",
                               line_text(text, m.start()), note=10))
    return out


def rule_delete_without_where(text, code, ctx):
    """DELETE without a WHERE clause is a parse error.

    The delete-all idiom is an always-true predicate:
    `DELETE com.x.Thing WHERE ars_createdAt != null`.
    """
    out = []
    for m in re.finditer(r"^\s*DELETE\s+[\w.]+\s*$", code, re.M):
        out.append(Finding("delete-no-where", line_of(text, m.start()),
                           "DELETE requires a WHERE clause; use "
                           "`WHERE ars_createdAt != null` to mean all.",
                           line_text(text, m.start()), note=9))
    return out


def _in_property_position(text, start):
    """True when the token at `start` is a KEY, not a value or a path segment.

    A key is preceded, ignoring whitespace and comments, by `{` or `,`. Two
    things break without this check and both were found in one procedure of an
    unseen codebase:

      dealer == null ? null : dealer.name     the ternary branch reads as a key
      claim.claimId, claim.dealerCode : ...   the path tail reads as a key

    Both produced confident duplicate-key findings on correct code.
    """
    i = start - 1
    while i >= 0:
        c = text[i]
        if c.isspace():
            i -= 1
            continue
        if c == ".":
            return False
        return c in "{,"
    return False


def _scan_keys(text):
    """Yield (path, offset, key) for every object key, quoted or bare.

    This rule cannot use the blanked view: the keys that actually bit us were
    QUOTED ("ITM-02"), and blanking strings erases exactly what it needs to see.
    So it walks the source itself, skipping comments and stepping over string
    CONTENT while still recognising a string that sits in key position.

    `path` is the chain of enclosing brace/bracket offsets, so keys are only
    compared against their siblings. The same key at two nesting depths is
    normal and must not be reported.
    """
    i, n = 0, len(text)
    stack = []
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if c == "/" and nxt == "/":
            i = text.find("\n", i)
            if i == -1:
                break
            continue
        if c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue

        if c in "{[":
            stack.append(i)
            i += 1
            continue
        if c in "}]":
            if stack:
                stack.pop()
            i += 1
            continue

        if c in ('"', "'"):
            quote, j = c, i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    break
                j += 1
            literal = text[i + 1:j]
            k = j + 1
            while k < n and text[k] in " \t":
                k += 1
            if k < n and text[k] == ":" and _in_property_position(text, i):
                yield tuple(stack), i, literal
            i = j + 1
            continue

        m = re.match(r"[A-Za-z_][\w]*", text[i:])
        if m:
            k = i + m.end()
            while k < n and text[k] in " \t":
                k += 1
            # `?:` and `::` are not key syntax; a single colon after an
            # identifier inside an object is.
            if (k < n and text[k] == ":" and text[k:k + 2] != "::" and stack
                    and _in_property_position(text, i)):
                yield tuple(stack), i, m.group(0)
            i += m.end()
            continue

        i += 1


def rule_duplicate_key(text, code, ctx):
    """A repeated key in an object literal: the LAST one silently wins.

    A per-item table was remapped many-to-one and ended up with `ITM-02` written
    three times. VAIL parsed it, kept 698 instead of 61, and the demo opened
    with two years of stock cover on a line that was supposed to be thin. A
    keyed table is the wrong shape for a many-to-one remap, and the failure is
    invisible because it still parses.
    """
    seen, dupes = {}, {}
    for path, offset, key in _scan_keys(text):
        ident = (path, key)
        if ident in seen:
            dupes.setdefault(ident, [seen[ident]]).append(offset)
        else:
            seen[ident] = offset
    out = []
    for (path, key), offsets in sorted(dupes.items(), key=lambda kv: kv[1][0]):
        out.append(Finding("duplicate-key", line_of(text, offsets[0]),
                           "key `%s` appears %d times among the same siblings "
                           "(lines %s); the last value wins and the others are "
                           "lost silently."
                           % (key, len(offsets),
                              ", ".join(str(line_of(text, o)) for o in offsets))))
    return out


def rule_unquoted_key(text, code, ctx):
    """A key containing a hyphen must be quoted, or the procedure stops compiling.

    Object keys are emitted bare and VAIL accepts that only for identifiers.
    Profile ids look like PRF-CLINICAL, and a bare hyphen inside a property list
    is a parse error rather than a warning: the write returns HTTP 200 and the
    procedure simply never compiles again.
    """
    out = []
    for m in re.finditer(r"(?<![\"\w.])([A-Za-z_][\w]*(?:-[\w]+)+)\s*:", code):
        out.append(Finding("unquoted-key", line_of(text, m.start()),
                           "key `%s` contains a hyphen and is not quoted; this is a "
                           "parse error the write will still accept."
                           % m.group(1),
                           line_text(text, m.start())))
    return out


def rule_mojibake(text, code, ctx):
    """UTF-8 bytes read back as CP1252 and stored inside the string literals.

    An em-dash is U+2014, E2 80 94 in UTF-8. Read as CP1252 that is a-circumflex,
    euro sign, right double quote, and in one demo the resulting three-character
    sequence was written INTO the VAIL source. Not a rendering fault a charset
    header can fix: every finding those agents wrote carried it into the database
    and onto the screen.

    Checked on the RAW text, not the blanked view, because it lives in strings.
    """
    out = []
    for m in re.finditer(u"[âÃÂ][-ÿ‘-”€]", text):
        out.append(Finding("mojibake", line_of(text, m.start()),
                           "UTF-8 read as CP1252 and stored in the source; this "
                           "travels into the database and onto the screen.",
                           line_text(text, m.start()), note=None))
    return out


def rule_declared_name(text, code, ctx):
    """The declared name must match the path the file sits at.

    push derives name and serviceName from the filesystem layout, so a
    declaration that disagrees writes one procedure and leaves another stale.

    Rule text has no PROCEDURE declaration and is not a broken procedure, so it
    is skipped rather than reported as one.
    """
    m = SIG.search(code)
    expect = ctx.get("expect")
    if not m:
        if _is_rule(code):
            return []
        return [Finding("no-signature", 1, "no PROCEDURE declaration found")]
    if expect and m.group(1) != expect:
        return [Finding("name-mismatch", line_of(text, m.start()),
                        "declares `%s` but its path says `%s`" % (m.group(1), expect))]
    return []


def rule_package(text, code, ctx):
    """A missing package line writes the procedure outside its namespace.

    Skipped for rule text, where the opposite is true and `rule_topic_package`
    is the check that applies.
    """
    if _is_rule(code):
        return []
    if not re.search(r"^\s*package\s+[\w.]+", code, re.M):
        return [Finding("no-package", 1, "no package declaration")]
    return []


# ---------------------------------------------------------------------------
# Rules below arrived from the pooled professional-services learnings of
# 2026-09. Three developers audited their own Claude Code history independently
# and filed 140 entries between them; these are the ones a static check can
# catch. The id in each docstring (DM-nn, NR-nn, PS-nn) is the entry in
# learnings/, where the full evidence and its provenance live.
#
# Entries corroborated by more than one of the three are the strongest signal in
# the whole corpus, and they are marked as such.
# ---------------------------------------------------------------------------

def _is_rule(code):
    """True when this is RULE text rather than a procedure.

    Rules and procedures are different resources with opposite package rules,
    and before this the linter read a rule as a broken procedure: "no PROCEDURE
    declaration found" plus "no package declaration", neither of which is true.
    """
    if SIG.search(code):
        return False
    return bool(re.search(r"^\s*(?:RULE\s+\w+|WHEN\s+EVENT\s+OCCURS)", code,
                          re.M | re.I))


# A topic path in a WHEN clause, a PUBLISH, or an import. Service events are
# `<pkg>.<Service>/<event>` and are NOT affected by the package-prefix trap, so
# only paths that start with a slash are interesting here.
_TOPIC_LITERAL = re.compile(r"\"(/[\w./-]+)\"")


def rule_topic_package(text, code, ctx):
    """A `package` line in a topic-triggered RULE corrupts the event binding.

    PS-02, cost hours. The rule compiles, never fires, and nothing points at the
    package line: the stored rule carries
    `{"code":"io.vantiq.rulemgr.vail.resource.unrecognized","message":"The
    resource associated with the event binding '/demo/eda/simTick' is not
    recognized."}` and the internal WHEN-path has been rewritten to
    `/demo.eda/demo/eda/simTick` - the package prepended to the topic.

    Service-event-triggered rules are unaffected, so only a slash-leading path
    is flagged. The fix is to create the rule with no package line at all.
    """
    if not _is_rule(code):
        return []
    pkg = re.search(r"^\s*package\s+[\w.]+", code, re.M)
    if not pkg:
        return []
    out = []
    for m in re.finditer(r"WHEN\s+EVENT\s+OCCURS\s+ON\s+(\"[^\"]*\")", text,
                         re.I):
        topic = _TOPIC_LITERAL.search(m.group(1))
        if not topic:
            continue
        out.append(Finding(
            "rule-topic-package", line_of(text, pkg.start()),
            "this rule binds to topic `%s` and declares a package; the package "
            "is prepended to the WHEN path, the binding stops matching, and the "
            "rule silently never fires. Create topic-triggered rules with no "
            "package line." % topic.group(1),
            line_text(text, pkg.start())))
    return out


def rule_unimported_topic(text, code, ctx):
    """An unqualified topic path in packaged VAIL is prefixed with the package.

    NR-18, cost hours. A publisher in `package com.demo.missile` and a rule in
    `package com.demo.missile.SimControl` each had `"/missiledefense/tick"`
    silently prefixed with their own package and landed on two different topics.
    The scheduled publish loop ran without errors and the subscriber never
    fired. Fixed with `import topic "/missiledefense/tick"` in all three files,
    then verified live.

    The same shape as NR-17 below: in packaged VAIL, an unqualified name is
    resolved INTO the package, and the resulting miss is silent.

    UNQUALIFIED is the operative word, and it is what keeps this quiet. A sweep
    over seven demos found 11 topic paths that already carry their own package -
    `PUBLISH event TO TOPIC "/com.meridian.logistics.Agents.FleetAssetMonitoring
    /tasks/..."` from a file in `package com.meridian.logistics...` - in code
    that ships and works. Those are self-qualified and cannot be prefixed into
    the wrong place, so only a path that does NOT begin with the file's own
    top-level package is reported. That left 3 findings, which is the shape
    NR-18 describes.
    """
    pkg = re.search(r"^\s*package\s+([\w.]+)", code, re.M)
    if not pkg:
        return []
    root = pkg.group(1).split(".")[0]
    imported = set(_TOPIC_LITERAL.findall(
        " ".join(re.findall(r"^\s*import\s+topic\s+.*$", text, re.M))))
    # A packaged RULE's WHEN clause belongs to `rule-topic-package`, which
    # reports the same line with the CORRECT fix: delete the package line, do
    # not add an import. Two findings for one defect is the noise this harness
    # is most careful about, so only one of them speaks.
    arms = r"PUBLISH\b[^\n]*?\bTO\s+TOPIC|SUBSCRIBE\s+TO\s+TOPIC"
    if not _is_rule(code):
        arms += r"|WHEN\s+EVENT\s+OCCURS\s+ON"
    out, seen = [], set()
    for m in re.finditer(r"(?:%s)\s+(\"[^\"]*\")" % arms, text, re.I):
        topic = _TOPIC_LITERAL.search(m.group(1))
        if not topic or topic.group(1) in imported:
            continue
        if topic.group(1).lstrip("/").startswith(root + "."):
            continue
        if topic.group(1) in seen:
            continue
        seen.add(topic.group(1))
        out.append(Finding(
            "unimported-topic", line_of(text, m.start()),
            "topic `%s` is referenced from a packaged file with no matching "
            "`import topic`; the package is prepended silently, so publisher "
            "and subscriber can land on different topics with no error."
            % topic.group(1),
            line_text(text, m.start())))
    return out


# System services that must be imported by name in a packaged file. ONE entry,
# because one is all anybody has watched fail (NR-17). The trap is general - any
# unqualified system service name resolves into the file's package - but a list
# of guesses is how a linter earns a reputation for noise. Add a name here WITH
# the error text that earned it.
SYSTEM_SERVICES = ("Notification",)


def rule_unimported_system_service(text, code, ctx):
    """An unqualified system service inside a packaged file resolves into it.

    NR-17, cost hours, and the worst kind of failure this platform has: a rule
    calling `Notification.sendPayloadToAll(...)` never fired, nothing appeared
    in the app OR THE ERROR LOG, and records just stayed in their initial state.
    `Notification` had resolved to `com.vantiq.demo.triage.Notification`:

        The procedure 'com.vantiq.demo.triage.Notification.sendPayloadToAll'
        ... could not be found

    and a rule with a compile error does not run. Fixed with
    `import service Notification` at the top of the file.
    """
    if not re.search(r"^\s*package\s+[\w.]+", code, re.M):
        return []
    out = []
    for svc in SYSTEM_SERVICES:
        if re.search(r"^\s*import\s+service\s+%s\b" % svc, code, re.M):
            continue
        m = re.search(r"(?<![\w.])%s\s*\.\s*\w+\s*\(" % svc, code)
        if not m:
            continue
        out.append(Finding(
            "unimported-system-service", line_of(text, m.start()),
            "`%s` is a system service called from a packaged file with no "
            "`import service %s`; it resolves into this package, the compile "
            "fails, and a rule with a compile error runs silently never."
            % (svc, svc),
            line_text(text, m.start())))
    return out


def rule_bare_array_type(text, code, ctx):
    """A parameter declared as bare `Array` is resolved as a missing custom type.

    NR-07. The compile error names a type that was never written and says
    nothing about arrays:

        "The type '<pkg>.Array' referenced by the procedure
        '<pkg>.ReportScraper.stripSectionPrefix' could not be found. Please
        either define the type or remove the reference."

    `bareKeys Array` -> `bareKeys String Array` compiled.
    """
    span = _param_span(code)
    if not span:
        return []
    start, end = span
    out = []
    pos = start + 1
    for part in code[start + 1:end].split(","):
        words = part.replace("Required", " ").split()
        if len(words) == 2 and words[1] == "Array":
            out.append(Finding(
                "bare-array-type", line_of(text, pos),
                "parameter `%s` is declared as bare `Array`; without an element "
                "type it parses as a reference to a custom type named `Array` "
                "in this package. Write `%s <Element> Array`."
                % (words[0], words[0]),
                line_text(text, pos)))
        pos += len(part) + 1
    return out


def rule_modifier_on_standalone(text, code, ctx):
    """Procedure modifiers are only accepted on SERVICE procedures.

    NR-08. Copying a service procedure out to a standalone scratch procedure to
    probe something takes the modifier with it, and the insert fails:

        {"code":"io.vantiq.rulemgr.vail.illegal.procedure.modifier","message":
         "Illegal use of the procedure modifier(s) 'stateless' for non-service
         procedure '<pkg>.probeDateMath'.  Procedure modifiers may only be
         applied to service procedures."}

    A service procedure is named `Service.operation`; an undotted name is
    standalone.
    """
    m = SIG.search(code)
    if not m:
        return []
    if "." in m.group(1):
        return []
    head = code[m.start():m.start(1)]
    mods = [w for w in re.findall(r"\w+", head) if w.upper() != "PROCEDURE"]
    if not mods:
        return []
    return [Finding(
        "modifier-on-standalone", line_of(text, m.start()),
        "`%s` is a standalone procedure (no `Service.` in its name) and carries "
        "the modifier(s) %s; modifiers are only legal on service procedures."
        % (m.group(1), ", ".join("`%s`" % w for w in mods)),
        line_text(text, m.start()))]


# Methods that BIND and then throw, because a VAIL DateTime is a raw
# java.time.Instant and has only the Instant API. Every name here appears in a
# quoted MissingMethodException; the Instant methods that DO work
# (toEpochMilli, plusSeconds, minusSeconds, plusMillis, minusMillis) are the
# near-miss cases the self-test asserts silence on.
INSTANT_TRAPS = ("getMillis", "toMillis", "toLong",
                 "minusMinutes", "plusMinutes", "minusHours", "plusHours",
                 "minusDays", "plusDays")


def rule_instant_method(text, code, ctx):
    """A VAIL DateTime is a `java.time.Instant`, so most date methods throw.

    NR-09 and PS-04, independently. These compile, push clean, and throw at
    execution:

        groovy.lang.MissingMethodException: No signature of method:
        java.time.Instant.toLong() is applicable for argument types: () values: []

        No signature of method: java.time.Instant.minusMinutes() is applicable
        for argument types: (Long) values: [10]
        Possible solutions: minusMillis(long), minusNanos(long)

    PS-04 adds `.toMillis()` from a second namespace: "binds but throws at
    runtime". Use `now().toEpochMilli()` and do millisecond arithmetic yourself,
    or `minusSeconds`/`plusSeconds`, which are real Instant methods.
    """
    out = []
    for m in re.finditer(r"\.(%s)\s*\(" % "|".join(INSTANT_TRAPS), code):
        out.append(Finding(
            "instant-method", line_of(text, m.start()),
            "`.%s()` does not exist on java.time.Instant, which is what a VAIL "
            "DateTime is; it compiles and throws MissingMethodException at "
            "execution. Use toEpochMilli() and millisecond arithmetic."
            % m.group(1),
            line_text(text, m.start()), note=None))
    for m in re.finditer(r"\btoInteger\s*\(\s*now\s*\(\s*\)", code):
        out.append(Finding(
            "instant-method", line_of(text, m.start()),
            "`toInteger(now())` throws: now() is a java.time.Instant. Use "
            "`now().toEpochMilli()`.",
            line_text(text, m.start())))
    return out


# Functions that do not exist, and whose absence is invisible because an
# unqualified call is silently package-qualified: `dateDiff(...)` becomes
# `<pkg>.dateDiff(...)`, a procedure nobody wrote, and the failure is
# `io.vantiq.rulemgr.vail.referenced.resource.not.found` at store time. The
# platform's own createProcedure lint gate does no identifier resolution, so it
# passes every one of these.
MISSING_BUILTINS = {
    # PS-04: 121 occurrences of the not-found error across one team's
    # transcripts. Do date arithmetic on the Instant instead.
    "dateDiff": "no such builtin; subtract toEpochMilli() values",
    "dateAdd": "no such builtin; use plusSeconds()/minusSeconds()",
    # DM-05: probed deliberately. `Encode.base64` is the primitive that exists;
    # these four spellings all fail to compile.
    "toBase64": "the base64 builtin is `Encode.base64(...)`",
    "encodeBase64": "the base64 builtin is `Encode.base64(...)`",
}


def rule_missing_builtin(text, code, ctx):
    """A call to a builtin that does not exist is silently package-qualified.

    PS-04 and DM-05. `dateDiff(...)` resolves to `<pkg>.dateDiff(...)` - a
    procedure in the current package that nobody wrote - and fails at store or
    compile time with `io.vantiq.rulemgr.vail.referenced.resource.not.found`,
    naming a procedure path rather than saying the function is missing. The
    platform's createProcedure lint gate does not resolve identifiers and passes
    it. Dotted spellings (`Base64.encode`, `Utils.base64Encode`) fail the same
    way and are caught by the dotted arm below.
    """
    out = []
    for name, advice in sorted(MISSING_BUILTINS.items()):
        for m in re.finditer(r"(?<![\w.])%s\s*\(" % name, code):
            out.append(Finding(
                "missing-builtin", line_of(text, m.start()),
                "`%s()` is not a VAIL builtin; unqualified, it resolves to a "
                "procedure in this package that does not exist. %s."
                % (name, advice),
                line_text(text, m.start())))
    for m in re.finditer(r"(?<![\w.])(?:Base64\s*\.\s*encode|"
                         r"Utils\s*\.\s*base64Encode)\s*\(", code):
        out.append(Finding(
            "missing-builtin", line_of(text, m.start()),
            "the base64 builtin is `Encode.base64(...)`; this spelling fails to "
            "compile (DM-05 probed four of them).",
            line_text(text, m.start())))
    return out


# The SECOND rule written and then deleted, recorded so nobody adds it back.
#
# DM-03 states that "VAIL's lambda operator is `=>`, not `->`" and that `->`
# "never compiles on any version". A rule flagging every `->` was written, and
# the self-test caught it firing on this, which is correct code from a real
# Vantiq project already in the suite as an asserted-silent case:
#
#     var ids = things.map(t -> {
#         var id = t.id
#         return id
#     })
#
# Going back to the evidence, DM-03 does not hold up. The failing line was
# `Bogus.updateAndGet(prev -> cnt)` - and `updateAndGet` does not exist on that
# instance AT ALL, which is DM-10, from the same session an hour earlier. The
# conclusion that the arrow was at fault came from reading the operators
# reference afterwards, not from probing `->` against `=>` in isolation. A docs
# read is not a failure anybody watched.
#
# `sort-closure` is not affected and stays: its parse error is first-hand, and
# `sort()` takes a field NAME, so a closure of either arrow style is wrong there
# whatever the lambda operator is.
#
# If `->` is ever watched failing on its own - same code, both arrows, one
# compiles and one does not - add the rule WITH that reproduction.


def rule_exception_placeholder(text, code, ctx):
    """`exception()` messages are Java MessageFormat: `{0}`, never `{}`.

    DM-04. The refusal path fires correctly and the caller gets "can't parse
    argument number" INSTEAD OF the real message, so the bug reads as a broken
    gate rather than a broken format string. Changing
    `'this operation ({}).'` to `'this operation ({0}).'` produced a readable
    refusal on re-test.

    `log.error("... {}", [...])` is the opposite convention and is correct; only
    `exception()` is flagged.
    """
    out = []
    for m in re.finditer(r"(?<![\w.])exception\s*\(", code):
        # Depth is counted on the BLANKED view so a paren inside the message
        # string cannot end the argument list early; the `{}` is then looked for
        # in the raw text, because that is where the string content still is.
        j, depth = m.end(), 1
        while j < len(code) and depth:
            if code[j] == "(":
                depth += 1
            elif code[j] == ")":
                depth -= 1
            j += 1
        if "{}" in text[m.end():j]:
            out.append(Finding(
                "exception-placeholder", line_of(text, m.start()),
                "`exception()` uses Java MessageFormat placeholders; a bare `{}` "
                "raises \"can't parse argument number\" and REPLACES the message "
                "you wrote. Use `{0}`, `{1}`.",
                line_text(text, m.start())))
    return out


# The THIRD rule written and then deleted, recorded so nobody adds it back.
#
# DM-10 reports `stateVar.updateAndGet((prev) => {...})` failing with the method
# not found, and concludes that the `Concurrent.*` atomics in the Vantiq MCP
# server's own service-state docs "do not exist there" - the MCP server being
# pre-release and documenting a newer runtime than the instance being edited.
# A rule flagging `.updateAndGet(` was written, and the sweep found 11 uses in
# the Retail demo's shipping code:
#
#     defaultStoreId.updateAndGet((v) => { return storeDefault })
#
# So the atomics DO exist, on some versions. DM-10 says as much in its own fix
# line - "unless the instance's version is confirmed to support the Concurrent.*
# atomics" - and a static check cannot know the version it is linting for.
#
# This is a CONVENTION, not a rule: on an instance that rejects it, service
# state variables are plain typed properties set by direct assignment
# (`Bogus = rows[0].count`), and the trade-off is real - plain scalar state is
# not replicated and resets on failover, which is DM-11's silent scheduled-
# procedure death. Confirm the instance before depending on either.


def rule_where_method_call(text, code, ctx):
    """A method call inside a WHERE clause binds as a procedure reference.

    NR-12, cost hours. Identifiers in a WHERE qualification are resolved against
    the queried type and the procedure namespace - never as method calls - so
    `WHERE memberName.contains("x")` fails to compile with:

        {"code":"io.vantiq.rulemgr.vail.referenced.resource.not.found",
         "message":"The procedure '<pkg>.memberName.contains' referenced by the
         procedure '<pkg>.searchMembers' could not be found."

    Reproduced on both a plaintext and an encrypted field, to rule out
    encryption as the cause. Filter in code after the query, or use the raw
    document form: `WITH where = {prop: {"$regex": needle, "$options": "i"}}`
    (NR-11), which is the only substring search VAIL has.

    Scoped to the remainder of the LINE, deliberately: a WHERE spread over
    several lines will be under-reported rather than over-reported.

    The keyword must not be preceded by a dot. `\bWHERE\b` alone matched the
    property path `pre.where.storeId` in the Retail demo and reported a correct
    ternary as a bad query - one finding, on the first sweep, on code nobody
    here wrote.
    """
    out = []
    for m in re.finditer(r"(?<![\w.])WHERE\b", code, re.I):
        end = code.find("\n", m.end())
        clause = code[m.end():end if end != -1 else len(code)]
        call = re.search(r"\b\w+\s*\.\s*\w+\s*\(", clause)
        if not call:
            continue
        out.append(Finding(
            "where-method-call", line_of(text, m.start()),
            "`%s` is a method call inside a WHERE clause; identifiers there "
            "resolve against the queried type and the procedure namespace, so "
            "this binds as a missing procedure path. Filter after the query, or "
            "use `WITH where = {...}` with $regex."
            % call.group(0).strip().rstrip("("),
            line_text(text, m.start())))
    return out


def rule_dollar_operator_collapse(text, code, ctx):
    """Two `$` operator keys in one object literal collapse to the last key.

    NR-22, cost hours. A date-range filter written the obvious way:

        {bookdate: {"$gte": start, "$lte": end}}

    silently applied ONE bound - object-literal construction kept only the last
    operator key. It parses, it runs, and it returns the wrong rows. The comment
    left beside the fix: "Two "$" operator keys in one VAIL object literal
    silently collapse to the last key (the $gte bound was being dropped), so the
    range must be expressed as an $and of single-operator objects."

        {"$and": [{bookdate: {"$gte": start}}, {bookdate: {"$lte": end}}]}

    Reuses the sibling-aware key scanner, so `$and` and `$or` at DIFFERENT
    nesting depths - the correct form above - stay quiet.
    """
    siblings = {}
    for path, offset, key in _scan_keys(text):
        if key.startswith("$"):
            siblings.setdefault(path, []).append((offset, key))
    out = []
    for path, found in sorted(siblings.items(), key=lambda kv: kv[1][0][0]):
        if len(found) < 2:
            continue
        out.append(Finding(
            "dollar-operator-collapse", line_of(text, found[0][0]),
            "%s are operator keys on the same object (lines %s); VAIL keeps "
            "only the last and drops the others silently. Express it as an "
            "`$and` of single-operator objects."
            % (", ".join("`%s`" % k for _o, k in found),
               ", ".join(str(line_of(text, o)) for o, _k in found)),
            line_text(text, found[0][0])))
    return out


def rule_dynamic_source(text, code, ctx):
    """The source name in `SELECT ... FROM SOURCE` is a compile-time literal.

    DM-01, settled by a deliberate probe rather than guessed. A procedure
    `zzTmpDynamicSourceProbe(srcName String)` doing `SELECT ONE FROM SOURCE s`
    where `s` held the parameter value: "Confirmed: the source name in
    `SELECT ... FROM SOURCE` is a compile-time literal - VAIL resolved the
    variable `s` as a source *named* `s`."

    There is no dynamic source selection in VAIL at all, so an environment
    cannot be chosen at runtime. One procedure per source binding, with
    everything else shared in a common procedure the entry points call.
    """
    span = _param_span(code)
    locals_ = set(n for n, _o in _params(code))
    locals_.update(re.findall(r"\bvar\s+(\w+)", code))
    if not locals_:
        return []
    out = []
    for m in re.finditer(r"\bFROM\s+SOURCE\s+(\w+)", code, re.I):
        if span and span[0] <= m.start() <= span[1]:
            continue
        if m.group(1) not in locals_:
            continue
        out.append(Finding(
            "dynamic-source", line_of(text, m.start()),
            "`FROM SOURCE %s` names a source literally called `%s`; the binding "
            "is resolved at compile time and the variable's value is never "
            "read. One procedure per source binding."
            % (m.group(1), m.group(1)),
            line_text(text, m.start())))
    return out


RULES = [rule_package, rule_declared_name,
         rule_indented_return, rule_groovy_it, rule_duplicate_key,
         rule_unquoted_key, rule_reserved_var, rule_while_loop,
         rule_sort_closure, rule_map_keys, rule_date_call,
         rule_delete_without_where, rule_mojibake,
         # pooled professional-services learnings, 2026-09
         rule_topic_package, rule_unimported_topic,
         rule_unimported_system_service, rule_bare_array_type,
         rule_modifier_on_standalone, rule_instant_method,
         rule_missing_builtin,
         rule_exception_placeholder,
         rule_where_method_call, rule_dollar_operator_collapse,
         rule_dynamic_source]


# ------------------------------------------------------------ cross-file ----

# Service procedures known to be invoked asynchronously even though they read
# like builtins. `Hash.md5` is the one with a quoted failure (NR-03); any
# procedure the tree or namespace actually defines is added at scan time, which
# is where this check gets its precision. Do not populate this from the docs.
ASYNC_SERVICES = ("Hash",)


def cross_file(files):
    """Checks that need the whole tree rather than one file.

    Two of them, and both are real errors the platform reports late:

      * `io.vantiq.rulemgr.vail.procedure.not.visible`. A PRIVATE procedure
        cannot be called from outside its own service. That surfaced when
        ApiGateway tried to read the profile catalogue directly; caught at push,
        but cheaper here.
      * a method chained onto a procedure invocation, which needs to know which
        names ARE procedures - see `_chained_calls`.
    """
    private, known = {}, set()
    for path, text in files.items():
        svc = os.path.basename(os.path.dirname(path))
        code = blank(text)
        for m in PRIVATE_SIG.finditer(code):
            private.setdefault(svc, set()).add(m.group(1).split(".")[-1])
        for m in SIG.finditer(code):
            known.add(m.group(1).split(".")[-1])

    out = []
    for path, text in files.items():
        svc = os.path.basename(os.path.dirname(path))
        code = blank(text)
        for m in re.finditer(r"\b([A-Z]\w+)\.(\w+)\s*\(", code):
            other, proc = m.group(1), m.group(2)
            if other == svc:
                continue
            if proc in private.get(other, set()):
                out.append((path, Finding(
                    "private-cross-service", line_of(text, m.start()),
                    "`%s.%s` is PRIVATE to %s and cannot be called from %s."
                    % (other, proc, other, svc), line_text(text, m.start()))))
        for finding in _chained_calls(text, code, known):
            out.append((path, finding))
    return out


def _chained_calls(text, code, known):
    """A method chained onto a procedure invocation is a compile error.

    NR-03. A procedure invocation is treated as async and cannot have further
    expressions applied in the same statement:

        {"code":"io.vantiq.rulemgr.vail.method.chain.async.statement",
         "message":"Chained expressions cannot be applied to a VAIL procedure
         invocation."}

    flagged at the column of the FIRST chained call, which is not where the
    procedure invocation is. `Hash.md5(report.filename).encodeHex().toString()`
    became two statements:

        var failedHash = Hash.md5(report.filename)
        var failedId = failedHash.encodeHex().toString()

    and compiled clean. Seen twice, in two sessions.

    This only fires on a name the scan KNOWS is a procedure - one defined in the
    tree or the namespace, or an evidenced entry in ASYNC_SERVICES. Chaining
    onto a genuine builtin is fine, and a rule that could not tell the two apart
    would report most of the codebase.
    """
    out = []
    for m in re.finditer(r"\b([A-Z]\w+)\s*\.\s*(\w+)\s*\(", code):
        if m.group(1) not in ASYNC_SERVICES and m.group(2) not in known:
            continue
        j, depth = m.end(), 1
        while j < len(code) and depth:
            if code[j] == "(":
                depth += 1
            elif code[j] == ")":
                depth -= 1
            j += 1
        k = j
        while k < len(code) and code[k] in " \t":
            k += 1
        if k >= len(code) or code[k] != ".":
            continue
        out.append(Finding(
            "chained-procedure-call", line_of(text, m.start()),
            "`%s.%s(...)` is a procedure invocation and cannot have a method "
            "chained onto it in the same statement; the compiler reports the "
            "column of the chained call, not of the invocation. Assign it to a "
            "variable first." % (m.group(1), m.group(2)),
            line_text(text, m.start())))
    return out


# ----------------------------------------------------------------- driver ---

def check_text(text, expect=None):
    code = blank(text)
    m = SIG.search(code)
    params = []
    if m:
        # Parameter names, for the shadowing rule. Everything between the open
        # paren and its match, first identifier of each comma-separated part.
        depth, i = 0, m.end() - 1
        start = i
        while i < len(code):
            if code[i] == "(":
                depth += 1
            elif code[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        for part in code[start + 1:i].split(","):
            pm = re.match(r"\s*(\w+)", part)
            if pm:
                params.append(pm.group(1))
    ctx = {"expect": expect, "params": params}
    out = []
    for rule in RULES:
        out.extend(rule(text, code, ctx))
    return out


def check_namespace(client, package):
    """Lint what is DEPLOYED, with no local source tree.

    This is the common case, not the exception. Of the Vantiq projects on this
    machine, one keeps VAIL in src/procedures/ and at least three others (527,
    657 and 501 procedures) are built directly in the namespace through the MCP
    server and have no .vail files at all. A harness that can only read a source
    tree is a harness for one project.

    Returns {fqn: [Finding]}. The name and package checks are skipped: there is
    no path to disagree with, and the package is implied by serviceName.
    """
    skip = {"no-package", "name-mismatch"}
    results = {}
    sources = client.procedures(package)
    for fqn, script in sources.items():
        if not script:
            continue
        found = [f for f in check_text(script) if f.rule not in skip]
        if found:
            results[fqn] = found
    # cross-file wants paths shaped like .../<Service>/<name>.vail so it can
    # read the service from the directory; synthesise that shape from the FQN.
    # Keyed by FQN. Keying by <Service>/<name> collapsed five services that each
    # own an ActiveCollabsGetAll into one, and printed the same finding five
    # times with no way to tell which service it belonged to.
    as_paths = {}
    for fqn, script in sources.items():
        parts = fqn.split(".")
        as_paths[os.path.join(".".join(parts[:-1]), parts[-1])] = script
    for path, finding in cross_file(as_paths):
        results.setdefault(path.replace(os.sep, "."), []).append(finding)
    return results


def check_tree(root):
    """Every .vail under root. Returns {path: [Finding]}."""
    files, results = {}, {}
    for dirpath, _dirs, names in os.walk(root):
        for fn in sorted(names):
            if not fn.endswith(".vail"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            files[path] = text
            svc = os.path.basename(dirpath)
            short = fn[:-5]
            expect = short if svc == "_package" else "%s.%s" % (svc, short)
            found = check_text(text, expect)
            if found:
                results[path] = found
    for path, finding in cross_file(files):
        results.setdefault(path, []).append(finding)
    return results
