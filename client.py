"""A Vantiq client that refuses to mistake acknowledgement for success.

The platform's failure signature is uniform: the write returns HTTP 200 and
something is broken somewhere else, or later. Everything here exists to replace
that 200 with a real answer.

Four things this encodes that cost us time to learn:

  * An error can arrive INSIDE a success envelope, shaped like a result set.
    `[{"code": ..., "message": ...}]` is not one row. Counting it as data was
    reported as fact twice in one session, once as "1 RolePermission row" and
    once as "the type exists".

  * Document CONTENT is at /docs/<name>. /api/v1/resources/documents/<name>
    returns the metadata record, which looks plausible enough to be mistaken for
    the file.

  * A procedure's body is `script`, not `source`. Reading the wrong field
    downloaded 129 procedures and 0 characters, silently.

  * A procedure's `name` is the SHORT name; the package lives in `serviceName`.
    Filtering on `name.startswith(package)` found 1 procedure of 129.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class VantiqError(RuntimeError):
    pass


def creds_from_mcp(repo):
    """Read server and token from the repo's .mcp.json.

    Never returned in a log line or an exception message. Keeping the credential
    here rather than in tooling is what lets every script in this harness work
    on any project without hardcoding a namespace.

    The server entry is usually keyed "vantiq", but that is a convention, not a
    rule, so any entry whose URL points at a Vantiq host will do. Assuming the
    key gives a KeyError that reads as "the harness is broken" when the real
    answer is "your server is called something else".
    """
    path = os.path.join(repo, ".mcp.json")
    if not os.path.exists(path):
        raise VantiqError("no .mcp.json in %s" % repo)
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    servers = cfg.get("mcpServers") or {}
    entry = servers.get("vantiq")
    if entry is None:
        for name, candidate in servers.items():
            if "vantiq" in (candidate.get("url") or "").lower() or "vantiq" in name.lower():
                entry = candidate
                break
    if entry is None:
        raise VantiqError("no Vantiq server in %s (found: %s)"
                          % (path, ", ".join(servers) or "nothing"))
    auth = (entry.get("headers") or {}).get("Authorization")
    if not auth:
        raise VantiqError("the Vantiq entry in %s carries no Authorization header"
                          % path)
    token = auth.split(None, 1)[-1].strip()
    parts = urllib.parse.urlsplit(entry.get("url") or "")
    if not parts.scheme:
        raise VantiqError("the Vantiq entry in %s has no usable url" % path)
    return "%s://%s" % (parts.scheme, parts.netloc), token


def looks_like_error(body):
    """True when a 200 body is actually an error.

    Vantiq returns errors as a LIST of {code, message} objects, which has the
    same shape as a result set of one row. Anything that treats a response as
    data without this check will eventually count an error as a record.
    """
    if isinstance(body, dict):
        return "code" in body and "message" in body
    if isinstance(body, list) and len(body) >= 1 and isinstance(body[0], dict):
        return "code" in body[0] and "message" in body[0]
    return False


def is_not_found(status, body):
    """Missing resources answer 400 with a code, not 404.

    NR-33, verified live on 1.44.1 against `GET .../mcpservers/<missing>` and
    `.../documents/<missing>/content`: "Not-found is HTTP 400, not 404, with
    code `io.vantiq.resource.not.found` - the script checks the error code, not
    the status." A `status == 404` branch never runs, so "does it exist?" comes
    out as "it exists", or as an unhandled error.
    """
    if status == 404:
        return True
    rows = body if isinstance(body, list) else [body]
    return any(isinstance(r, dict) and r.get("code") == "io.vantiq.resource.not.found"
               for r in rows)


# Fields the server owns. Echoing them back on a PUT is rejected, and the
# rejection names Mongo rather than the field you added.
#
# NR-36, cost hours, hit three times before the pattern was recognised and then
# again months later by a migration script doing a full-record PUT:
#
#     WriteError{code=66, message='Performing an update on the path '_id' would
#     modify the immutable field '_id''}
#
# `_id` is the one Mongo refuses outright. The rest are audit fields and
# compiler OUTPUT - echoing a stale `vailErrors` or `currentState` back at the
# platform is at best meaningless and at worst overwrites what it just computed.
SERVER_MANAGED = (
    "_id",
    "ars_version", "ars_createdAt", "ars_createdBy", "ars_modifiedAt",
    "ars_modifiedBy", "ars_namespace", "ars_relationships",
    "compilerOCC", "currentState", "resourceBinding", "vailErrors",
)


def strip_server_fields(record):
    """A copy of `record` safe to PUT back. See SERVER_MANAGED.

    The GET-change-one-field-PUT round trip is the single most common way to
    edit a Vantiq resource, and it does not work on the record you were given.
    """
    return dict((k, v) for k, v in record.items() if k not in SERVER_MANAGED)


# Resource paths that look right and are not. Checked on every call, because
# each of these returns something plausible rather than an obvious refusal.
def _path_trap(path, method="GET"):
    """The reason `path` is wrong, or None."""
    p = path.strip("/").split("?")[0]
    head = p.split("/")[0]
    # NR-30. The namespace listing labels these under `system`, so writing the
    # prefix is the obvious move; the server adds its own and the error names a
    # resource nobody asked for:
    #   "The resource system.system.genaiflows is not recognized as a Vantiq
    #    system resource" (HTTP 500)
    #   "The resource system.system.secrets is not recognized ... Either correct
    #    resource name or adjust access URI/prefix."
    if head.startswith("system."):
        return ("system resource paths take no `system.` prefix; the server adds "
                "it and reports `system.%s`. Use `%s`." % (head, head[7:]))
    # DM-16. `types/<T>` is the type DEFINITION resource. Instances of a custom
    # type live at `custom/<T>`, and the wrong one 400s.
    #
    # Only on a WRITE. `GET types/<T>` reads the definition and is exactly right;
    # trapping that broke reading a schema, which is a thing this harness does.
    parts = p.split("/")
    if (method in ("POST", "PUT", "PATCH", "DELETE")
            and len(parts) >= 2 and parts[0] == "types" and parts[1] not in ("", "@")):
        return ("`types/%s` is the type DEFINITION; instances of a custom type "
                "insert and update at `custom/%s`." % (parts[1], parts[1]))
    # NR-35, and already encoded in Client.document(). The documented content
    # sub-resource 400s with io.vantiq.resource.not.found even for a document
    # that exists, on 1.44.1.
    if parts[0] == "documents" and parts[-1] == "content":
        return ("`documents/<name>/content` 400s even for a document that "
                "exists; the served bytes are at `<server>/docs/<name>`.")
    return None


def _modal(values):
    """The most common non-empty value, or None.

    Used to infer the owning namespace from a listing without spending a round
    trip, on the reasoning that your own package's procedures are overwhelmingly
    yours and the inherited ones are the minority. When that is not true - a
    package with more inherited procedures than its own - this infers the wrong
    one, so `Client.namespace()` is the answer that is actually read back from
    the server, and it wins when it has been called.
    """
    counts = {}
    for v in values:
        if v:
            counts[v] = counts.get(v, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def error_text(body):
    rows = body if isinstance(body, list) else [body]
    return "; ".join("%s: %s" % (r.get("code"), r.get("message"))
                     for r in rows if isinstance(r, dict))


class Client(object):
    def __init__(self, repo=None, server=None, token=None, timeout=180):
        if token is None:
            server, token = creds_from_mcp(repo)
        self.server, self._token, self.timeout = server, token, timeout
        self._namespace = None

    # ---------------------------------------------------------------- raw ---
    def raw(self, method, path, body=None, query=None, api=True):
        if api:
            trap = _path_trap(path, method)
            if trap:
                raise VantiqError("%s %s: %s" % (method, path, trap))
        url = self.server + ("/api/v1/resources/" if api else "/") + path.lstrip("/")
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self._token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw.strip():
                    return resp.status, None
                try:
                    return resp.status, json.loads(raw)
                except ValueError:
                    return resp.status, raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, raw
        except urllib.error.URLError as exc:
            # A timeout usually means the write LANDED. The caller must re-read
            # before retrying, or it will double-apply.
            return 0, str(exc)

    def call(self, method, path, body=None, query=None, api=True):
        """raw(), with an error inside a 200 raised rather than returned."""
        status, body_out = self.raw(method, path, body, query, api)
        if status == 200 and looks_like_error(body_out):
            raise VantiqError("%s %s -> 200 carrying an error: %s"
                              % (method, path, error_text(body_out)))
        return status, body_out

    # -------------------------------------------------------------- reads ---
    def select(self, resource, where=None, props=None, limit=None):
        q = {}
        if where:
            q["where"] = json.dumps(where)
        if props:
            q["props"] = json.dumps(props)
        if limit:
            q["limit"] = limit
        status, body = self.call("GET", resource, query=q or None)
        if status != 200:
            raise VantiqError("select %s -> %s: %s" % (resource, status,
                                                       json.dumps(body)[:300]))
        return body if isinstance(body, list) else []

    def execute(self, fqn, params=None):
        status, body = self.call("POST", "procedures/" + fqn, params or {})
        if status != 200:
            raise VantiqError("%s -> %s: %s" % (fqn, status, json.dumps(body)[:600]))
        return body

    def document(self, name):
        """The SERVED bytes. Note /docs/, not the resources path."""
        status, body = self.raw("GET", "docs/" + name.lstrip("/"), api=False)
        if status != 200:
            raise VantiqError("document %s -> %s" % (name, status))
        return body if isinstance(body, str) else json.dumps(body)

    def procedures(self, package, hand_written_only=True):
        """Every procedure in a package, with its body.

        `name` is the short name and the package is in `serviceName`, so the
        filter is on serviceName. Getting that wrong finds almost nothing and
        reports it as a clean sweep.

        `ars_createdBy == "system"` marks procedures the PLATFORM generated:
        collaboration machinery, A2A dispatch, activity-pattern handlers. In one
        project 451 of 527 procedures were system-generated. Linting them is
        pure noise, because nobody wrote them and nobody can edit them, and it
        was 22 of the first 46 findings against unseen namespaces.

        `ars_namespace` is the second filter and it matters more for WRITES than
        for reads. NR-48: this listing returns system-owned and INHERITED
        records alongside your own, and a sweep that re-POSTed everything it
        returned - to force a recompile after a platform upgrade - materialised
        a local copy of every one. The count afterwards was 522 new procedures
        plus 5 rules, under services the project had never defined
        (ActivityPattern 65, Broker 61, Deployment 64, Test 35, Utils 21).
        Cleanup deleted 437 of them, each checked against a surviving original
        first.

        Nothing here re-POSTs anything. The filter is applied so that a caller
        who feeds this list into a write loop is not handed the inherited rows
        in the first place.
        """
        rows = self.select("procedures", limit=2000,
                           props=["name", "serviceName", "isPrivate",
                                  "ars_createdBy", "ars_namespace"])
        ours = [r for r in rows if (r.get("serviceName") or "").startswith(package)]
        if hand_written_only:
            ours = [r for r in ours if r.get("ars_createdBy") != "system"]
        mine = self._namespace or _modal(r.get("ars_namespace") for r in ours)
        if mine:
            ours = [r for r in ours
                    if (r.get("ars_namespace") or mine) == mine]
        out = {}
        for r in ours:
            fqn = r["serviceName"] + "." + r["name"]
            status, body = self.call("GET", "procedures/" + urllib.parse.quote(fqn))
            if status == 200 and isinstance(body, dict):
                # `script`, not `source`. The wrong field returns empty strings
                # for every procedure and no error at all.
                out[fqn] = body.get("script") or ""
        return out

    def namespace(self):
        """The namespace this TOKEN authenticates to, read off a real record.

        Two entries, from two teams, and the same failure both times: the
        namespace you believe you are in is not a property of anything you
        configured.

          DM-21: "REST installs land in whatever namespace the auth token
          belongs to, with no failure signal - a day's procedures silently went
          into the wrong namespace."

          NR-51: a CLI profile's `namespace =` line disagreed with its token
          after the profile was repurposed. A throwaway secret created through
          it came back `"ars_namespace":"<other namespace>"`. "Token namespace
          wins over the profile field."

        So this reads `ars_namespace` back from the server rather than trusting
        any local configuration - which is the only way either team found out.
        The types listing is used because every namespace has some and the field
        is on every record.
        """
        if self._namespace is None:
            rows = self.select("types", limit=1, props=["ars_namespace"])
            if not rows or not rows[0].get("ars_namespace"):
                raise VantiqError(
                    "cannot determine the token's namespace; refusing to guess. "
                    "Check it by hand before writing anything.")
            self._namespace = rows[0]["ars_namespace"]
        return self._namespace

    def assert_namespace(self, expected):
        """Refuse to continue unless the token authenticates to `expected`.

        Call this before any write session. It is one round trip against a day
        of procedures written into someone else's namespace.
        """
        actual = self.namespace()
        if actual != expected:
            raise VantiqError(
                "this token authenticates to namespace `%s`, not `%s`. The token "
                "decides where writes land; nothing else does." % (actual, expected))
        return actual

    # ------------------------------------------------------------- writes ---
    def put(self, resource, name, record):
        """PUT a record the server gave you, with its own fields stripped.

        NR-36. `GET`, change one field, `PUT` it back is the obvious edit and it
        is rejected on `_id`. See SERVER_MANAGED for the full list and the
        WriteError it produces.

        For `genaiflows` and `collaborationtypes` this is also the call that
        COMPILES the resource: NR-31 found POST stores the body and leaves
        `ars_version: 1` with `currentState: unbound`, and a PUT of the identical
        body takes it to `ars_version: 2` and compiles it. Two independent
        sessions. So a POST alone is never finished for those two.
        """
        return self.call("PUT", "%s/%s" % (resource, urllib.parse.quote(name)),
                         strip_server_fields(record))

    def upsert(self, resource, definition, key="name"):
        """Write, then PROVE it by reading the row back.

        Identity is (serviceName, name) where a serviceName exists. Keying on the
        short name alone collapses six services' `ping` into one, which reports
        five silent failures on a clean push and would hide a real one.
        """
        status, body = self.raw("POST", resource, definition)
        if status not in (200, 201) and status not in (0, 504):
            raise VantiqError("%s %s -> %s: %s"
                              % (resource, definition.get(key), status,
                                 json.dumps(body)[:400]))
        where = {key: definition.get(key)}
        if definition.get("serviceName"):
            where["serviceName"] = definition["serviceName"]
        rows = self.select(resource, where=where, props=[key, "ars_version"])
        if not rows:
            raise VantiqError("%s %s: wrote with status %s and the row is not there"
                              % (resource, definition.get(key), status))
        return rows[0]

    # ------------------------------------------------------------- health ---
    def vail_errors(self, package):
        """Every compile error in the package, at BOTH levels.

        A procedure carries its own vailErrors and the parent service does not
        aggregate them, so a procedure can fail to parse while its service reads
        perfectly clean. The reverse also happens and is worse: adding a
        parameter to a procedure on a service that declares an explicit interface
        leaves the PROCEDURE clean and puts the error on the SERVICE, where
        nothing that only checks procedures will ever see it, while every
        procedure in that service stops compiling.
        """
        out = {}
        for r in self.select("procedures", limit=2000,
                             props=["name", "serviceName", "vailErrors"]):
            if not (r.get("serviceName") or "").startswith(package):
                continue
            if r.get("vailErrors"):
                out["procedure/%s.%s" % (r["serviceName"].split(".")[-1], r["name"])] = \
                    r["vailErrors"]
        for res in ("services", "collaborationtypes", "rules"):
            for r in self.select(res, limit=500, props=["name", "vailErrors"]):
                if not (r.get("name") or "").startswith(package):
                    continue
                if r.get("vailErrors"):
                    out["%s/%s" % (res, r["name"])] = r["vailErrors"]
        return out

    def snapshot(self, package, resources=None):
        """{resource/name: ars_version} for everything in the package.

        Taken before and after a change, the difference is the honest answer to
        "what did that just do". Used to prove a guide rebuild touched two
        documents and nothing else.
        """
        resources = resources or ("procedures", "services", "types", "documents",
                                  "rules", "sources", "topics", "collaborationtypes",
                                  "projects", "semanticindexes", "llms")
        out = {}
        for res in resources:
            try:
                rows = self.select(res, limit=2000,
                                   props=["name", "serviceName", "ars_version"])
            except VantiqError:
                continue
            for r in rows:
                full = r.get("serviceName")
                name = (full + "." + r["name"]) if full else r.get("name", "")
                if name.startswith(package):
                    out["%s/%s" % (res, name)] = r.get("ars_version")
        return out


def diff_snapshot(before, after):
    """(added, removed, changed) between two snapshots."""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return added, removed, changed
