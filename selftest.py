"""Prove every rule catches its trap, and does not fire on the innocent case.

A linter whose rules are untested is worse than no linter: it reports confidently
and gets trusted. Each case below is the real code that cost us something, paired
with the near-miss that must stay quiet.

Run: python selftest.py
"""
import io
import os
import sys

from lint import check_text, cross_file
from source import blank

HEAD = "package com.atlas.health\n\nSTATELESS PROCEDURE Svc.thing(): Object\n\n"


def case(name, body, rule, should_fire, expect="Svc.thing", head=HEAD,
         also=()):
    """One rule against one snippet, plus every OTHER rule against it.

    `also` is the set of rule ids that are allowed to fire alongside the
    subject. Anything else firing is a failure, and that is not pedantry: for a
    long time this suite collected the collateral findings and threw them away,
    so a new rule could report on all forty snippets and the run still printed
    "0 failure(s)". The first new rule added after that changed was a general
    `->` rule; it fired on the asserted-silent closure case, and going back to
    its evidence showed the entry behind it was wrong. See the recorded deletion
    in lint.py. That is the whole value of this suite and it needs the collateral
    check to work.
    """
    found = check_text(head + body, expect)
    fired = [f for f in found if f.rule == rule]
    other = sorted(set(f.rule for f in found if f.rule != rule))
    unexpected = [r for r in other if r not in also]
    ok = bool(fired) == should_fire and not unexpected
    return ok, name, rule, fired, unexpected


CASES = []

# --- indented return: the guard clause that returns success ------------------
CASES.append(("guard clause that falls through", """
if (args.profileId == null) {
    return {ok: false}
}
return {ok: true}
""", "indented-return", True))

CASES.append(("if/else with one trailing return", """
var out = {ok: true}
if (args.profileId == null) {
    out = {ok: false}
}
return out
""", "indented-return", False))

# --- Groovy `it` -------------------------------------------------------------
CASES.append(("loop variable named it", """
var rows = []
for (it in things) {
    rows = rows + [it]
}
return rows
""", "groovy-it", True))

CASES.append(("loop variable named item", """
var rows = []
for (item in things) {
    rows = rows + [item]
}
return rows
""", "groovy-it", False))

# --- the rule we deliberately do NOT have ------------------------------------
# `WHERE k == k` with a parameter named k was tested against the live namespace
# and filters correctly, 5 of 5. It appears 59 times in shipping code. Anything
# that flags it is crying wolf, so this case asserts silence.
SHADOW_HEAD = ("package com.atlas.health\n\n"
               "STATELESS PROCEDURE Svc.thing(itemId String): Object\n\n")
CASES.append(("WHERE itemId == itemId is NOT flagged (tested: it filters)", """
var rows = SELECT * FROM com.atlas.health.Item WHERE itemId == itemId
return rows
""", "param-shadow", False, "Svc.thing", SHADOW_HEAD))

# --- reserved words ----------------------------------------------------------
CASES.append(("variable named update", """
var update = {snapshotId: "S1"}
UPDATE com.atlas.health.Snapshot(update) WHERE snapshotId == "S1"
return update
""", "reserved-var", True))

CASES.append(("variable named patch", """
var patch = {snapshotId: "S1"}
UPDATE com.atlas.health.Snapshot(patch) WHERE snapshotId == "S1"
return patch
""", "reserved-var", False))

# --- no while loop -----------------------------------------------------------
CASES.append(("a while loop", """
var i = 0
while (i < 10) {
    i = i + 1
}
return i
""", "while-loop", True))

CASES.append(("a FOR loop", """
var n = 0
for (x in things) {
    n = n + 1
}
return n
""", "while-loop", False))

# --- sort takes a field name -------------------------------------------------
CASES.append(("sort with a closure", """
var s = lots.sort(entry -> entry.expiryDate)
return s
""", "sort-closure", True))

CASES.append(("sort with a field name", """
var s = lots.sort("expiryDate")
return s
""", "sort-closure", False))

# --- map is a LinkedHashMap --------------------------------------------------
CASES.append(("map.keys()", """
var ks = byLocation.keys()
return ks
""", "map-keys", True))

CASES.append(("map.keySet()", """
var ks = byLocation.keySet()
return ks
""", "map-keys", False))

# --- date() versus toDate() --------------------------------------------------
CASES.append(("date() instead of toDate()", """
var d = date("2026-08-12T06:00:00Z")
return d
""", "date-call", True))

CASES.append(("toDate()", """
var d = toDate("2026-08-12T06:00:00Z")
return d
""", "date-call", False))

# --- DELETE needs a WHERE ----------------------------------------------------
CASES.append(("DELETE with no WHERE", """
DELETE com.atlas.health.Item
return {}
""", "delete-no-where", True))

CASES.append(("DELETE with the always-true predicate", """
DELETE com.atlas.health.Item WHERE ars_createdAt != null
return {}
""", "delete-no-where", False))

# --- duplicate keys ----------------------------------------------------------
CASES.append(("cover table with a key written three times", """
var coverByItem = {
    "ITM-02": 61.0,
    "ITM-01": 520.0,
    "ITM-02": 505.0,
    "ITM-02": 698.0
}
return coverByItem
""", "duplicate-key", True))

CASES.append(("same key at different nesting depths", """
var cfg = {
    name: "outer",
    inner: {name: "inner"},
    other: {name: "another"}
}
return cfg
""", "duplicate-key", False))

# --- unquoted hyphenated key -------------------------------------------------
CASES.append(("profile id used as a bare key", """
var byProfile = {
    PRF-CLINICAL: {items: []},
    PRF-FOODBEV: {items: []}
}
return byProfile
""", "unquoted-key", True))

CASES.append(("the same keys, quoted", """
var byProfile = {
    "PRF-CLINICAL": {items: []},
    "PRF-FOODBEV": {items: []}
}
return byProfile
""", "unquoted-key", False))

# --- name and package --------------------------------------------------------
CASES.append(("declares a different name than its path", """
return {}
""", "name-mismatch", True, "Svc.other"))

CASES.append(("declares the name its path implies", """
return {}
""", "name-mismatch", False, "Svc.thing"))

CASES.append(("no package line", """
return {}
""", "no-package", True, "Svc.thing",
              "STATELESS PROCEDURE Svc.thing(): Object\n\n"))


# --- mojibake ----------------------------------------------------------------
CASES.append(("em-dash stored double-decoded", u"""
var note = "cold chain â€” excursion recorded"
return note
""", "mojibake", True))

CASES.append(("a clean string", """
var note = "cold chain excursion recorded"
return note
""", "mojibake", False))


# --- the false positives found by running against unseen codebases -----------
# Every case below is correct code from a real Vantiq project that an earlier
# version of these rules flagged. Together they were 138 findings across three
# namespaces, all wrong. They are asserted silent so they cannot come back.

CASES.append(("return inside a closure is correct, not the trap", """
var ids = things.map(t -> {
    var id = t.id
    return id
})
return ids
""", "indented-return", False))

CASES.append(("date() with three arguments is a real VAIL function", """
var elapsed = (date(now(), "date", "epochMilliseconds") - started)
return elapsed
""", "date-call", False))

CASES.append(("a ternary branch is not an object key", """
var row = {
    dealerName: dealer == null ? null : dealer.name,
    region: dealer == null ? null : dealer.region,
    score: dealer == null ? null : dealer.score
}
return row
""", "duplicate-key", False))

CASES.append(("a dotted path before a colon is not a key", """
var out = {
    claimId: claim.claimId, dealerCode: claim.dealerCode,
    dealerName: dealer == null ? claim.dealerCode : dealer.name
}
return out
""", "duplicate-key", False))

CASES.append(("a genuine duplicate key is still caught", """
var m = {
    "ITM-02": 61.0,
    "ITM-02": 698.0
}
return m
""", "duplicate-key", True))


CASES.append(("if/else inside a => closure is correct", """
var result = Checkpoint.compute(rootEventId, (id, current) => {
    var checkpoint = {}
    if (checkpoint.isEmpty()) {
        return null
    } else {
        return checkpoint
    }
})
return result
""", "indented-return", False))


# Declaration forms seen in the wild. The modifier list is OPEN, and every form
# below was reported as "no PROCEDURE declaration found" by an earlier pattern
# that enumerated modifiers: 26 findings across three projects, all of them the
# pattern's ignorance rather than a defect.
DECL_FORMS = [
    ("uppercase modifiers", """package p

PRIVATE STATELESS PROCEDURE Svc.thing(): Object

"""),
    ("lowercase modifiers", """package p

stateless private PROCEDURE Svc.thing(event) HIDDEN

"""),
    ("multi partition", """package p

PRIVATE MULTI PARTITION PROCEDURE Svc.thing()

"""),
    ("no modifiers", """package p

PROCEDURE Svc.thing(): Object

"""),
]
for _label, _head in DECL_FORMS:
    CASES.append(("declaration parsed: " + _label, """
return {}
""", "no-signature", False, "Svc.thing", _head))

# ---------------------------------------------------------------------------
# Pooled professional-services learnings, 2026-09. Each pair is the failure one
# of the three audits recorded, and the near-miss it must not be confused with.
# The near-miss is the important half: most of these traps are one character
# away from the correct form.
# ---------------------------------------------------------------------------

RULE_HEAD = ""          # rules carry no package line and no PROCEDURE
PKG_RULE_HEAD = "package demo.eda\n\n"

# --- PS-02: a package line in a topic-triggered rule kills the binding --------
CASES.append(("topic rule with a package line", """
RULE SimulatorService_onTick
WHEN EVENT OCCURS ON "/demo/eda/simTick" AS event
var x = event.value
""", "rule-topic-package", True, None, PKG_RULE_HEAD))

CASES.append(("topic rule with no package line", """
RULE SimulatorService_onTick
WHEN EVENT OCCURS ON "/demo/eda/simTick" AS event
var x = event.value
""", "rule-topic-package", False, None, RULE_HEAD))

CASES.append(("packaged rule on a SERVICE event is unaffected", """
RULE IngestService_onRaw
WHEN EVENT OCCURS ON "demo.eda.IngestService/rawReading" AS event
var x = event.value
""", "rule-topic-package", False, None, PKG_RULE_HEAD))

# --- NR-18: an unqualified topic is prefixed with the file's package ---------
CASES.append(("publish to a topic with no import", """
PUBLISH {tick: 1} TO TOPIC "/missiledefense/tick"
return true
""", "unimported-topic", True))

IMPORTED_HEAD = ("package com.atlas.health\n\n"
                 'import topic "/missiledefense/tick"\n\n'
                 "STATELESS PROCEDURE Svc.thing(): Object\n\n")
CASES.append(("publish to a topic that is imported", """
PUBLISH {tick: 1} TO TOPIC "/missiledefense/tick"
return true
""", "unimported-topic", False, "Svc.thing", IMPORTED_HEAD))

# 11 of these in the Logistics demo, shipping and working: the path already
# carries the package, so it cannot be prefixed into the wrong place.
CASES.append(("a topic path that already carries its own package", """
PUBLISH event TO TOPIC "/com.atlas.health.Agents.FleetMonitoring/tasks/x"
return true
""", "unimported-topic", False))

# --- NR-17: an unqualified system service resolves into the package ----------
CASES.append(("Notification called from a packaged file", """
Notification.sendPayloadToAll("app", {msg: "hi"})
return true
""", "unimported-system-service", True))

IMPORT_SVC_HEAD = ("package com.atlas.health\n\n"
                   "import service Notification\n\n"
                   "STATELESS PROCEDURE Svc.thing(): Object\n\n")
CASES.append(("Notification with import service", """
Notification.sendPayloadToAll("app", {msg: "hi"})
return true
""", "unimported-system-service", False, "Svc.thing", IMPORT_SVC_HEAD))

# --- NR-07: a bare Array parameter is a missing custom type ------------------
BARE_ARRAY = ("package com.atlas.health\n\n"
              "STATELESS PROCEDURE Svc.thing(bareKeys Array): Object\n\n")
CASES.append(("parameter declared as bare Array", """
return bareKeys
""", "bare-array-type", True, "Svc.thing", BARE_ARRAY))

TYPED_ARRAY = ("package com.atlas.health\n\n"
               "STATELESS PROCEDURE Svc.thing(bareKeys String Array): Object\n\n")
CASES.append(("parameter with an element type", """
return bareKeys
""", "bare-array-type", False, "Svc.thing", TYPED_ARRAY))

# --- NR-08: modifiers are only legal on service procedures -------------------
STANDALONE_MOD = "package com.atlas.health\n\nSTATELESS PROCEDURE probeDateMath(): Object\n\n"
CASES.append(("stateless on a standalone procedure", """
return 1
""", "modifier-on-standalone", True, "probeDateMath", STANDALONE_MOD))

STANDALONE_PLAIN = "package com.atlas.health\n\nPROCEDURE probeDateMath(): Object\n\n"
CASES.append(("standalone procedure with no modifier", """
return 1
""", "modifier-on-standalone", False, "probeDateMath", STANDALONE_PLAIN))

CASES.append(("stateless on a SERVICE procedure is correct", """
return 1
""", "modifier-on-standalone", False))

# --- NR-09 / PS-04: a DateTime is a java.time.Instant ------------------------
CASES.append(("minusMinutes on a DateTime", """
var cutoff = now().minusMinutes(10)
return cutoff
""", "instant-method", True))

CASES.append(("minusSeconds and toEpochMilli are real Instant methods", """
var cutoff = now().minusSeconds(600)
var ms = now().toEpochMilli()
return {cutoff: cutoff, ms: ms}
""", "instant-method", False))

CASES.append(("toInteger(now())", """
var ms = toInteger(now())
return ms
""", "instant-method", True))

# --- PS-04 / DM-05: builtins that do not exist -------------------------------
CASES.append(("dateDiff, which resolves into the package", """
var gap = dateDiff(a, b)
return gap
""", "missing-builtin", True))

CASES.append(("millisecond arithmetic instead of dateDiff", """
var gap = (toDate(a).toEpochMilli() - toDate(b).toEpochMilli())
return gap
""", "missing-builtin", False))

CASES.append(("Base64.encode, one of the four wrong spellings", """
var h = Base64.encode(raw)
return h
""", "missing-builtin", True))

CASES.append(("Encode.base64, the one that exists", """
var h = Encode.base64(raw)
return h
""", "missing-builtin", False))

# --- DM-04: exception() is Java MessageFormat --------------------------------
CASES.append(("exception with a bare {} placeholder", """
exception("io.atlas.refused", "cannot do this operation ({}).", [name])
return false
""", "exception-placeholder", True))

CASES.append(("exception with a positional {0}", """
exception("io.atlas.refused", "cannot do this operation ({0}).", [name])
return false
""", "exception-placeholder", False))

CASES.append(("log.error legitimately uses {}", """
log.error("could not reach {}", [host])
return false
""", "exception-placeholder", False))

# --- DM-10: the third rule deliberately NOT written --------------------------
# DM-10 says `updateAndGet` does not exist. The sweep found 11 uses of it in the
# Retail demo's shipping code, so it exists on some versions and DM-10's own fix
# line concedes the version dependence. A static check cannot know the version.
CASES.append(("updateAndGet is NOT flagged (DM-10 is version-specific)", """
Bogus.updateAndGet((prev) => { return cnt })
return true
""", "concurrent-api", False))

# --- NR-12: a method call in WHERE binds as a procedure path -----------------
CASES.append(("contains() inside a WHERE clause", """
var rows = SELECT * FROM com.atlas.health.Item WHERE memberName.contains("x")
return rows
""", "where-method-call", True))

CASES.append(("equality in WHERE, filtering afterwards", """
var rows = SELECT * FROM com.atlas.health.Item WHERE memberName == needle
return rows
""", "where-method-call", False))

CASES.append(("the raw document form with $regex is the substring search", """
var rows = SELECT * FROM com.atlas.health.Item WITH where = {memberName: {"$regex": needle}}
return rows
""", "where-method-call", False))

# `WHERE` matched this property path in the Retail demo and reported a
# correct ternary as a bad query.
CASES.append(("a property named `where` is not the WHERE keyword", """
var whereStore = pre.where.storeId != null ? SimulationEngine.evalTemplate(pre.where.storeId) : null
return whereStore
""", "where-method-call", False))

# --- NR-22: two $ operator keys on one object collapse -----------------------
CASES.append(("a $gte and $lte range on one object", """
var q = {bookdate: {"$gte": start, "$lte": end}}
return q
""", "dollar-operator-collapse", True))

CASES.append(("the same range as an $and of single-operator objects", """
var q = {"$and": [{bookdate: {"$gte": start}}, {bookdate: {"$lte": end}}]}
return q
""", "dollar-operator-collapse", False))

# --- DM-01: FROM SOURCE is a compile-time literal ----------------------------
SRC_HEAD = ("package com.atlas.health\n\n"
            "STATELESS PROCEDURE Svc.thing(srcName String): Object\n\n")
CASES.append(("FROM SOURCE naming a parameter", """
var row = SELECT ONE FROM SOURCE srcName
return row
""", "dynamic-source", True, "Svc.thing", SRC_HEAD))

CASES.append(("FROM SOURCE naming a real source", """
var row = SELECT ONE FROM SOURCE AtlasRemote
return row
""", "dynamic-source", False, "Svc.thing", SRC_HEAD))

# --- NR-05 / PS-05: reserved words as PARAMETER names ------------------------
MAP_PARAM = ("package com.atlas.health\n\n"
             "STATELESS PROCEDURE Svc.thing(map Object): Object\n\n")
CASES.append(("a parameter named map", """
return 1
""", "reserved-var", True, "Svc.thing", MAP_PARAM))

KEYMAP_PARAM = ("package com.atlas.health\n\n"
                "STATELESS PROCEDURE Svc.thing(keyMap Object): Object\n\n")
CASES.append(("a parameter named keyMap", """
return 1
""", "reserved-var", False, "Svc.thing", KEYMAP_PARAM))

# PS-05 said `state` was reserved. A sweep over seven demos found `var state`
# 68 times and `state` as a PARAMETER twice, all of it in shipping code that
# works, so the entry did not survive. Both forms are asserted silent.
STATE_PARAM = ("package com.atlas.health\n\n"
               "STATELESS PROCEDURE Svc.thing(state Object): Object\n\n")
CASES.append(("a parameter named state is NOT flagged (PS-05 disproved)", """
return 1
""", "reserved-var", False, "Svc.thing", STATE_PARAM))

CASES.append(("`var state` is NOT flagged (68 uses in shipping code)", """
var state = {patient: pt}
return state
""", "reserved-var", False))

# --- the second rule deliberately NOT written --------------------------------
# DM-03 says `->` never compiles. A rule flagging it fired on the asserted-
# silent closure case above, which is real shipping code, and the entry did not
# survive going back to its evidence. This asserts the silence directly so the
# rule cannot be reintroduced without this case going red.
CASES.append(("`->` is NOT flagged (DM-03 did not survive its evidence)", """
var ids = things.map(t -> {
    var id = t.id
    return id
})
return ids
""", "arrow-lambda", False))


# ---------------------------------------------------------------------------
# NC, added 2026-09. A fourth audit, weighted toward what the platform's own
# bundled documentation shows that the real compiler then rejects. Every claim
# below was checked against the 1,757-file corpus before it became a rule:
# `END` 0 occurrences, `PUBLIC` 0, `INSERT {` 0, colon-less return types 0.
# ---------------------------------------------------------------------------

# --- NC-01: the colon, and the END ------------------------------------------
NO_COLON = ("package com.atlas.health\n\n"
            "STATELESS PROCEDURE Svc.thing(id String) Object\n\n")
CASES.append(("return type with no colon", """
return {}
""", "missing-return-colon", True, "Svc.thing", NO_COLON))

CASES.append(("return type with a colon", """
return {}
""", "missing-return-colon", False))

# `HIDDEN` is a declaration modifier, not a return type. 12 in the corpus.
HIDDEN_DECL = ("package com.atlas.health\n\n"
               "PROCEDURE Svc.thing(id String) HIDDEN WITH ars_dependentResource=true\n\n")
CASES.append(("HIDDEN after the params is not a return type", """
return {}
""", "missing-return-colon", False, "Svc.thing", HIDDEN_DECL))

CASES.append(("a trailing END terminator", """
var found = 1
return found
END
""", "end-terminator", True))

CASES.append(("no END terminator", """
var found = 1
return found
""", "end-terminator", False))

# --- NC-02: PUBLIC is not a modifier, PRIVATE is ----------------------------
PUBLIC_DECL = ("package com.atlas.health\n\n"
               "PUBLIC PROCEDURE Svc.thing(): String\n\n")
CASES.append(("PUBLIC as a visibility modifier", """
return "pong"
""", "public-modifier", True, "Svc.thing", PUBLIC_DECL))

# NC-02 guesses PRIVATE fails too. It does not: 820 uses in the demo corpus,
# and private-cross-service exists because the platform enforces it.
PRIVATE_DECL = ("package com.atlas.health\n\n"
                "PRIVATE STATELESS PROCEDURE Svc.thing(): String\n\n")
CASES.append(("PRIVATE is NOT flagged (820 uses in shipping code)", """
return "pong"
""", "public-modifier", False, "Svc.thing", PRIVATE_DECL))

# --- NC-04: Array and void in the return position ---------------------------
RET_ARRAY = ("package com.atlas.health\n\n"
             "STATELESS PROCEDURE Svc.thing(): Array\n\n")
CASES.append(("Array as a return type", """
return []
""", "bare-array-type", True, "Svc.thing", RET_ARRAY))

RET_OBJECT = ("package com.atlas.health\n\n"
              "STATELESS PROCEDURE Svc.thing(): Object\n\n")
CASES.append(("Object as a return type is fine", """
return []
""", "bare-array-type", False, "Svc.thing", RET_OBJECT))

# --- NC-07: the INSERT object literal ---------------------------------------
CASES.append(("INSERT with an object literal", """
INSERT {sensorId: targetSensorId, status: "open"} INTO com.atlas.health.Alert
return true
""", "insert-object-literal", True))

CASES.append(("INSERT in the call form", """
INSERT com.atlas.health.Alert(sensorId: targetSensorId, status: "open")
return true
""", "insert-object-literal", False))

# --- NC-05: the WHEN payload is not implicitly `event` ----------------------
CASES.append(("a WHEN with no alias whose body reads event.", """
RULE IngestTemperatureReading
WHEN MESSAGE ARRIVES FROM TemperatureSensorSource

var payload = event.message
""", "when-alias", True, None, RULE_HEAD))

CASES.append(("the same WHEN with AS event", """
RULE IngestTemperatureReading
WHEN MESSAGE ARRIVES FROM TemperatureSensorSource AS event

var payload = event.message
""", "when-alias", False, None, RULE_HEAD))

CASES.append(("a rule that never dereferences the payload", """
RULE Heartbeat
WHEN MESSAGE ARRIVES FROM TemperatureSensorSource

var n = 1
""", "when-alias", False, None, RULE_HEAD))


def blanking_cases():
    """The two incidents that motivated source.blank, as direct assertions."""
    out = []

    # An odd number of quotes inside a comment must not desynchronise the
    # matcher for the code that follows it.
    src = ('// the "vital" class matters, and one stray " here\n'
           'var x = {clinicalUse: "a note"}\n')
    b = blank(src)
    out.append(("comment with an odd quote does not swallow following code",
                "clinicalUse" in b and "vital" not in b and "a note" not in b))

    # A rule must never match inside a string literal.
    src2 = 'var a = "for (it in things)"\nvar b = 1\n'
    fired = [f for f in check_text(HEAD + src2, "Svc.thing") if f.rule == "groovy-it"]
    out.append(("a rule does not fire on its own example inside a string", not fired))

    # Length and line numbers must survive blanking.
    src3 = 'var a = 1  // c\nvar b = "x\\ny"\nvar c = 3\n'
    out.append(("blank preserves length", len(blank(src3)) == len(src3)))
    out.append(("blank preserves line count",
                blank(src3).count("\n") == src3.count("\n")))
    return out


def cross_file_case():
    files = {
        "src/procedures/Simulation/profileCatalog.vail":
            "package com.atlas.health\n\n"
            "PRIVATE STATELESS PROCEDURE Simulation.profileCatalog(): Object\n\nreturn {}\n",
        "src/procedures/ApiGateway/submitCommand.vail":
            "package com.atlas.health\n\n"
            "STATELESS PROCEDURE ApiGateway.submitCommand(): Object\n\n"
            "var cat = Simulation.profileCatalog()\nreturn cat\n",
        "src/procedures/Simulation/seedNetwork.vail":
            "package com.atlas.health\n\n"
            "STATELESS PROCEDURE Simulation.seedNetwork(): Object\n\n"
            "var cat = Simulation.profileCatalog()\nreturn cat\n",
    }
    found = cross_file(files)
    priv = [(p, f) for p, f in found if f.rule == "private-cross-service"]
    caller_flagged = any("submitCommand" in p for p, _f in priv)
    sibling_quiet = not any("seedNetwork" in p for p, _f in priv)
    out = [("private procedure called from another service is flagged", caller_flagged),
           ("the owning service calling its own private is not flagged", sibling_quiet)]

    # NR-03. Chaining onto a PROCEDURE invocation is a compile error; chaining
    # onto a builtin is not. The whole precision of this check is knowing which
    # names are procedures, which is why it lives here and not in check_text.
    chain = {
        "src/procedures/Reports/stripPrefix.vail":
            "package com.atlas.health\n\n"
            "STATELESS PROCEDURE Reports.stripPrefix(s String): String\n\nreturn s\n",
        "src/procedures/Reports/ingest.vail":
            "package com.atlas.health\n\n"
            "STATELESS PROCEDURE Reports.ingest(): Object\n\n"
            "var failedId = Hash.md5(report.filename).encodeHex().toString()\n"
            "return failedId\n",
        "src/procedures/Reports/split.vail":
            "package com.atlas.health\n\n"
            "STATELESS PROCEDURE Reports.split(): Object\n\n"
            "var failedHash = Hash.md5(report.filename)\n"
            "var failedId = failedHash.encodeHex().toString()\n"
            "return failedId\n",
        "src/procedures/Reports/plain.vail":
            "package com.atlas.health\n\n"
            "STATELESS PROCEDURE Reports.plain(): Object\n\n"
            "var t = Math.abs(delta).toString()\nreturn t\n",
    }
    hits = [p for p, f in cross_file(chain) if f.rule == "chained-procedure-call"]
    out.append(("a method chained onto a procedure invocation is flagged",
                any("ingest" in p for p in hits)))
    out.append(("the same call split across two statements is not",
                not any("split" in p for p in hits)))
    out.append(("chaining onto a builtin that is not a known procedure is not",
                not any("plain" in p for p in hits)))
    return out


def client_cases():
    """The REST traps, which are knowledge rather than parsing.

    None of these needs a server. Each is a shape the platform answers
    plausibly and wrongly, so the assertion is that the harness refuses the
    call rather than that it handles the reply.
    """
    from client import _path_trap, strip_server_fields, is_not_found, _modal
    out = []

    # NR-30: the server adds the `system.` prefix itself.
    out.append(("a `system.` resource prefix is refused",
                bool(_path_trap("system.genaiflows", "GET"))))
    out.append(("the unprefixed path is allowed",
                not _path_trap("genaiflows", "GET")))

    # DM-16: instances live at custom/<T>. But the DEFINITION is read at
    # types/<T>, and trapping that broke reading a schema.
    out.append(("writing an instance to types/<T> is refused",
                bool(_path_trap("types/Ticket", "POST"))))
    out.append(("reading a type definition at types/<T> is allowed",
                not _path_trap("types/Ticket", "GET")))
    out.append(("custom/<T> is allowed",
                not _path_trap("custom/Ticket", "POST")))

    # NR-35: the documented content sub-resource 400s on 1.44.1.
    out.append(("documents/<name>/content is refused",
                bool(_path_trap("documents/x.md/content", "GET"))))

    # NR-36: the GET-edit-PUT round trip does not work on the record you got.
    stripped = strip_server_fields(
        {"_id": "a", "ars_version": 2, "vailErrors": None,
         "currentState": {}, "name": "n", "script": "s"})
    out.append(("_id and the ars_/compiler fields are stripped before PUT",
                stripped == {"name": "n", "script": "s"}))

    # NR-33: not-found is 400 with a code.
    out.append(("a 400 carrying io.vantiq.resource.not.found reads as not-found",
                is_not_found(400, [{"code": "io.vantiq.resource.not.found",
                                    "message": "m"}])))
    out.append(("an ordinary 200 row does not",
                not is_not_found(200, [{"name": "x"}])))

    # NR-48: the listing carries inherited records.
    out.append(("the owning namespace is the modal one",
                _modal(["ours", "ours", "inherited", None]) == "ours"))

    # NC-11: system.projects has no description, and the failure cascades.
    from client import body_trap
    out.append(("a project created with a description is refused",
                bool(body_trap("projects", {"name": "P", "description": "x"}))))
    out.append(("a project with no description is allowed",
                not body_trap("projects", {"name": "P"})))

    # NC-06: a VEH package must be compound. The opposite of NC-03's advice for
    # PROCEDURE headers, which is why both are spelled out.
    out.append(("a VEH on a simple package name is refused",
                bool(body_trap("collaborationtypes",
                               {"name": "TemperatureMonitor",
                                "isEventHandler": True}))))
    out.append(("a VEH on a compound package name is allowed",
                not body_trap("collaborationtypes",
                              {"name": "com.example.TemperatureMonitor",
                               "isEventHandler": True})))
    return out


def ops_cases():
    """PS-14, PS-15, PS-16 and NR-38, all on scheduledevents."""
    from opscheck import scheduled_faults, service_schedule_faults
    out = []

    ok = {"name": "tick", "interval": 5000, "topic": "/demo/eda/simTick"}
    out.append(("a well-formed scheduled event has no faults",
                not scheduled_faults(ok)))

    out.append(("an interval below the 1000ms floor is caught",
                any("floor" in f for f in scheduled_faults(
                    dict(ok, interval=500)))))
    out.append(("no topic and no resource is caught",
                any("no topic" in f for f in scheduled_faults(
                    {"name": "t", "interval": 5000}))))
    out.append(("a /services/ target is caught",
                any("service-event path" in f for f in scheduled_faults(
                    dict(ok, topic="/services/demo.eda.SimulatorService/tickRequest")))))

    # PS-15: the 60,000ms grid, and only for SERVICE scheduled procedures.
    out.append(("15,000ms on a service scheduled procedure is caught",
                bool(service_schedule_faults([{"name": "w", "interval": 15000}]))))
    out.append(("120,000ms is an even multiple and passes",
                not service_schedule_faults([{"name": "w", "interval": 120000}])))
    return out


def ui_cases():
    """NR-20 and PS-22: the same defect found by two teams two months apart."""
    from uilint import check_page
    out = []
    subscribing = ('const ws = new WebSocket(u);\n'
                   'ws.send(JSON.stringify({op: "subscribe", '
                   'resourceId: "/topics/triage/escalations"}))')
    fired = [f.rule for f in check_page(subscribing)]
    out.append(("a WebSocket subscription to a topic is flagged",
                "topic-subscription" in fired))

    crud = ('const ws = new WebSocket(u);\n'
            'ws.send(JSON.stringify({op: "subscribe", '
            'resourceId: "/types/com.x.Ticket/insert"}))')
    out.append(("subscribing to type CRUD instead is not flagged",
                "topic-subscription" not in [f.rule for f in check_page(crud)]))

    # A topic path that is not a subscription must stay quiet.
    mention = 'const HELP = "/topics/help-index"'
    out.append(("a topic path that is not a subscription is not flagged",
                "topic-subscription" not in [f.rule for f in check_page(mention)]))
    return out


def tree_cases():
    """check_tree against the layouts that actually exist on disk.

    These are not hypothetical. Run over seven demos, check_tree reported 520
    findings and 474 of them - 91% - were its own assumptions: 407 name
    mismatches because only one directory layout was supported, and 67 missing
    package declarations because the rule matched `package` case-sensitively
    while the platform's exporter writes `PACKAGE`. After these, 32.
    """
    import shutil
    import tempfile
    from lint import check_tree
    root = tempfile.mkdtemp()
    try:
        def w(rel, body):
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            io.open(p, "w", encoding="utf-8").write(body)
            return p

        # Layout A, hand-maintained: <Service>/<operation>.vail
        w("src/procedures/BedCapacityAgent/placePatient.vail",
          "package com.atlas.health\n\n"
          "stateless PROCEDURE BedCapacityAgent.placePatient(): Object\n\nreturn {}\n")
        # Layout B, the Vantiq exporter: <pkg dirs>/<Service>_<operation>.vail
        w("export/procedures/com/atlas/health/BedCapacityAgent_findBed.vail",
          "PACKAGE com.atlas.health\n\n"
          "stateless PROCEDURE BedCapacityAgent.findBed(): Object\n\nreturn {}\n")
        # Layout B with an underscore in the OPERATION as well.
        w("export/procedures/com/atlas/health/IsrAgent_a2a_dispatchPlan.vail",
          "PACKAGE com.atlas.health\n\n"
          "PRIVATE STATELESS PROCEDURE IsrAgent.a2a_dispatchPlan(): Object\n\nreturn {}\n")
        # Genuinely wrong: declares something neither reading allows.
        w("src/procedures/BedCapacityAgent/relieveCapacity.vail",
          "package com.atlas.health\n\n"
          "stateless PROCEDURE SomethingElse.notThis(): Object\n\nreturn {}\n")
        # Platform-generated: nobody can edit it, so it is not linted.
        w("export/procedures/com/atlas/health/Agent_a2a_bridge.vail",
          "PACKAGE com.atlas.health\n\n"
          "/**\n * GENERATED -- DO NOT EDIT\n */\n"
          "PRIVATE STATELESS PROCEDURE WrongName.whatever(): Object\n\nreturn {}\n")

        res = check_tree(root)
        rules = dict((os.path.basename(p), [f.rule for f in fs])
                     for p, fs in res.items())
        out = [
            ("layout A: <Service>/<operation>.vail is accepted",
             "placePatient.vail" not in rules),
            ("layout B: the Vantiq export layout is accepted",
             "BedCapacityAgent_findBed.vail" not in rules),
            ("layout B: an underscore in the operation still resolves",
             "IsrAgent_a2a_dispatchPlan.vail" not in rules),
            ("uppercase PACKAGE counts as a package declaration",
             not any("no-package" in v for v in rules.values())),
            ("a name matching NEITHER layout is still flagged",
             "name-mismatch" in rules.get("relieveCapacity.vail", [])),
            ("a GENERATED -- DO NOT EDIT file is not linted at all",
             "Agent_a2a_bridge.vail" not in rules),
        ]
        return out
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    failures = 0
    print("rule cases")
    for c in CASES:
        ok, name, rule, fired, unexpected = case(*c)
        mark = "ok  " if ok else "FAIL"
        if not ok:
            failures += 1
        note = ""
        if not ok:
            note = "  (fired: %s" % ([f.rule for f in fired] or "nothing")
            if unexpected:
                note += ", collateral: %s" % unexpected
            note += ")"
        print("  %s %-52s %s%s" % (mark, name[:52], rule, note))

    print("\nblanking")
    for name, ok in blanking_cases():
        if not ok:
            failures += 1
        print("  %s %s" % ("ok  " if ok else "FAIL", name))

    print("\ncross-file")
    for name, ok in cross_file_case():
        if not ok:
            failures += 1
        print("  %s %s" % ("ok  " if ok else "FAIL", name))

    for label, fn in (("tree layouts", tree_cases),
                      ("REST traps", client_cases),
                      ("scheduled events", ops_cases),
                      ("console", ui_cases)):
        print("\n%s" % label)
        for name, ok in fn():
            if not ok:
                failures += 1
            print("  %s %s" % ("ok  " if ok else "FAIL", name))

    print("\n%d failure(s)" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
