"""vq: one entry point for the Vantiq harness.

    python vq.py check   <project> [package]   lint what is deployed
    python vq.py ui      <project> [--house]   lint the console(s)
    python vq.py push    <project> <package>   the full pipeline, with gates
    python vq.py ops     <project> <package> [ReadModel ...]
    python vq.py health  <project> [package]   compile state, both levels
    python vq.py selftest                      prove the rules still hold
    python vq.py install <project>             copy the harness into a project
    python vq.py package <dest>                a clean copy to hand to someone else

`<project>` is a folder holding a .mcp.json. The package is discovered from the
namespace when omitted, because on a project you did not set up you will not
know it, and guessing wrong reports a clean sweep of nothing.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from client import Client, VantiqError  # noqa: E402


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
    if not os.path.exists(os.path.join(project, ".mcp.json")):
        raise SystemExit("no .mcp.json in %s; this is not a Vantiq project folder"
                         % project)
    return Client(repo=project)


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
            print("      :%-5d %-20s %s" % (f.line, f.rule, f.message[:80]))
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


def cmd_install(project):
    """Copy the harness into a project that has never seen it."""
    import shutil
    dest = os.path.join(project, "tools", "vharness")
    os.makedirs(dest, exist_ok=True)
    n = 0
    for fn in sorted(os.listdir(HERE)):
        if fn.endswith((".py", ".md")) and fn != "sync.py":
            shutil.copy2(os.path.join(HERE, fn), os.path.join(dest, fn))
            n += 1
    n += _copy_learnings(dest)
    print("installed %d files into %s" % (n, os.path.relpath(dest, project)))
    print("run:  python tools/vharness/vq.py check .")
    return 0


def cmd_package(dest):
    """A copy fit to hand to another Vantiq developer.

    Leaves behind the two files that only mean something inside this repo:
    sync.py knows one team's seven demo folders, and notes_index.py needs the
    demo-series documents to rebuild the first half of NOTES.md - without them
    it refuses rather than writing a truncated file, which is right here and
    unhelpful in a copy.

    NOTES.md itself ships, because the 213 recorded behaviours are the most
    portable thing here, and so does learnings/, because every rule taken from
    the pooled corpus cites an entry id and the recipient needs to be able to
    read the entry.
    """
    import shutil
    SERIES_ONLY = {"sync.py", "notes_index.py"}
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
    print("packaged %d files into %s, plus %d in learnings/"
          % (len(taken), dest, learned))
    print("  left behind (this repo only): %s" % ", ".join(left))
    print("")
    print("for the recipient:")
    print("  python vq.py selftest              # 82 cases, proves the rules hold")
    print("  python vq.py check <project>       # a folder holding a .mcp.json")
    print("")
    print("Requires Python 3.6+ and nothing else. No third-party packages.")
    return 0


COMMANDS = {"package": cmd_package, "check": cmd_check, "ui": cmd_ui, "push": cmd_push, "ops": cmd_ops,
            "health": cmd_health, "selftest": cmd_selftest, "install": cmd_install}


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
