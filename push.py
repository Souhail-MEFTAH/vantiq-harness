"""Push VAIL from a source tree, and prove it works before saying so.

The pipeline, in the order the failures demand:

  1. lint          static traps, before anything reaches the wire
  2. snapshot      versions before, so the change can be stated exactly
  3. drift         local signatures against the DEPLOYED interface
  4. push          each procedure, verified by read-back
  5. interface     rebuilt from the procedures the service now owns
  6. vailErrors    at procedure AND service level
  7. smoke         call into each touched service; only execution proves it
  8. report        exactly which resources moved

Steps 3, 6 and 7 all exist for the same trap, which is the most expensive one on
this platform and has been rediscovered at least three times:

  Adding a parameter to a procedure on a service that declares an explicit
  interface returns HTTP 200. The PROCEDURE reads vailErrors: null with a
  populated AST. The SERVICE carries io.vantiq.service.operation.mismatched.
  parameters, and every procedure in that service stops compiling.

And step 7 exists because even the service-level check is not sufficient: a
variable named `it` collides with Groovy's implicit closure parameter and fails
the class assembly with every vailErrors field clean. Only calling into the
service proves it.
"""
import json
import os
import re
import sys
import urllib.parse

from client import Client, VantiqError
from lint import SIG, check_tree
from source import blank

INDENT = "  "


def collect(proc_dir, package, only=None):
    """Procedures from <proc_dir>/<Service>/<name>.vail.

    The filesystem layout is the manifest: name and serviceName come from the
    path, so a declaration that disagrees is a lint error rather than a second
    source of truth. `_package` holds procedures owned by the package rather
    than any service.
    """
    procs = []
    for service in sorted(os.listdir(proc_dir)):
        sdir = os.path.join(proc_dir, service)
        if not os.path.isdir(sdir) or (only and service not in only):
            continue
        for fn in sorted(os.listdir(sdir)):
            if not fn.endswith(".vail"):
                continue
            with open(os.path.join(sdir, fn), encoding="utf-8") as fh:
                script = fh.read()
            short = fn[:-5]
            if service == "_package":
                procs.append({"name": "%s.%s" % (package, short),
                              "script": script, "language": "VAIL"})
            else:
                procs.append({"name": short,
                              "serviceName": "%s.%s" % (package, service),
                              "script": script, "language": "VAIL"})
    return procs


def signature_of(script):
    """(name, [param names], is_private) from a procedure body, or None.

    Matched against the BLANKED view. A parameter carries
    `DESCRIPTION "start_simulation | ... (foo)"`, and counting parentheses in the
    raw text runs the matcher past the closing paren and into the body, so the
    parameter list comes back with `if`, `e` and whatever else it swept up. That
    turned the drift check into eighteen false alarms on a tree that was
    byte-identical to what was deployed.
    """
    blanked = blank(script)
    m = SIG.search(blanked)
    if not m:
        return None
    depth, i = 0, m.end() - 1
    start = i
    while i < len(blanked):
        if blanked[i] == "(":
            depth += 1
        elif blanked[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    params = []
    for part in blanked[start + 1:i].split(","):
        pm = re.match(r"\s*(\w+)", part)
        if pm:
            params.append(pm.group(1))
    # A word boundary, not space-delimited. SIG's leading `\s*` puts a newline
    # at the front of the match, so testing for " PRIVATE " missed every
    # declaration that starts a line, which is all of them.
    head = blanked[max(0, m.start()):m.end()]
    return m.group(1), params, bool(re.search(r"\bPRIVATE\b", head))


def interface_drift(client, procs, package):
    """Local parameter lists against what each service's interface declares.

    This is the trap, caught BEFORE the write instead of after. A changed
    parameter list on an interface-declaring service is not an edit, it is a
    service-wide outage that reports success.
    """
    services = sorted({p["serviceName"] for p in procs if p.get("serviceName")})
    drift = []
    for svc in services:
        # A direct GET, not a select with props. `hasExplicitInterface` is
        # returned on the resource but is not a queryable property: asking for it
        # in props fails the whole query with
        # "The property: system.services.hasExplicitInterface is not defined."
        status, row = client.call("GET", "services/" + urllib.parse.quote(svc))
        if status != 200 or not isinstance(row, dict):
            continue
        if not row.get("hasExplicitInterface"):
            continue
        declared = {}
        for op in (row.get("interface") or []):
            declared[op.get("name")] = [p.get("name") for p in (op.get("parameters") or [])]
        for p in procs:
            if p.get("serviceName") != svc:
                continue
            sig = signature_of(p["script"])
            if not sig:
                continue
            short, params, is_private = sig
            short = short.split(".")[-1]
            # A PRIVATE procedure is not an operation and is correctly absent
            # from the interface. Reporting it as drift flagged thirteen
            # deliberately private builders on a healthy tree.
            if is_private:
                continue
            if short not in declared:
                drift.append((svc, short, "not in the declared interface",
                              declared.get(short), params))
            elif declared[short] != params:
                drift.append((svc, short, "parameter list differs",
                              declared[short], params))
    return drift


def rebuild_interfaces(client, services):
    """A procedure absent from its service interface fails to compile.

    Rebuilt from the procedures the service actually owns, so adding one is a
    file plus a push rather than a second thing to remember. Private procedures
    are excluded: they are not operations.
    """
    out = []
    for svc in sorted(services):
        rows = client.select("procedures", where={"serviceName": svc},
                             props=["name", "isPrivate", "parameters", "description"])
        iface = []
        for r in rows:
            if r.get("isPrivate"):
                continue
            entry = {"name": r["name"]}
            if r.get("parameters"):
                entry["parameters"] = r["parameters"]
            if r.get("description"):
                entry["description"] = r["description"]
            iface.append(entry)
        iface.sort(key=lambda e: e["name"])
        status, body = client.raw("POST", "services", {"name": svc, "interface": iface})
        out.append((svc, len(iface), status))
    return out


COMPILE_FAILURES = ("could not be compiled", "startup failed",
                    "compilation failed", "groovy.lang")


def smoke(client, services):
    """Call into each service. Only execution proves the class assembled.

    The GOAL is to force the service's Groovy class to assemble, because a
    variable named `it` (or anything else that breaks assembly) leaves every
    procedure reporting `vailErrors: null` while the whole service is dead.
    Any invocation forces that. What comes back barely matters.

    An earlier version probed `Service.ping()`. That is a convention of one
    project: of nineteen services across three other Vantiq projects, NONE had a
    ping, so every service would have been reported unverified and the push
    refused. The probe now prefers a zero-argument public procedure and falls
    back to any public procedure at all.

    An ARGUMENT error is a PASS. "parameter is required but has not been
    assigned a value" can only be raised by a class that compiled and ran.
    """
    broken, tested, unverifiable = [], 0, []
    for svc in sorted(services):
        rows = client.select("procedures", where={"serviceName": svc},
                             props=["name", "isPrivate", "parameters"])
        public = [r for r in rows if not r.get("isPrivate")]
        if not public:
            unverifiable.append((svc, "no public procedure to call"))
            continue
        # A zero-argument procedure gives the cleanest signal; otherwise any one
        # will do, because the argument error still proves assembly.
        zero = [r for r in public if not r.get("parameters")]
        probe = (zero or public)[0]
        name = "%s.%s" % (svc, probe["name"])
        status, body = client.raw("POST", "procedures/" + name, {})
        text = json.dumps(body) if body else ""
        low = text.lower()
        if any(sig in low for sig in COMPILE_FAILURES):
            broken.append((svc, text[:300]))
        elif status == 200 or "has not been assigned a value" in low or \
                "is required" in low:
            tested += 1
        elif status in (0, 404):
            unverifiable.append((svc, "%s could not be reached (status %s)"
                                 % (name, status)))
        else:
            # Some other runtime error. The class ran to raise it, so assembly
            # is proven; the error is the procedure's business, not the push's.
            tested += 1
    return broken, tested, unverifiable


def run(repo, package, proc_dir=None, only=None, allow_drift=False):
    proc_dir = proc_dir or os.path.join(repo, "src", "procedures")
    client = Client(repo=repo)
    print("push %s -> %s" % (os.path.relpath(proc_dir, repo), client.server))

    # 1. lint
    findings = check_tree(proc_dir)
    if findings:
        print("\nLINT (nothing was pushed):")
        for path, fs in sorted(findings.items()):
            for f in fs:
                note = (" [note %s]" % f.note) if f.note else ""
                print("%s%s:%d %s%s\n%s%s%s" % (INDENT, os.path.basename(path), f.line,
                                                f.rule, note, INDENT, INDENT, f.message))
        return 1
    print(INDENT + "lint: clean")

    procs = collect(proc_dir, package, only)
    if not procs:
        print("no procedures found")
        return 1
    services = sorted({p["serviceName"] for p in procs if p.get("serviceName")})

    # 2. before
    before = client.snapshot(package)

    # 3. drift, the interface trap, caught before the write
    drift = interface_drift(client, procs, package)
    if drift and not allow_drift:
        print("\nINTERFACE DRIFT (nothing was pushed):")
        for svc, name, why, declared, local in drift:
            print("%s%s.%s: %s\n%s%sdeclared %s\n%s%slocal    %s"
                  % (INDENT, svc.split(".")[-1], name, why,
                     INDENT, INDENT, declared, INDENT, INDENT, local))
        print("\n%sChanging a parameter list on a service with an explicit interface"
              % INDENT)
        print("%sreturns 200 and stops every procedure in that service from" % INDENT)
        print("%scompiling. Re-run with allow_drift=True only if the interface is" % INDENT)
        print("%sbeing updated in the same push." % INDENT)
        return 1
    if drift:
        print(INDENT + "drift: %d signature change(s), proceeding as asked" % len(drift))

    # 4. push
    failed = []
    for p in procs:
        try:
            client.upsert("procedures", p)
        except VantiqError as exc:
            failed.append((p.get("name"), str(exc)[:200]))
    print("%spushed: %d/%d verified by read-back" % (INDENT, len(procs) - len(failed),
                                                     len(procs)))
    for n, msg in failed:
        print("%s%sFAILED %s: %s" % (INDENT, INDENT, n, msg))

    # 5. interfaces
    for svc, n, status in rebuild_interfaces(client, services):
        print("%sinterface %-28s %2d operations -> %s"
              % (INDENT, svc.split(".")[-1], n, status))

    # 6. vailErrors, both levels
    errs = client.vail_errors(package)
    if errs:
        print("\nVAIL ERRORS:")
        for k, v in errs.items():
            print("%s%s: %s" % (INDENT, k, json.dumps(v)[:400]))
        return 1
    print(INDENT + "vailErrors: none, at procedure and service level")

    # 7. execution
    broken, tested, unverifiable = smoke(client, services)
    if broken:
        print("\nSERVICE WILL NOT COMPILE (vailErrors does not catch this):")
        for name, msg in broken:
            print("%s%s: %s" % (INDENT, name.split(".")[-1], msg))
        return 1
    # A service with nothing public to call cannot be proven, and a failure to
    # test must never be reported as a pass. It is named and does not block:
    # refusing the push would make the harness unusable on a namespace whose
    # services are entirely event-driven, which is a legitimate design and is
    # exactly what two services in this series are.
    for svc, why in unverifiable:
        print("%s!! %s UNVERIFIED: %s" % (INDENT, svc.split(".")[-1], why))
    print("%ssmoke: %d/%d services execute%s"
          % (INDENT, tested, len(services),
             (", %d unverifiable" % len(unverifiable)) if unverifiable else ""))

    # 8. what actually moved
    after = client.snapshot(package)
    added = sorted(set(after) - set(before))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    print("%schanged: %d resource(s)%s" % (INDENT, len(added) + len(changed),
                                           (", added %d" % len(added)) if added else ""))
    return 0 if not failed else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: push.py <repo> <package> [Service ...]")
        raise SystemExit(2)
    sys.exit(run(sys.argv[1], sys.argv[2], only=set(sys.argv[3:]) or None))
