"""Claude Code hooks: check what Claude writes through Vantiq VIA, as it writes it.

The doctrine of this harness is that a write reporting success proves nothing.
For a long time the only thing enforcing that was a paragraph in CLAUDE.md
asking Claude to check its work - an instruction, which Claude can skip. These
hooks make the check happen whether Claude remembers or not.

  post-tool-use   After every VIA upsert, insert, update or delete of VAIL: lint
                  the source Claude sent, read the resource back, and read back
                  the SERVICE it belongs to as well, because a procedure can
                  report clean while its service has stopped compiling (SC-44).
                  A compile error goes straight back to Claude. Lint findings go
                  back as context Claude can weigh, not as errors, because a
                  linter can be wrong and the compiler cannot.

  stop            Before the session ends, re-check everything written in it,
                  and refuse to finish while any of it does not compile - twice
                  at most, so a problem Claude cannot fix never traps a session.

READ-ONLY BY CONSTRUCTION. Nothing here writes to, deletes from or executes
anything in the namespace: it issues GETs, and tells Claude what it found. A
self-test holds that.

A failure of the hook itself - no connection, a rejected token, a timeout, a
bug - never blocks Claude. It is reported once per session as something that
could not be verified, which is the truth, and the session carries on.

Installed by `vq.py init` into the project's .claude/settings.local.json.
Disable without editing anything: set VQ_HOOKS=off.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from client import (Client, VantiqError, describe_connection,  # noqa: E402
                    find_connection, find_connection_named, is_not_found,
                    vantiq_connection_names)
from lint import check_text  # noqa: E402

# VIA exposes generic tools rather than one per resource. Of 461 local
# sessions, every VAIL write went through one of these four, with the resource
# type in `resource` and the source in `instance.script` or `updates.script`.
WRITE_TOOLS = ("upsert", "insert", "update", "delete")
VAIL_KINDS = ("procedures", "rules", "services")

# The same rules check_namespace() skips for deployed source: there is no file
# path for a name to disagree with, and the package can live in serviceName.
SKIP_LINT = ("no-package", "name-mismatch", "no-signature")

READ_TIMEOUT = 10          # seconds per GET; the hook itself is allowed 30
MAX_STOP_BLOCKS = 2        # then report and let the session end
MAX_TRACKED = 20           # resources re-checked at Stop
STOP_BUDGET = 80           # seconds; the Stop hook itself is allowed 120
STALE_DAYS = 7

STATE_ROOT = None          # tests point this somewhere disposable


# --------------------------------------------------------------- reading ---

def disabled(env):
    return str(env.get("VQ_HOOKS", "")).strip().lower() in ("off", "0", "false", "no")


def parse_tool(tool_name):
    """(server, tool) from mcp__<server>__<tool>, or (None, None)."""
    m = re.match(r"^mcp__(.+?)__(.+)$", tool_name or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def kind_of(resource):
    """VIA accepts `system.procedures` and `procedures` alike; REST wants the latter."""
    r = (resource or "").strip() if isinstance(resource, str) else ""
    return r[len("system."):] if r.startswith("system.") else r


def _json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _record(response):
    """The stored record VIA returned, when there is one to read a name from.

    The shape reaching a hook is not pinned down anywhere, so every plausible
    one is handled: the record itself, its JSON text, MCP content blocks, or a
    wrapper holding those blocks. Anything else - including the "result exceeds
    maximum allowed tokens" text large writes come back as - yields None, and
    the name is taken from the tool input instead.
    """
    cand = response
    for _ in range(3):
        if isinstance(cand, str):
            cand = _json(cand)
        elif isinstance(cand, list):
            cand = _json("".join(b.get("text", "") for b in cand if isinstance(b, dict)))
        elif isinstance(cand, dict) and "name" not in cand and isinstance(cand.get("content"), list):
            cand = cand["content"]
        else:
            break
    return cand if isinstance(cand, dict) and isinstance(cand.get("name"), str) else None


def _package(script):
    m = re.search(r"^\s*package\s+([\w.]+)", script or "", re.M | re.I)
    return m.group(1) if m else None


def target(tool, tool_input, tool_response):
    """(kind, fqn, service, script) for a VAIL write this hook can identify, or None.

    Procedure names arrive in every form VIA accepts - `Service.op`, fully
    qualified, bare with the service in `serviceName` - so the qualified name is
    rebuilt from whatever is present, preferring the record VIA returned. An
    update addressed by a query rather than a name is not identifiable, and is
    skipped rather than guessed at.
    """
    kind = kind_of(tool_input.get("resource"))
    if kind not in VAIL_KINDS:
        return None
    body = tool_input.get("instance") or tool_input.get("updates") or tool_input.get("object")
    body = body if isinstance(body, dict) else {}
    script = body.get("script") if isinstance(body.get("script"), str) else None
    rec = _record(tool_response) or {}
    name = rec.get("name") or body.get("name") or tool_input.get("resourceId")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    service = rec.get("serviceName") or body.get("serviceName")
    package = _package(script)

    if kind != "procedures":
        if "." not in name and package:
            name = "%s.%s" % (package, name)
        return kind, name, None, script

    if service:
        return kind, "%s.%s" % (service, name.split(".")[-1]), service, script
    dots = name.count(".")
    if dots >= 2:
        return kind, name, name.rsplit(".", 1)[0], script
    if dots == 1:
        svc, op = name.split(".")
        if package:
            return kind, "%s.%s.%s" % (package, svc, op), "%s.%s" % (package, svc), script
        return kind, name, svc, script
    return kind, ("%s.%s" % (package, name)) if package else name, None, script


def read_errors(client, kind, fqn):
    """vailErrors on one resource: a list (empty when clean), or None if not found.

    GET only. Anything but a readable 200 or a not-found is a VantiqError, so
    the caller reports "could not verify" rather than "clean".
    """
    path = "%s/%s" % (kind, urllib.parse.quote(fqn, safe=""))
    status, body = client.raw("GET", path)
    if is_not_found(status, body):
        return None
    if status != 200 or not isinstance(body, dict):
        raise VantiqError("GET %s answered %s" % (path, status or "nothing"))
    errs = body.get("vailErrors")
    return errs if errs else []


def describe_errors(errs, limit=5):
    items = errs if isinstance(errs, list) else [errs]
    out = []
    for e in items[:limit]:
        if isinstance(e, dict):
            inner = e.get("error") if isinstance(e.get("error"), dict) else e
            msg = inner.get("message") or json.dumps(inner)[:200]
            pos = (e.get("location") or {}).get("startPosition") or {}
            where = " (line %s, column %s)" % (pos.get("line"), pos.get("column")) \
                if pos.get("line") else ""
            code = " [%s]" % inner["code"] if inner.get("code") else ""
            out.append("%s%s%s" % (msg, where, code))
        else:
            out.append(str(e)[:300])
    if len(items) > limit:
        out.append("... and %d more" % (len(items) - limit))
    return out


def client_for(server, project):
    """A short-timeout client on the connection Claude actually wrote through."""
    try:
        conn = find_connection_named(server, project)
    except VantiqError:
        conn = find_connection(project)
    c = Client(server=conn["server"], token=conn["token"], timeout=READ_TIMEOUT)
    c.connection = dict((k, v) for k, v in conn.items() if k != "token")
    return c


# ----------------------------------------------------------------- state ---

def state_dir(session_id):
    root = STATE_ROOT or os.path.join(tempfile.gettempdir(), "vharness-hooks")
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "")[:80] or "no-session"
    path = os.path.join(root, safe)
    os.makedirs(path, exist_ok=True)
    return path


def record_write(session_id, entry):
    """One file per write, so parallel tool calls never race on a shared file."""
    d = state_dir(session_id)
    name = "w-%d-%d.json" % (int(time.time() * 1000000), os.getpid())
    tmp = os.path.join(d, name + ".tmp")
    with io.open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(entry))
    os.replace(tmp, os.path.join(d, name))


def written(session_id):
    d = state_dir(session_id)
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.startswith("w-") and fn.endswith(".json"):
            try:
                with io.open(os.path.join(d, fn), encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except (OSError, ValueError):
                continue
    return out


def counter(session_id, name, bump=False):
    path = os.path.join(state_dir(session_id), name)
    try:
        with io.open(path, encoding="utf-8") as fh:
            n = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        n = 0
    if bump:
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(str(n + 1))
    return n


def sweep_stale():
    """Session folders older than STALE_DAYS are left by sessions long over."""
    root = STATE_ROOT or os.path.join(tempfile.gettempdir(), "vharness-hooks")
    if not os.path.isdir(root):
        return
    cutoff = time.time() - STALE_DAYS * 86400
    for fn in os.listdir(root):
        path = os.path.join(root, fn)
        try:
            if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


# ----------------------------------------------------------------- hooks ---

def _context(text, user=None):
    out = {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                  "additionalContext": text}}
    if user:
        out["systemMessage"] = user
    return json.dumps(out)


def post_tool_use(payload, make_client=None, env=None):
    """Returns (exit_code, stdout, stderr)."""
    env = os.environ if env is None else env
    if disabled(env):
        return 0, None, None
    server, tool = parse_tool(payload.get("tool_name"))
    if tool not in WRITE_TOOLS:
        return 0, None, None
    tool_input = payload.get("tool_input") or {}
    t = target(tool, tool_input if isinstance(tool_input, dict) else {},
               payload.get("tool_response"))
    if not t:
        return 0, None, None
    kind, fqn, service, script = t
    session = payload.get("session_id")
    project = env.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    record_write(session, {"server": server, "kind": kind, "fqn": fqn,
                           "service": service, "deleted": tool == "delete"})

    lint_notes = []
    if script and tool != "delete":
        for f in check_text(script):
            if f.rule in SKIP_LINT:
                continue
            note = " [note %s]" % f.note if f.note else ""
            lint_notes.append("line %d, %s%s: %s" % (f.line, f.rule, note, f.message))

    problems, unverified, via = [], [], "?"
    try:
        client = (make_client or client_for)(server, project)
        via = describe_connection(client.connection).split("\n")[0] \
            if getattr(client, "connection", None) else client.server
        if tool != "delete":
            errs = read_errors(client, kind, fqn)
            if errs is None:
                unverified.append("%s %s was not found on read-back, so it could not be "
                                  "checked; if it was written under another name, check "
                                  "that one yourself" % (kind[:-1], fqn))
            elif errs:
                problems.append(("%s %s" % (kind[:-1], fqn), errs))
        if service and kind == "procedures":
            serrs = read_errors(client, "services", service)
            if serrs:
                problems.append(("its service %s" % service, serrs))
    except VantiqError as exc:
        reason = str(exc)
        if counter(session, "infra-warned"):
            if lint_notes:
                return 0, _context("vantiq-harness lint on %s:\n  %s"
                                   % (fqn, "\n  ".join(lint_notes))), None
            return 0, None, None
        counter(session, "infra-warned", bump=True)
        text = ("vantiq-harness could not read back %s to check that it compiles: %s. "
                "The write was not verified - check it yourself before building on it."
                % (fqn, reason))
        if lint_notes:
            text += "\nLint on the source you sent:\n  " + "\n  ".join(lint_notes)
        return 0, _context(text, user="vantiq-harness could not verify VIA writes: %s "
                                      "(reported once per session)" % reason), None

    if problems:
        lines = ["vantiq-harness: the VIA %s reported success, and it does not compile."
                 % tool]
        for label, errs in problems:
            lines.append("  %s:" % label)
            lines.extend("    - %s" % m for m in describe_errors(errs))
        if any(label.startswith("its service") for label, _e in problems):
            lines.append("  A procedure can read clean while its service is broken - an "
                         "interface out of step with the procedures is the usual cause.")
        if lint_notes:
            lines.append("  Lint on the source you sent, which may explain it:")
            lines.extend("    - %s" % n for n in lint_notes)
        lines.append("  Fix this before building on it. Read back through %s." % via)
        return 2, None, "\n".join(lines) + "\n"

    notes = []
    if lint_notes:
        notes.append("vantiq-harness lint on %s - these compiled, but each is a trap that "
                     "has cost someone time; weigh them:\n  %s"
                     % (fqn, "\n  ".join(lint_notes)))
    notes.extend(unverified)
    if notes:
        return 0, _context("\n".join(notes)), None
    return 0, None, None


def stop(payload, make_client=None, env=None):
    """Returns (exit_code, stdout, stderr)."""
    env = os.environ if env is None else env
    if disabled(env):
        return 0, None, None
    session = payload.get("session_id")
    entries = written(session)
    sweep_stale()
    if not entries:
        return 0, None, None
    project = env.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()

    by_server = {}
    for e in entries:
        s = by_server.setdefault(e.get("server"), {"resources": {}, "services": set()})
        key = (e.get("kind"), e.get("fqn"))
        if e.get("deleted"):
            s["resources"].pop(key, None)
        else:
            s["resources"][key] = True
        if e.get("service"):
            s["services"].add(e["service"])

    started, checked, problems, skipped = time.time(), 0, [], 0
    try:
        for server, work in by_server.items():
            client = (make_client or client_for)(server, project)
            todo = [("resource",) + k for k in work["resources"]] + \
                   [("service", "services", svc) for svc in sorted(work["services"])]
            for _label, kind, fqn in todo:
                if checked >= MAX_TRACKED or time.time() - started > STOP_BUDGET:
                    skipped += 1
                    continue
                errs = read_errors(client, kind, fqn)
                checked += 1
                if errs:
                    problems.append(("%s %s" % (kind[:-1], fqn), errs))
    except VantiqError as exc:
        return 0, json.dumps({"systemMessage":
                              "vantiq-harness could not check this session's VIA writes "
                              "before it ended: %s" % exc}), None

    tail = (" (%d more not checked in the time allowed)" % skipped) if skipped else ""
    if problems:
        if counter(session, "stop-blocks") >= MAX_STOP_BLOCKS:
            return 0, json.dumps({"systemMessage":
                                  "vantiq-harness: %d resource(s) written this session still "
                                  "do not compile%s. Not blocking again."
                                  % (len(problems), tail)}), None
        counter(session, "stop-blocks", bump=True)
        lines = ["vantiq-harness: before finishing, %d resource(s) written through VIA in "
                 "this session do not compile:" % len(problems)]
        for label, errs in problems:
            lines.append("  %s:" % label)
            lines.extend("    - %s" % m for m in describe_errors(errs))
        lines.append("Fix them, or if an error was already there before this session and is "
                     "out of scope, say so plainly to the user and finish.")
        return 0, json.dumps({"decision": "block", "reason": "\n".join(lines)}), None

    return 0, json.dumps({"systemMessage":
                          "vantiq-harness: %d VIA write(s) this session read back clean%s."
                          % (checked, tail)}), None


# --------------------------------------------------------------- install ---

def _js_escape(name):
    return re.sub(r"([.^$*+?()\[\]{}|\\/])", r"\\\1", name)


def matcher(names=None):
    """Anchored, for the VIA write tools on every Vantiq connection known here.

    Named connections are listed so a VIA server called something without
    "vantiq" in it still matches; the pattern also covers any server that does
    have it, so a connection added later is caught without re-running init.
    The hook re-checks the server itself, so a loose match costs a no-op.
    """
    alts = sorted(set(_js_escape(n) for n in (names or []) if n)) + [".*[Vv]antiq.*"]
    return "^mcp__(?:%s)__(?:%s)$" % ("|".join(alts), "|".join(WRITE_TOOLS))


def _is_ours(hook):
    return any(str(a).replace("\\", "/").endswith("vharness/hooks.py")
               for a in (hook.get("args") or []))


def install(project, remove=False, python=None, names=None):
    """Merge the hooks into <project>/.claude/settings.local.json. Returns the path.

    settings.local.json, not settings.json: the command is this machine's
    Python by absolute path, which means nothing on a colleague's machine, and
    it is the per-developer file Claude Code keeps out of version control.

    Exec form - `command` plus `args` - so no shell parses the paths. A OneDrive
    folder has spaces in it, and the same command string is read by bash,
    PowerShell or cmd depending on the machine. With `args` it is none of them.

    Merges: everything else in the file, including other hooks, is kept.
    Re-running replaces this harness's entries rather than adding a second set.
    A file that is not valid JSON is refused, never overwritten.
    """
    project = os.path.abspath(project)
    path = os.path.join(project, ".claude", "settings.local.json")
    settings = {}
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            raw = fh.read()
        if raw.strip():
            try:
                settings = json.loads(raw)
            except ValueError as exc:
                raise VantiqError("%s is not valid JSON (%s); not touching it" % (path, exc))
    hooks = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}

    for event in ("PostToolUse", "Stop"):
        kept = []
        for group in hooks.get(event) or []:
            rest = [h for h in (group.get("hooks") or []) if not _is_ours(h)]
            if rest:
                kept.append(dict(group, hooks=rest))
        hooks[event] = kept

    if not remove:
        py = (python or sys.executable).replace("\\", "/")
        script = os.path.join(project, "tools", "vharness", "hooks.py").replace("\\", "/")
        if names is None:
            names = vantiq_connection_names(project)
        hooks["PostToolUse"].append({
            "matcher": matcher(names),
            "hooks": [{"type": "command", "command": py,
                       "args": [script, "post-tool-use"], "timeout": 30,
                       "statusMessage": "vantiq-harness: reading back the VIA write"}]})
        hooks["Stop"].append({
            "hooks": [{"type": "command", "command": py,
                       "args": [script, "stop"], "timeout": 120,
                       "statusMessage": "vantiq-harness: checking this session's VIA "
                                        "writes compile"}]})

    hooks = dict((k, v) for k, v in hooks.items() if v)
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(settings, indent=2) + "\n")

    if os.path.isdir(os.path.join(project, ".git")):
        ignore = os.path.join(project, ".gitignore")
        entry = ".claude/settings.local.json"
        current = io.open(ignore, encoding="utf-8").read() if os.path.exists(ignore) else ""
        if entry not in current.split("\n"):
            with io.open(ignore, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(("" if not current or current.endswith("\n") else "\n") + entry + "\n")
    return path


# ------------------------------------------------------------------ main ---

def main(argv):
    mode = argv[1] if len(argv) > 1 else ""
    handler = {"post-tool-use": post_tool_use, "stop": stop}.get(mode)
    if handler is None:
        sys.stderr.write("usage: hooks.py post-tool-use|stop  (reads the hook JSON on stdin)\n")
        return 1
    raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read()
    payload = _json(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
    if not isinstance(payload, dict):
        return 0
    try:
        code, out, err = handler(payload)
    except Exception as exc:  # a bug in a hook must never wedge a session
        err_text = "vantiq-harness hook failed and did not check anything: %s\n" % exc
        sys.stderr.buffer.write(err_text.encode("utf-8", "replace")) \
            if hasattr(sys.stderr, "buffer") else sys.stderr.write(err_text)
        return 1
    if out:
        sys.stdout.write(out)
    if err:
        if hasattr(sys.stderr, "buffer"):
            sys.stderr.buffer.write(err.encode("utf-8", "replace"))
        else:
            sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
