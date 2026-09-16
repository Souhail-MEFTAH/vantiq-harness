"""vq: one entry point for the Vantiq harness.

    python vq.py check   <project> [package]   lint what is deployed
    python vq.py ui      <project> [--house]   lint the console(s)
    python vq.py push    <project> <package>   the full pipeline, with gates
    python vq.py ops     <project> [package] [ReadModel ...]
    python vq.py health  <project> [package]   compile state, both levels
    python vq.py selftest                      prove the rules still hold
    python vq.py init    <project>             START HERE on a new project
    python vq.py install <project>             copy the files only, no CLAUDE.md
    python vq.py package <dest>                a clean copy to hand to someone else

`<project>` is the folder you run Claude Code in, connected to Vantiq VIA at any
scope: local, the project's .mcp.json, or user. The package is discovered from the
namespace when omitted, because on a project you did not set up you will not
know it, and guessing wrong reports a clean sweep of nothing.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from client import (Client, VantiqError, describe_connection,  # noqa: E402
                    find_connection)


def discover_package(client):
    """The package prefix this namespace's own services share.

    Everything under io.vantiq.* is platform infrastructure and is excluded, or
    a namespace with one app looks like it has two.
    """
    names = [s.get("name", "") for s in client.select("services", limit=500,
                                                      props=["name"])]
    pkgs = {}
    for n in names:
        if not n or n.startswith("io.vantiq."):
            continue
        parts = n.split(".")
        if len(parts) >= 3:
            pkgs.setdefault(".".join(parts[:3]), 0)
            pkgs[".".join(parts[:3])] += 1
    if not pkgs:
        return None
    return max(pkgs.items(), key=lambda kv: kv[1])[0]


def _client(project):
    """A client on the VIA connection Claude Code uses in `project`, announced.

    It always says which connection, because writes land in whatever namespace
    the token belongs to (DM-21, NR-51), and a clean result read from one
    namespace says nothing about another.
    """
    try:
        c = Client(repo=project)
    except VantiqError as exc:
        raise SystemExit(str(exc))
    print(describe_connection(c.connection))
    return c


def cmd_check(project, package=None):
    import collections
    from lint import check_namespace, check_tree
    c = _client(project)
    package = package or discover_package(c)
    if not package:
        raise SystemExit("could not find an application package in this namespace")
    tree = os.path.join(project, "src", "procedures")
    if os.path.isdir(tree):
        print("linting the source tree at src/procedures")
        res = check_tree(tree)
        label = lambda k: os.path.basename(k)
    else:
        print("no src/procedures; linting what is DEPLOYED in %s" % package)
        res = check_namespace(c, package)
        label = lambda k: k.split(".", 3)[-1]
    counts = collections.Counter(f.rule for fs in res.values() for f in fs)
    for key, fs in sorted(res.items()):
        for f in fs:
            note = (" [note %s]" % f.note) if f.note else ""
            print("  %-46s:%-5d %s%s\n      %s"
                  % (label(key)[:46], f.line, f.rule, note, f.message))
    print("\n%s" % (dict(counts) if counts else "clean"))
    return 1 if counts else 0


def cmd_ui(project, *flags):
    import collections
    from uilint import check_file
    house = "--house" in flags
    found = []
    for dirpath, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in
                   ("node_modules", ".git", "export", "archive", "__pycache__")]
        for fn in files:
            if fn.endswith((".html", ".js")) and "min." not in fn:
                p = os.path.join(dirpath, fn)
                if os.path.getsize(p) < 4000:
                    continue
                fs = check_file(p, house_style=house)
                if fs:
                    found.append((os.path.relpath(p, project), fs))
    total = collections.Counter()
    for rel, fs in found:
        print("  %s" % rel)
        for f in fs:
            total[f.rule] += 1
            note = (" [note %s]" % f.note) if f.note else ""
            print("      :%-5d %-20s %s%s" % (f.line, f.rule, f.message[:80], note))
    print("\n%s" % (dict(total) if total else "clean"))
    return 1 if total else 0


def cmd_push(project, package):
    import push
    return push.run(project, package)


def cmd_ops(project, package=None, *models):
    import opscheck
    c = _client(project)
    package = package or discover_package(c)
    models = list(models) or [m for m in _guess_read_models(c, package)]
    if not models:
        raise SystemExit("name at least one read model, e.g. ApiGateway.getRunState")
    opscheck.report(project, package, models)
    return 0


def _guess_read_models(client, package):
    """Procedures that look like a screen would poll them."""
    rows = client.select("procedures", limit=2000,
                         props=["name", "serviceName", "ars_createdBy"])
    out = []
    for r in rows:
        svc = r.get("serviceName") or ""
        if not svc.startswith(package) or r.get("ars_createdBy") == "system":
            continue
        if r["name"].startswith("get"):
            out.append(svc.split(".")[-1] + "." + r["name"])
    return sorted(out)[:8]


def cmd_health(project, package=None):
    c = _client(project)
    package = package or discover_package(c)
    errs = c.vail_errors(package)
    print("package: %s on %s" % (package, c.server))
    if errs:
        for k, v in errs.items():
            print("  %s: %s" % (k, str(v)[:300]))
        print("\n%d resource(s) will not compile" % len(errs))
        return 1
    print("  vailErrors: none, at procedure and service level")
    print("  note: this is NOT proof the services assemble. Use `push` for that,")
    print("  or call one procedure per service yourself.")
    return 0


def cmd_selftest():
    import subprocess
    return subprocess.call([sys.executable, os.path.join(HERE, "selftest.py")])


def _copy_learnings(dest):
    """The pooled corpus travels with the harness.

    Every rule added from it cites an entry id in its docstring - NR-17, PS-02,
    DM-01 - and an id with no file to look it up in is exactly the guard whose
    reason is not written down. Copied as a directory because that is how a
    colleague adds theirs: drop a VANTIQ-LEARNINGS-<name>.md in beside them.
    """
    import shutil
    src = os.path.join(HERE, "learnings")
    if not os.path.isdir(src):
        return 0
    out = os.path.join(dest, "learnings")
    os.makedirs(out, exist_ok=True)
    n = 0
    for fn in sorted(os.listdir(src)):
        if fn.endswith(".md"):
            shutil.copy2(os.path.join(src, fn), os.path.join(out, fn))
            n += 1
    return n


def _copy_license(dest):
    """The LICENSE travels with every copy, vendored ones included.

    MIT permits reuse on one condition: the notice is included in all copies or
    substantial portions. Everything else here is copied by extension, and
    LICENSE has none, so without this every `package` and every vendored
    tools/vharness would have shipped without the one file the license requires.
    """
    import shutil
    src = os.path.join(HERE, "LICENSE")
    if not os.path.exists(src):
        return 0
    shutil.copy2(src, os.path.join(dest, "LICENSE"))
    return 1


# What a Vantiq project's CLAUDE.md needs to say. Written into the project by
# `vq.py init`, between markers so a re-run replaces it instead of stacking.
#
# Deliberately SHORT. A CLAUDE.md that lists every trap gets skimmed and then
# ignored, and the traps are in NOTES.md where they belong, each with the error
# text that earned it. What has to be in context from the first turn is the
# doctrine, because it is the thing that changes how you work rather than
# something you look up once you are already stuck.
MARK_BEGIN = "<!-- vantiq-harness:begin -->"
MARK_END = "<!-- vantiq-harness:end -->"

CLAUDE_SECTION = """%s
## Working on this Vantiq project

You build here through Vantiq VIA, and VIA reporting success is not evidence
that what you built works. There is a build harness at `tools/vharness`; use it
rather than rebuilding its checks:

```
python tools/vharness/vq.py check  .            lint what is deployed (read-only)
python tools/vharness/vq.py health .            compile state, procedure AND service
python tools/vharness/vq.py ops    .            what a screen costs per day
python tools/vharness/vq.py push   . <package>  push with every gate
```

`tools/vharness/NOTES.md` records %d platform behaviours, each with the error
text that earned it. Read it before debugging something that "should work":
most of them are not things a linter can catch, and roughly two thirds have no
check at all.

**The one thing to carry into any Vantiq work:** a write through VIA succeeds and
the thing can still be broken, somewhere else or later. A clean push does not
mean the service compiles; `vailErrors: null` on a procedure does not mean its
service is healthy; and only calling a procedure proves the class assembled.
Verify by read-back and by execution, never by a status code.
%s
""" % (MARK_BEGIN, 223, MARK_END)


def _behaviour_count():
    """How many behaviours NOTES.md actually records, so the text cannot drift."""
    notes = os.path.join(HERE, "NOTES.md")
    if not os.path.exists(notes):
        return None
    import io as _io
    import re as _re
    text = _io.open(notes, encoding="utf-8", errors="replace").read()
    m = _re.search(r"^\| recorded learnings \|(.+)\|\s*$", text, _re.M)
    if not m:
        return None
    cells = [c.strip() for c in m.group(1).split("|") if c.strip().isdigit()]
    return int(cells[-1]) if cells else None


def cmd_init(project):
    """Set a project up so Claude knows the harness exists. Start here.

    `install` copies the files; that is necessary and not sufficient. A harness
    Claude has not been told about does not get used - it re-derives the same
    checks badly, or trusts a 200. This writes the CLAUDE.md section that puts
    the doctrine in context from the first turn, and is idempotent so it can be
    re-run after an upgrade.
    """
    import io as _io
    try:
        print(describe_connection(find_connection(project)))
    except VantiqError as exc:
        print("warning: %s" % exc)
        print("  init will still set the project up, but `check`, `health`, `ops`")
        print("  and `push` need that connection to read anything back.")
    print("")

    cmd_install(project)

    count = _behaviour_count()
    section = CLAUDE_SECTION
    if count and count != 223:
        section = section.replace("records 223 platform", "records %d platform" % count)

    path = os.path.join(project, "CLAUDE.md")
    existing = ""
    if os.path.exists(path):
        existing = _io.open(path, encoding="utf-8", errors="replace").read()

    if MARK_BEGIN in existing and MARK_END in existing:
        head = existing[:existing.index(MARK_BEGIN)]
        tail = existing[existing.index(MARK_END) + len(MARK_END):].lstrip("\n")
        merged = head + section + ("\n" + tail if tail else "")
        verb = "updated the harness section in"
    elif existing.strip():
        merged = existing.rstrip("\n") + "\n\n" + section
        verb = "appended a harness section to"
    else:
        merged = "# %s\n\n%s" % (os.path.basename(os.path.abspath(project)), section)
        verb = "created"
    _io.open(path, "w", encoding="utf-8", newline="\n").write(merged)
    print("%s CLAUDE.md" % verb)

    print("")
    print("next, in this order:")
    print("  1. read tools/vharness/NOTES.md            (install nothing, costs a tab)")
    print("  2. python tools/vharness/vq.py check .     (read-only, writes nothing)")
    print("  3. start Claude Code here; the CLAUDE.md is picked up automatically")
    return 0


def cmd_install(project):
    """Copy the harness into a project that has never seen it."""
    import shutil
    dest = os.path.join(project, "tools", "vharness")
    os.makedirs(dest, exist_ok=True)
    n = 0
    for fn in sorted(os.listdir(HERE)):
        if fn.endswith((".py", ".md")):
            shutil.copy2(os.path.join(HERE, fn), os.path.join(dest, fn))
            n += 1
    n += _copy_learnings(dest)
    n += _copy_license(dest)
    print("installed %d files into %s" % (n, os.path.relpath(dest, project)))
    print("run:  python tools/vharness/vq.py check .")
    return 0


def cmd_package(dest):
    """A copy fit to hand to another Vantiq developer.

    Leaves behind notes_index.py, which needs the demo-series documents to
    rebuild the first half of NOTES.md: without them it refuses rather than
    write a truncated file, which is right for a maintainer and unhelpful in a
    copy.

    NOTES.md itself ships, because the 223 recorded behaviours are the most
    portable thing here, and so does learnings/, because every rule taken from
    the pooled corpus cites an entry id and the recipient needs to be able to
    read the entry.
    """
    import shutil
    SERIES_ONLY = {"notes_index.py"}
    os.makedirs(dest, exist_ok=True)
    taken, left = [], []
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith((".py", ".md")):
            continue
        if fn in SERIES_ONLY:
            left.append(fn)
            continue
        shutil.copy2(os.path.join(HERE, fn), os.path.join(dest, fn))
        taken.append(fn)
    learned = _copy_learnings(dest)
    licensed = _copy_license(dest)
    print("packaged %d files into %s, plus %s%d in learnings/"
          % (len(taken), dest, "LICENSE and " if licensed else "", learned))
    print("  left behind (this repo only): %s" % ", ".join(left))
    print("")
    print("for the recipient:")
    print("  python vq.py selftest              # 145 assertions, proves the rules hold")
    print("  python vq.py check <project>       # a folder where Claude Code uses VIA")
    print("")
    print("Requires Python 3.6+ and nothing else. No third-party packages.")
    return 0


COMMANDS = {"package": cmd_package, "check": cmd_check, "ui": cmd_ui, "push": cmd_push, "ops": cmd_ops,
            "health": cmd_health, "selftest": cmd_selftest, "install": cmd_install,
            "init": cmd_init}


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd not in COMMANDS:
        print("unknown command %r\n" % cmd)
        print(__doc__)
        return 2
    try:
        return COMMANDS[cmd](*argv[1:]) or 0
    except TypeError as exc:
        print("wrong arguments for %s: %s\n" % (cmd, exc))
        print(__doc__)
        return 2
    except VantiqError as exc:
        print("vantiq: %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
