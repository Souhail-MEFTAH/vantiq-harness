"""Static checks on a Vantiq-hosted console.

These consoles ship as ONE self-contained HTML document, because the document
store serves each file from its own URL and a page that references ./app.js finds
nothing. That constraint makes them large, hand-edited and easy to break in ways
nobody notices until a customer is watching.

Every rule below is a defect that shipped in one of the seven demos. The
expensive ones all share a shape: the console renders something plausible while
being wrong, so the failure reads as "the demo has no data" or "the click did
nothing" rather than as an error.
"""
import re

from source import line_of, line_text
from lint import Finding

TOKEN_SHAPE = re.compile(r"(?<![A-Za-z0-9_\-])[A-Za-z0-9_\-]{43}=(?![A-Za-z0-9_\-=])")


def rule_hardcoded_endpoint(text):
    """A console pointed at the namespace it was imported FROM.

    Defense 13.3: the UI document carried a config block naming an absolute host
    and a token, and it survived the namespace import. Every query went to the
    old server with the old token and returned 401. The screens rendered their
    empty states, so it presented as "the demo has no data" while the namespace
    was in fact full.

    A hosted console should derive its origin, or be given one at publish time.
    """
    out = []
    for m in re.finditer(r"[\"'](https?://[\w.-]*vantiq[\w.-]*)[\"'/]", text):
        line = line_text(text, m.start())
        # A DEFAULT the operator can change is not the trap. Every console here
        # puts the server in an editable field on its connect form, and flagging
        # that is the guard crying wolf on five of five consoles. What bit us was
        # an assignment: a config object or a variable that the page then uses
        # with no way to override it, which survives an import and silently
        # points the console at the namespace it came from.
        is_form_default = re.search(r"<input\b[^>]*\bvalue\s*=", line)
        is_assignment = re.search(r"(?:=|:)\s*[\"']https?://", line)
        if is_form_default and not re.search(r"token", line, re.I):
            continue
        if not is_assignment:
            continue
        out.append(Finding("hardcoded-endpoint", line_of(text, m.start()),
                           "absolute Vantiq host `%s` assigned in the page; it will "
                           "survive an import and point the console at the namespace "
                           "it came from." % m.group(1), line))
    return out


def rule_source_carries_token(text):
    """A token-shaped string in the SOURCE page.

    Baking a credential at publish time is a deliberate, documented choice. A
    credential in the working tree is not: it reaches version control, exports
    and anyone with the repo.
    """
    return [Finding("source-token", line_of(text, m.start()),
                    "token-shaped string in the page source; bake credentials at "
                    "publish time, never in the tree.", "")
            for m in TOKEN_SHAPE.finditer(text)]


def rule_swallowed_refusal(text):
    """A fetch whose non-ok response is never surfaced.

    Defense 13.9: access control refused every approve, deny and delegate click.
    The request stayed pending, the refusal counter incremented, and the operator
    saw a success toast and no change. The control was working exactly as
    designed and the console said the opposite.

    Heuristic and deliberately loose: it looks for a fetch/await whose result is
    used without any reference to `.ok`, `status`, `error` or a catch nearby.
    """
    out = []
    for m in re.finditer(r"\bawait\s+fetch\s*\(", text):
        window = text[m.start():m.start() + 700]
        if not re.search(r"\.ok\b|\.status\b|\bcatch\b|\berror\b|throw\b", window):
            out.append(Finding("swallowed-refusal", line_of(text, m.start()),
                               "a fetch whose failure is never inspected; a server "
                               "refusal will render as success.",
                               line_text(text, m.start())))
    return out


def rule_grid_min_width(text):
    """A grid whose implicit column sizes to its widest min-content.

    Defense 13.19: `#app` was a grid with no declared column, and every child
    carried the default `min-width: auto`. The header's 1796px min-content set
    the column, the body stretched to match, and `overflow-x: hidden` on body cut
    up to 40% of the console away with no scrollbar to recover it.

    The fix is `minmax(0, 1fr)` on the column, or `min-width: 0` on the children.
    """
    out = []
    has_grid = re.search(r"display\s*:\s*grid", text)
    if not has_grid:
        return out
    guarded = re.search(r"minmax\(\s*0", text) or re.search(r"min-width\s*:\s*0", text)
    hides = re.search(r"overflow-x\s*:\s*hidden", text)
    if not guarded:
        m = has_grid
        out.append(Finding("grid-min-width", line_of(text, m.start()),
                           "a grid with no minmax(0,...) and no min-width:0 on its "
                           "children sizes to the widest min-content" +
                           (" and overflow-x:hidden will cut the excess with no "
                            "scrollbar." if hides else "."),
                           line_text(text, m.start())))
    return out


def rule_topic_subscription(text):
    """A browser subscribed to a TOPIC does not receive what VAIL publishes to it.

    Two teams, two namespaces, two months apart, neither aware of the other. It
    is the most corroborated entry in the pooled learnings and it is the most
    expensive one to find, because every part of it works: the rule fires, its
    other effects happen, the subscribe frame is acknowledged, and no error is
    raised anywhere.

    NR-20 probed it at the socket: the subscribe frame came back acknowledged
    with `"topic":"/topics/triage/escalations"`, the `INSERT status: 200`, then
    "timeout, closing" with no event frame - while the record it should have
    announced was confirmed `status: 'escalated'`. A direct
    `POST /resources/topics/...` over REST delivered a frame immediately, so the
    socket and the subscription were both fine.

    PS-22 reached the same place from the UI side and wrote the fix into the
    code: "Subscribed to type CRUD rather than `PUBLISH TO TOPIC` because topic
    publishes don't reach WebSocket subscribers on the Vantiq platform (verified
    empirically); `system.collaborations` insert/update events deliver in real
    time (~1s) and carry the full instance as `event.value`."

    So: make a database write the delivery mechanism. Subscribe to
    `/types/<fq>/insert` or `/types/<fq>/update` and have the VAIL INSERT or
    UPSERT the row that carries the state change.

    Note the second half of that, from PS-19: a type's `rulesSuppressed`
    defaults ON, and with it on the writes raise no CRUD events at all, so the
    replacement path is silent in exactly the same way. That one was designed
    around rather than observed, so it is not checked here - but set
    `rulesSuppressed: false` explicitly on any type a subscriber depends on.
    """
    out = []
    for m in re.finditer(r"[\"'](/topics/[\w./-]+)[\"']", text):
        window = text[max(0, m.start() - 200):m.start()]
        if not re.search(r"subscribe|websocket|\bws\b", window, re.I):
            continue
        out.append(Finding("topic-subscription", line_of(text, m.start()),
                           "a WebSocket subscription to `%s`: VAIL "
                           "`PUBLISH ... TO TOPIC` is not delivered to socket "
                           "subscribers. Subscribe to /types/<fq>/insert|update "
                           "and write the row instead." % m.group(1),
                           line_text(text, m.start())))
    return out


def rule_external_reference(text):
    """A relative asset reference in a document-store page.

    Each document is served from its own URL, so ./styles.css resolves to
    nothing and the page renders as a column of unstyled headings. The one
    exception is a console deliberately published as a directory of documents,
    which is why this reports rather than refuses.
    """
    out = []
    for m in re.finditer(r'(?:src|href)="(?!https?:|data:|#|mailto:)([^"]+)"', text):
        out.append(Finding("external-reference", line_of(text, m.start()),
                           "relative reference `%s`; a document store serves each "
                           "file from its own URL." % m.group(1),
                           line_text(text, m.start())))
    return out


def rule_mojibake(text):
    """UTF-8 read back as CP1252, reaching the screen.

    A platform-and-encoding fact, not a preference: the mangled bytes are
    stored and rendered. Same rule as the VAIL side in lint.py.
    """
    out = []
    for m in re.finditer(u"[âÃÂ][-ÿ‘-”€]", text):
        out.append(Finding("mojibake", line_of(text, m.start()),
                           "UTF-8 read as CP1252; this reaches the screen.",
                           line_text(text, m.start())))
    return out




def rule_em_dash(text):
    """HOUSE STYLE, not a platform behaviour.

    One team here forbids em-dashes in customer-facing text. That is a writing
    convention and nothing on the platform cares, so it is OFF by default and
    must be asked for. Shipping a style rule as though it were a correctness
    rule is how a shared tool earns a reputation for noise.
    """
    out = []
    for m in re.finditer(u"—|&mdash;", text):
        out.append(Finding("em-dash", line_of(text, m.start()),
                           "em-dash in a customer-facing page (house style).", ""))
    return out


# Correctness rules, on by default. Every one is a defect that shipped.
RULES = [rule_hardcoded_endpoint, rule_source_carries_token, rule_swallowed_refusal,
         rule_topic_subscription,
         rule_grid_min_width, rule_external_reference, rule_mojibake]

# Opt-in. Conventions, not defects.
HOUSE_RULES = [rule_em_dash]


def check_page(text, house_style=False):
    out = []
    for rule in RULES + (HOUSE_RULES if house_style else []):
        out.extend(rule(text))
    return out


def check_file(path, house_style=False):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return check_page(fh.read(), house_style)
