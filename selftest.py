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
    # PUT updates the definition and DELETE removes the type; both are right.
    # An earlier version trapped every write verb here.
    out.append(("updating or deleting a type DEFINITION at types/<T> is allowed",
                not _path_trap("types/Ticket", "PUT")
                and not _path_trap("types/Ticket", "DELETE")))
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

    # NC-06 is deliberately NOT a guard: the entry records the error but not
    # the create body, so which field holds the package would be a guess, and a
    # guessed field in raw() refuses valid writes. This asserts the silence.
    out.append(("a VEH body is not second-guessed (NC-06 recorded no body)",
                not body_trap("collaborationtypes",
                              {"name": "onReading", "isEventHandler": True,
                               "boundService": "com.example.TemperatureMonitor"})))
    return out


def ops_cases():
    """PS-14, PS-15, PS-16 and NR-38, all on scheduledevents."""
    from opscheck import scheduled_faults, service_schedule_faults, dead_schedules
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

    # PS-16, and a bug in the check itself. A rule's body is WRITTEN under
    # `ruleText` and STORED as `source` (NR-38); asking for one field only came
    # back empty and would have reported every scheduled event as dead.
    class _Rules(object):
        def __init__(self, rows):
            self.rows = rows

        def select(self, resource, **kw):
            return self.rows

    events = [{"name": "tick", "topic": "/demo/eda/simTick"},
              {"name": "orphan", "topic": "/demo/eda/nobody"}]
    stored = _Rules([{"name": "onTick",
                      "source": 'RULE onTick\nWHEN EVENT OCCURS ON '
                                '"/topics/demo/eda/simTick" AS event\n'}])
    dead, err = dead_schedules(stored, events)
    out.append(("a rule body stored as `source` counts as a subscriber",
                not err and ("tick", "/demo/eda/simTick") not in dead))
    out.append(("a scheduled event nothing subscribes to is reported",
                ("orphan", "/demo/eda/nobody") in dead))
    dead2, err2 = dead_schedules(_Rules([{"name": "onTick"}]), events)
    out.append(("rules with no readable body are refused, not read as all-dead",
                bool(err2) and not dead2))
    return out


def ui_cases():
    """NR-20 and PS-22: the same defect, found separately by two contributors."""
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


def connection_cases():
    """The VIA connection is found where Claude Code finds it, and nowhere else.

    Every case builds a throwaway home directory and project, so nothing here
    reads the real ~/.claude.json or the real environment.
    """
    import json as _json
    import shutil
    import tempfile
    from client import VantiqError, describe_connection, find_connection
    root = tempfile.mkdtemp()
    via = "https://%s/mcp/io.vantiq.via.mcpServer"

    def entry(host, token="fake-token"):
        e = {"type": "http", "url": via % host}
        if token is not None:
            e["headers"] = {"Authorization": "Bearer " + token}
        return e

    def setup(user=None, local=None, project=None, local_key=None):
        case = tempfile.mkdtemp(dir=root)
        home, proj = os.path.join(case, "home"), os.path.join(case, "proj")
        os.makedirs(home)
        os.makedirs(proj)
        cfg = {}
        if user is not None:
            cfg["mcpServers"] = user
        if local is not None:
            cfg["projects"] = {(local_key or (lambda d: d))(proj): {"mcpServers": local}}
        if cfg:
            io.open(os.path.join(home, ".claude.json"), "w",
                    encoding="utf-8").write(_json.dumps(cfg))
        if project is not None:
            io.open(os.path.join(proj, ".mcp.json"), "w",
                    encoding="utf-8").write(_json.dumps({"mcpServers": project}))
        return proj, home

    def find(proj, home, env=None):
        return find_connection(proj, home=home, env=env or {})

    def error(proj, home, env=None):
        try:
            find(proj, home, env)
        except VantiqError as exc:
            return str(exc)
        return None

    out = []
    try:
        p, h = setup(project={"vantiq": entry("dev.vantiq.com")})
        c = find(p, h)
        out.append(("a project .mcp.json connection is found",
                    c["scope"] == "project" and c["server"] == "https://dev.vantiq.com"))

        # The case that stopped every command: VIA at user scope, no .mcp.json.
        p, h = setup(user={"vantiqVia": entry("test.vantiq.com")})
        c = find(p, h)
        out.append(("a user-scope VIA connection is found with no .mcp.json",
                    c["scope"] == "user" and c["host"] == "test.vantiq.com"))

        # Local scope is keyed by path; written here with the other separator
        # and a trailing one, which must still match.
        p, h = setup(local={"vantiq": entry("local.vantiq.com")},
                     project={"vantiq": entry("dev.vantiq.com")},
                     user={"vantiqVia": entry("test.vantiq.com")},
                     local_key=lambda d: d.replace("\\", "/") + "/")
        c = find(p, h)
        out.append(("precedence is local, then project, then user",
                    c["scope"] == "local" and [o["scope"] for o in c["others"]]
                    == ["project", "user"]))

        p, h = setup(project={"vantiq": entry("dev.vantiq.com")},
                     user={"vantiqVia": entry("test.vantiq.com")})
        text = describe_connection(find(p, h))
        out.append(("a second connection to a different host is called out",
                    "note:" in text and "test.vantiq.com" in text))
        p, h = setup(project={"vantiq": entry("test.vantiq.com")},
                     user={"vantiqVia": entry("test.vantiq.com")})
        out.append(("a second connection to the same host is not",
                    "note:" not in describe_connection(find(p, h))))

        # The Vantiq plugin's own servers, and unrelated ones, are not VIA.
        p, h = setup(project={"vantiq-help": {"type": "stdio", "command": "npx"},
                              "vantiq-docs": {"type": "http",
                                              "url": "https://docs.vantiq.com/mcp"},
                              "github": {"type": "http",
                                         "url": "https://api.githubcopilot.com/mcp/",
                                         "headers": {"Authorization": "Bearer x"}}},
                     user={"vantiqVia": entry("test.vantiq.com")})
        out.append(("plugin, docs and unrelated servers do not stand in front of VIA",
                    find(p, h)["scope"] == "user"))

        p, h = setup(project={"vantiq": {
            "type": "http",
            "url": "https://${VANTIQ_HOST:-dev.vantiq.com}/mcp/io.vantiq.via.mcpServer",
            "headers": {"Authorization": "Bearer ${VANTIQ_TOKEN}"}}})
        c = find(p, h, env={"VANTIQ_TOKEN": "from-env"})
        out.append(("${VAR} and ${VAR:-default} expand as Claude Code expands them",
                    c["token"] == "from-env" and c["host"] == "dev.vantiq.com"))
        e = error(p, h, env={})
        out.append(("an unset ${VAR} is refused, never sent as a literal token",
                    bool(e) and "VANTIQ_TOKEN" in e))

        p, h = setup(project={"vantiq": entry("dev.vantiq.com", token=None)})
        e = error(p, h)
        out.append(("a VIA connection with no token is refused with the reason",
                    bool(e) and "Authorization" in e))

        p, h = setup()
        e = error(p, h)
        out.append(("with no connection anywhere, every place looked is named",
                    bool(e) and ".mcp.json" in e and ".claude.json" in e))

        p, h = setup(project={"vantiq": {
            "type": "http", "url": "not-a-url-io.vantiq.via.mcpServer",
            "headers": {"Authorization": "Bearer fake-secret-value"}}})
        e = error(p, h)
        out.append(("an error about a connection never contains its token",
                    bool(e) and "fake-secret-value" not in e))
        p, h = setup(project={"vantiq": entry("dev.vantiq.com", token="fake-secret-value")})
        out.append(("describe_connection never contains the token",
                    "fake-secret-value" not in describe_connection(find(p, h))))
        return out
    finally:
        shutil.rmtree(root, ignore_errors=True)


def hook_cases():
    """The Claude Code hooks, against a fake VIA and a disposable settings folder.

    Nothing here touches a real namespace. The fake records every method the
    hooks use, which is how read-only is proven rather than promised.
    """
    import json as _json
    import re as _re
    import shutil
    import tempfile
    import hooks
    from client import VantiqError

    root = tempfile.mkdtemp()
    saved_root = hooks.STATE_ROOT
    hooks.STATE_ROOT = os.path.join(root, "state")
    methods = []

    class Fake(object):
        def __init__(self, errors=None, missing=(), fail=None):
            self.errors, self.missing, self.fail = errors or {}, set(missing), fail
            self.paths = []
            self.server = "https://dev.example"
            self.connection = {"name": "vantiq", "scope": "project",
                               "host": "dev.example", "others": []}

        def raw(self, method, path, body=None, query=None, api=True):
            methods.append(method)
            self.paths.append(path)
            if self.fail:
                raise VantiqError(self.fail)
            if path in self.missing:
                return 400, [{"code": "io.vantiq.resource.not.found", "message": "m"}]
            return 200, {"name": path, "vailErrors": self.errors.get(path)}

    env = {"CLAUDE_PROJECT_DIR": root}
    src = "package com.acme\n\nPROCEDURE Svc.op(): Object\n\nreturn 1\n"
    err = [{"error": {"code": "io.vantiq.vail.syntax.error", "message": "boom"},
            "location": {"startPosition": {"line": 8, "column": 42}}}]

    def pay(tool, inp, resp=None, session="s1"):
        return {"session_id": session, "tool_name": "mcp__vantiq__" + tool,
                "tool_input": inp, "tool_response": resp}

    def run(fn, payload, fake=None, e=None):
        called = []

        def make(server, project):
            called.append(server)
            return fake or Fake()
        code, out, errtext = fn(payload, make_client=make, env=e or env)
        return code, out, errtext, called

    out = []
    try:
        # --- what fires, and what does not ---------------------------------
        c, o, e, called = run(hooks.post_tool_use,
                              pay("select", {"resource": "system.procedures"}))
        out.append(("a VIA read does not trigger a check", c == 0 and not o and not called))
        c, o, e, called = run(hooks.post_tool_use,
                              pay("upsert", {"resource": "system.types",
                                             "instance": {"name": "T"}}))
        out.append(("a write that carries no VAIL does not trigger a check",
                    c == 0 and not o and not called))
        c, o, e, called = run(hooks.post_tool_use,
                              pay("upsert", {"resource": "procedures",
                                             "instance": {"name": "Svc.op", "script": src}}),
                              e={"CLAUDE_PROJECT_DIR": root, "VQ_HOOKS": "off"})
        out.append(("VQ_HOOKS=off disables it completely", c == 0 and not o and not called))

        # --- the procedure and its SERVICE are both read back -------------
        fake = Fake()
        c, o, e, _ = run(hooks.post_tool_use,
                         pay("upsert", {"resource": "system.procedures",
                                        "instance": {"name": "Svc.op", "script": src}}), fake)
        out.append(("a clean write is silent and reads back procedure and service",
                    c == 0 and not o and not e and fake.paths ==
                    ["procedures/com.acme.Svc.op", "services/com.acme.Svc"]))

        fake = Fake(errors={"procedures/com.acme.Svc.op": err})
        c, o, e, _ = run(hooks.post_tool_use,
                         pay("upsert", {"resource": "procedures",
                                        "instance": {"name": "Svc.op", "script": src}}), fake)
        out.append(("a compile error goes back to Claude (exit 2, on stderr)",
                    c == 2 and "boom" in (e or "") and "line 8" in (e or "")))

        fake = Fake(errors={"services/com.acme.Svc": err})
        c, o, e, _ = run(hooks.post_tool_use,
                         pay("upsert", {"resource": "procedures",
                                        "instance": {"name": "Svc.op", "script": src}}), fake)
        out.append(("a clean procedure in a broken service is still caught (SC-44)",
                    c == 2 and "its service" in (e or "")))

        # --- lint is context, not an error ---------------------------------
        trap = src.replace("return 1", "var i = 0\nwhile (i < 3) {\n    i = i + 1\n}\nreturn i")
        c, o, e, _ = run(hooks.post_tool_use,
                         pay("upsert", {"resource": "procedures",
                                        "instance": {"name": "Svc.op", "script": trap}}))
        ctx = (_json.loads(o).get("hookSpecificOutput") or {}).get("additionalContext", "") \
            if o else ""
        out.append(("a lint finding reaches Claude as context, cited, without blocking",
                    c == 0 and "while-loop" in ctx and "SC-A06" in ctx))

        # --- names arrive in every form VIA accepts -----------------------
        T = hooks.target
        out.append(("a fully qualified procedure name is used as given",
                    T("upsert", {"resource": "procedures", "instance":
                                 {"name": "com.acme.Svc.op"}}, None)[1:3]
                    == ("com.acme.Svc.op", "com.acme.Svc")))
        out.append(("serviceName in the body qualifies a short name",
                    T("insert", {"resource": "procedures", "instance":
                                 {"name": "op", "serviceName": "com.acme.Svc"}}, None)[1:3]
                    == ("com.acme.Svc.op", "com.acme.Svc")))
        blocks = [{"type": "text", "text": _json.dumps(
            {"name": "op", "serviceName": "com.acme.Svc", "vailErrors": None})}]
        out.append(("the record VIA returned is preferred, in content blocks",
                    T("upsert", {"resource": "procedures", "instance": {"name": "x"}},
                      blocks)[1] == "com.acme.Svc.op"))
        big = "Error: result (315,557 characters) exceeds maximum allowed tokens."
        out.append(("an oversized result falls back to the name in the input",
                    T("upsert", {"resource": "procedures", "instance":
                                 {"name": "Svc.op", "script": src}}, big)[1]
                    == "com.acme.Svc.op"))
        out.append(("an update addressed by id is identified",
                    T("update", {"resource": "system.procedures",
                                 "resourceId": "com.acme.Svc.op",
                                 "updates": {"script": src}}, None)[1] == "com.acme.Svc.op"))
        out.append(("an update addressed by a query is skipped, not guessed",
                    T("update", {"resource": "procedures", "qual": {"name": "op"},
                                 "updates": {"script": src}}, None) is None))

        # --- a failure of the hook never blocks ---------------------------
        fake = Fake(fail="connection refused")
        c1, o1, e1, _ = run(hooks.post_tool_use,
                            pay("upsert", {"resource": "procedures", "instance":
                                           {"name": "Svc.op", "script": src}},
                                session="infra"), fake)
        c2, o2, e2, _ = run(hooks.post_tool_use,
                            pay("upsert", {"resource": "procedures", "instance":
                                           {"name": "Svc.op", "script": src}},
                                session="infra"), fake)
        out.append(("an unreachable server is reported once, and never blocks",
                    c1 == 0 and c2 == 0 and o1 and "could not" in o1
                    and "systemMessage" in o1 and not o2))

        # --- Stop ------------------------------------------------------------
        c, o, e, called = run(hooks.stop, {"session_id": "nothing-written"})
        out.append(("Stop does nothing, and calls nothing, if nothing was written",
                    c == 0 and not o and not called))

        run(hooks.post_tool_use, pay("upsert", {"resource": "procedures", "instance":
                                                {"name": "Svc.op", "script": src}},
                                     session="stop"))
        bad = Fake(errors={"procedures/com.acme.Svc.op": err})
        results = [run(hooks.stop, {"session_id": "stop"}, bad)[1] for _ in range(3)]
        decisions = [_json.loads(r).get("decision") for r in results]
        out.append(("Stop refuses to finish on a compile error, at most twice",
                    decisions == ["block", "block", None]
                    and "Not blocking again" in results[2]))

        run(hooks.post_tool_use, pay("upsert", {"resource": "procedures", "instance":
                                                {"name": "Svc.op", "script": src}},
                                     session="clean"))
        c, o, e, _ = run(hooks.stop, {"session_id": "clean"}, Fake())
        out.append(("Stop confirms a clean session to the user",
                    c == 0 and "read back clean" in (_json.loads(o).get("systemMessage") or "")))

        run(hooks.post_tool_use, pay("upsert", {"resource": "procedures", "instance":
                                                {"name": "Svc.op", "script": src}},
                                     session="deleted"))
        run(hooks.post_tool_use, pay("delete", {"resource": "procedures",
                                                "resourceId": "com.acme.Svc.op"},
                                     session="deleted"))
        fake = Fake()
        run(hooks.stop, {"session_id": "deleted"}, fake)
        out.append(("a deleted procedure is not re-read, but its service is",
                    fake.paths == ["services/com.acme.Svc"]))

        out.append(("every call the hooks made was a GET (read-only)",
                    methods and set(methods) == {"GET"}))

        # --- the real connection path: offline, and the token never leaks ---
        proj = os.path.join(root, "proj with spaces")
        os.makedirs(proj)
        io.open(os.path.join(proj, ".mcp.json"), "w", encoding="utf-8").write(_json.dumps(
            {"mcpServers": {"vantiq": {"type": "http",
             "url": "https://127.0.0.1:9/mcp/io.vantiq.via.mcpServer",
             "headers": {"Authorization": "Bearer fake-secret-hook"}}}}))
        code, o, e = hooks.post_tool_use(
            pay("upsert", {"resource": "procedures", "instance":
                           {"name": "Svc.op", "script": src}}, session="real"),
            env={"CLAUDE_PROJECT_DIR": proj})
        out.append(("through the real client, an unreachable host does not block or leak",
                    code == 0 and o and "fake-secret-hook" not in (o or "") + (e or "")))

        # --- install ---------------------------------------------------------
        settings = os.path.join(proj, ".claude", "settings.local.json")
        os.makedirs(os.path.dirname(settings))
        mine = {"permissions": {"allow": ["Bash(npm *)"]},
                "hooks": {"PostToolUse": [{"matcher": "Write|Edit", "hooks": [
                    {"type": "command", "command": "prettier --write"}]}]}}
        io.open(settings, "w", encoding="utf-8").write(_json.dumps(mine))
        os.makedirs(os.path.join(proj, ".git"))
        hooks.install(proj, python="C:/Py/python.exe", names=["vantiq", "prod"])
        hooks.install(proj, python="C:/Py/python.exe", names=["vantiq", "prod"])
        cfg = _json.load(io.open(settings, encoding="utf-8"))
        post = cfg["hooks"]["PostToolUse"]

        def is_ours(h):
            return any(str(a).replace("\\", "/").endswith("tools/vharness/hooks.py")
                       for a in (h.get("args") or []))
        ours = [h for g in post for h in g["hooks"] if is_ours(h)]
        out.append(("install keeps the user's own hooks and settings",
                    cfg["permissions"] == mine["permissions"]
                    and any(h.get("command") == "prettier --write"
                            for g in post for h in g["hooks"])))
        out.append(("re-running install does not add a second set",
                    len(ours) == 1 and len(cfg["hooks"]["Stop"]) == 1))
        out.append(("hooks run in exec form, so no shell parses a path with spaces",
                    len(ours) == 1 and ours[0]["command"] == "C:/Py/python.exe"
                    and ours[0]["args"][0].endswith("tools/vharness/hooks.py")
                    and " " in ours[0]["args"][0]))
        ours_groups = [g for g in post if any(is_ours(h) for h in g["hooks"])]
        m = _re.compile(ours_groups[0]["matcher"] if ours_groups else "^$")
        out.append(("the matcher takes VIA writes on every Vantiq connection, and nothing else",
                    all(m.search(n) for n in ("mcp__vantiq__upsert", "mcp__vantiqVia__delete",
                                              "mcp__prod__update"))
                    and not any(m.search(n) for n in ("mcp__vantiq__select",
                                                      "mcp__github__update",
                                                      "mcp__vantiq__upsert_x"))))
        gi = io.open(os.path.join(proj, ".gitignore"), encoding="utf-8").read()
        out.append(("in a git project, settings.local.json is ignored exactly once",
                    gi.count(".claude/settings.local.json") == 1))
        hooks.install(proj, remove=True)
        cfg = _json.load(io.open(settings, encoding="utf-8"))
        out.append(("removal takes out only this harness's hooks",
                    "Stop" not in cfg["hooks"] and len(cfg["hooks"]["PostToolUse"]) == 1
                    and not any(is_ours(h) for g in cfg["hooks"]["PostToolUse"]
                                for h in g["hooks"])))
        io.open(settings, "w", encoding="utf-8").write("{ not json")
        try:
            hooks.install(proj)
            refused = False
        except VantiqError:
            refused = io.open(settings, encoding="utf-8").read() == "{ not json"
        out.append(("a malformed settings file is refused and left untouched", refused))
        return out
    finally:
        hooks.STATE_ROOT = saved_root
        shutil.rmtree(root, ignore_errors=True)


def copy_cases():
    """Every copy the harness makes carries its LICENSE.

    MIT permits reuse on one condition: the notice travels with all copies or
    substantial portions. `package` and `install` copy by file extension, and
    LICENSE has none, so this is exactly the kind of requirement that is met
    once and then quietly stops being met when someone tidies the copy loop.
    """
    import contextlib
    import shutil
    import tempfile
    import vq
    root = tempfile.mkdtemp()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            vq.cmd_package(os.path.join(root, "pkg"))
            os.makedirs(os.path.join(root, "proj"))
            vq.cmd_install(os.path.join(root, "proj"))
        return [
            ("a `vq.py package` copy carries LICENSE",
             os.path.exists(os.path.join(root, "pkg", "LICENSE"))),
            ("a `vq.py install` copy carries LICENSE",
             os.path.exists(os.path.join(root, "proj", "tools", "vharness", "LICENSE"))),
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def citation_cases():
    """Every note a finding prints is an id NOTES.md actually has.

    `vq.py check` prints `[note SC-A06]` beside a finding so the reader can look
    it up. Those values were once the original author's loose count of an
    unnumbered block, off by one from the sixth note on, and every rule added
    from the pooled learnings printed no note at all. Both are held here: a
    cited id must exist, and a rule that came from a recorded learning must
    cite it. The rules allowed to print none are structural checks with no
    single incident behind them.
    """
    import re as _re
    here = os.path.dirname(os.path.abspath(__file__))
    notes = io.open(os.path.join(here, "NOTES.md"), encoding="utf-8").read()
    ids = set(_re.findall(r"(?m)^(?:\| |- )([A-Z]{2}-[A-Z]?\d{2})\b", notes))
    structural = {"duplicate-key", "unquoted-key", "name-mismatch",
                  "no-package", "no-signature"}

    printed, uncited = set(), set()
    for c in CASES:
        name, body, rule, should_fire = c[:4]
        if not should_fire:
            continue
        expect = c[4] if len(c) > 4 else "Svc.thing"
        head = c[5] if len(c) > 5 else HEAD
        for f in check_text(head + body, expect):
            if f.rule != rule:
                continue
            if f.note:
                printed.add(f.note)
            elif rule not in structural:
                uncited.add(rule)

    written = set()
    for module in ("lint.py", "uilint.py"):
        src = io.open(os.path.join(here, module), encoding="utf-8").read()
        written |= set(_re.findall(r'"((?:DM|NC|NR|PS|SC|DF)-[A-Z]?\d{2})"', src))

    return [
        ("every note a lint finding prints is an id in NOTES.md",
         printed and printed <= ids),
        ("every rule from a recorded learning cites it (uncited: %s)"
         % (", ".join(sorted(uncited)) or "none"), not uncited),
        ("every id written into lint.py and uilint.py exists in NOTES.md "
         "(missing: %s)" % (", ".join(sorted(written - ids)) or "none"),
         written <= ids),
    ]


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

    for label, fn in (("citations", citation_cases),
                      ("tree layouts", tree_cases),
                      ("VIA connection", connection_cases),
                      ("hooks", hook_cases),
                      ("copies", copy_cases),
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
