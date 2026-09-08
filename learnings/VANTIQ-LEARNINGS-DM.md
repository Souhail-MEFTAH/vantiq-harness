> **Redacted for public release.** This file was written for internal pooling
> and is published with customer, namespace and deployment identifiers removed.
> Angle-bracket placeholders (`<pkg>`, `<ns>`, `<namespace>`, `<deployment>`,
> `<installation>`, `<backend repo>`) stand in for names that were here. Vantiq
> platform error codes and `dev.vantiq.com` are kept verbatim, because they are
> what you would search for.

# VAIL

### The source name in `SELECT ... FROM SOURCE` is a compile-time literal; a variable compiles as a source named by the identifier

- **id**: DM-01
- **area**: VAIL
- **status**: verified
- **cost**: minutes (a deliberate probe; it settled a whole design question)
- **symptom**: `var s = srcName; SELECT ONE FROM SOURCE s ...` behaves as a lookup of a source literally named `s`, not the value of the variable.
- **cause**: The source binding is resolved statically at compile time; VAIL does not evaluate the token as an expression.
- **fix**: One procedure per source binding; share everything else (identity rules etc.) in a common procedure the entry points call. An environment cannot be selected dynamically in VAIL at all.
- **evidence**: Probe procedure `zzTmpDynamicSourceProbe(srcName String)` with `SELECT ONE FROM SOURCE s`; result: "Confirmed: the source name in `SELECT ... FROM SOURCE` is a compile-time literal - VAIL resolved the variable `s` as a source *named* `s`." Recorded in the shipped procedure comment: "probed 2026-08-21: a variable `s` compiled to a search for a source *named* `s`".
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21; repo scripts/pythonConnector/KNOWLEDGE.md

### A VAIL `SELECT count = count()` returns a one-row list, never a bare integer

- **id**: DM-02
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: `var cnt = select count=count() FROM ...` assigned straight to a state variable stores a list, not a number.
- **cause**: A VAIL SELECT always yields a list of rows, even for an aggregate - the result is `[{ count: 42 }]`.
- **fix**: Extract the scalar: `stateVar = rows[0].count`. Held on both platform versions in play.
- **evidence**: "a VAIL `SELECT` always yields a **list of rows**, even for an aggregate. So `var cnt = select ...` makes `cnt` a one-element list like `[{ count: 42 }]`. Assigning that straight into [the state variable] would store the list, not the number." Final accepted code: `Bogus = rows[0].count`.
- **source**: claudelogs/20260721_142353_*.md, 2026-07-21

### VAIL's lambda operator is `=>`, not `->`

- **id**: DM-03
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: A lambda written Java-style with `->` is a syntax error at the arrow, and it is easy to misattribute to a platform version difference.
- **cause**: VAIL defines the lambda operator as `=>`; `->` never compiles on any version.
- **fix**: `(prev) => { return cnt }` - block body with an explicit `return`, per the canonical examples.
- **evidence**: User: "`Bogus.updateAndGet(prev -> cnt)` that gives a syntax error on ->, probably because we're on a different version of Vantiq." Assistant, after checking the operators reference: "this isn't a version difference. VAIL's lambda operator is `=>`, not `->`."
- **source**: claudelogs/20260721_142353_*.md, 2026-07-21

### VAIL `exception()` messages are Java MessageFormat; a bare `{}` placeholder raises "can't parse argument number" and replaces the real error

- **id**: DM-04
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: A refusal path fires correctly, but the caller receives "can't parse argument number" instead of the intended message.
- **cause**: `exception()` message templates are Java MessageFormat - positional `{0}`, `{1}` - not Python/logback-style `{}`.
- **fix**: Use `{0}`-style placeholders in every `exception()` message.
- **evidence**: "The gate fired (nothing was created - 0 accounts), but the message is mangled: `can't parse argument number`. VAIL's `exception()` uses Java MessageFormat, so placeholders are `{0}`, not `{}`." Fix applied (`'this operation ({}).' -> 'this operation ({0}).'`) and the re-test showed a readable refusal.
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21

### `Encode.base64()` is the base64 built-in that exists; four plausible spellings fail to compile, and `Context.serverUri()` returns the internal URL

- **id**: DM-05
- **area**: VAIL
- **status**: verified
- **cost**: minutes (probed before committing to a design that depended on it)
- **symptom**: Building a Basic-auth header in VAIL, `toBase64`, `Base64.encode`, `Utils.base64Encode`, and `encodeBase64` all fail compilation.
- **cause**: The built-in is namespaced under `Encode`. Probed at the same time: `Context.serverUri()` returned `http://localhost:8080` - the server's internal address, not the public URL.
- **fix**: `Encode.base64(...)`. Treat `Context.serverUri()` as a loopback address - exactly right for a REMOTE source hitting `{serverUri}/authenticate`, wrong for anything a browser must reach.
- **evidence**: "Two probes settled the design rather than guessing: `Context.serverUri()` -> `http://localhost:8080`, and `Encode.base64` is the primitive that exists (`toBase64`, `Base64.encode`, `Utils.base64Encode`, `encodeBase64` all fail to compile)."
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21

### Creating a procedure over REST succeeds at the HTTP level even when it does not compile; the errors ride in `vailErrors`

- **id**: DM-06
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: POST of a `.vail` file to `/api/v1/resources/procedures` reports success, but the procedure carries a compile error - here, `stateless` on a bare package procedure (it is only legal on service procedures).
- **cause**: Compile errors do not fail the create/update call; they are stored on the resource and returned in the response body's `vailErrors` array. A script that only checks the HTTP code believes the install worked.
- **fix**: Always parse `vailErrors` out of the create/update response (and off the resource later), not just the status code. Drop `stateless` on non-service procedures.
- **evidence**: Failing code: `stateless PROCEDURE connectorDevTest(payload Object ...)` - created successfully, then: "Created, but with a compile error: `stateless` is only legal on service procedures. Dropping it." Fixed code identical minus the modifier; "Compiles clean." Every subsequent install script in the session parses `d.get('vailErrors')` from a 200 response.
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21

### "VAIL does not guarantee short-circuit evaluation of `||`" - asserted in shipped code, never watched to fail

- **id**: DM-07
- **area**: VAIL
- **status**: unverified
- **cost**: n/a (defensive style only)
- **symptom**: None observed; no failure ever demonstrated it.
- **cause**: The claim exists only as a code comment justifying nested `if`s ("Nested rather than || -- VAIL does not guarantee short-circuit evaluation."), copied faithfully into three shipped procedures. No probe tested it and no documentation citation was ever produced.
- **fix**: If it matters, probe it (`null.trim()` behind a `||` guard) before either relying on short-circuiting or perpetuating the nested-if style as fact.
- **evidence**: Comment text only; no transcript moment shows `||` failing. Flagged here so someone can verify or kill it.
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21

# service interface

### With `hasExplicitInterface: true` the interface is a compiled contract that does not sync with the procedures in either direction - a mismatch breaks the whole service while every procedure reports clean

- **id**: DM-08
- **area**: service interface
- **status**: verified
- **cost**: hours (multiple bites across three sessions)
- **symptom**: (a) Procedures added to a service exist and run, but the declared interface stays frozen, so generated clients do not expose them; (b) a service carried an operation with no implementing procedure and a `partitionedType` naming a nonexistent type, both standing errors; (c) adding one more procedure produced a service-level compile error - every individual procedure listed ok, but the entire service refused to run.
- **cause**: The `interface` array is stored on the service resource and compiled as a contract; nothing derives it from the procedures or vice versa. An undeclared procedure, or a declared return type disagreeing with the implementation (`Object` declared, `Boolean` returned), fails the whole service, not the one operation.
- **fix**: When adding a procedure to such a service, update the service's `interface` array in the same operation, with explicit correct return types; check service-level `vailErrors`, not per-procedure state.
- **evidence**: Live errors off a service: `io.vantiq.service.operations.implementation.missing` and `io.vantiq.service.partitionedType.not.found`. Commit record: "Two mismatches - an undeclared changeOwnPassword, and requirePrivilege declared Object when it returns Boolean - broke the entire service, not merely the offending operation, while every individual procedure still reported clean." Earlier session: "the service interface updated (it errored until I added the interface entry)."
- **source**: claudelogs/20260721_142353_*.md, 2026-07-21; claudelogs/20260810_122113_*.md, 2026-08-10; claudelogs/20260821_092650_*.md, 2026-08-21

### `Context` propagates unchanged into a called service procedure

- **id**: DM-09
- **area**: service interface
- **status**: verified
- **cost**: minutes (deliberate probe; it enabled a single shared identity procedure)
- **symptom**: Design question probed before relying on it: does an inner service procedure see the caller's identity or its own?
- **cause**: The platform carries the calling Context through intra-service procedure calls.
- **fix**: Safe to centralize identity rules in one procedure called by every entry point. If this ever stops holding, the fix is NOT to pass the username as a parameter - that hands the caller control of who they are.
- **evidence**: Probe pair `zzCtxOuter` calling `zzCtxInner`, both returning `Context.preferredUsername()` / `Context.username()`; result: "`Context` propagates intact into a called service procedure - `<user>` in both." Shipped comment: "Context propagates into a called service procedure unchanged - verified 2026-08-21."
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21

### Service state variables on the deployed instance are plain typed properties set by direct assignment; the `Concurrent.Value`/`updateAndGet` API in the MCP server's own docs does not exist there

- **id**: DM-10
- **area**: service interface
- **status**: verified
- **cost**: minutes (bounded only because the failure was immediate)
- **symptom**: Following the MCP server's service-state context docs produced `stateVar.updateAndGet((prev) => {...})`, which the target instance rejected: the method could not be found.
- **cause**: The MCP server is pre-release and its context docs describe a newer Vantiq runtime than the instance being edited. On the actual instance, state vars are plain typed properties.
- **fix**: Default to simple assignment (`stateVar = value`) unless the instance's version is confirmed to support the `Concurrent.*` atomics. Trade-off: plain scalar state is not replicated and resets on failover.
- **evidence**: User: "updateAndGet could not be found. elsewhere it's just simple assignment." Fix: "On your instance, service state variables are plain typed properties you set with direct assignment ... So it's just: `Bogus = rows[0].count`".
- **source**: claudelogs/20260721_142353_*.md, 2026-07-21

### A scheduled (timed-event) procedure that throws does nothing, silently - and uninitialized service state is the usual trigger

- **id**: DM-11
- **area**: service interface
- **status**: verified
- **cost**: hours
- **symptom**: A 5-minute timed event stops doing its work with no visible error; the observed trigger is a service state variable "shifting to not initialized".
- **cause**: Scheduled procedures run with no caller, so an unhandled exception goes only to `system.errors` and the tick is a no-op. The causal chain (non-replicated property types revert to `null`/`0`/`{}` on node failover, restart, or rebalance; the next tick dereferences null and dies quietly) comes from the platform's service-state contract docs, not a live reproduction - the silent-drop symptom itself is the user's direct production report.
- **fix**: Initialize state via `initializeGlobalState`/`initializePartitionedState`; null-guard reads in the handler; wrap the handler body in try/catch and log, so a drop becomes a visible failure.
- **evidence**: User: "how do I keep a timed event from silently dropping when a state variable shifts to not initialized? services can have state variables, as in [the API service] and also in TimedEvents service."
- **source**: claudelogs/20260721_142353_*.md, 2026-07-21

### presetValues are delivered by text substitution into the script, so a preset key that is also an ordinary identifier gets replaced where it should not

- **id**: DM-57
- **area**: service interface
- **status**: verified
- **cost**: hours (working scripts broke after a rename; the functional versions had to be dug out of git and the naming convention reworked across every script)
- **symptom**: Connector scripts that worked before a refactor renamed input globals to camelCase broke afterward, with no code-logic change involved.
- **cause**: presetValues reach the script as textual substitution before execution; the replacement process cannot distinguish the intended placeholder from other uses of the same token, so a short or common preset key (e.g. `line`) is replaced everywhere it appears.
- **fix**: Preset key = the distinctive snake_case name the Python reads (`globals().get('annotation_data')`), value = the camelCase VAIL variable: `presetValues = { annotation_data: annotationData }`. Never use short or common words as preset keys.
- **evidence**: User: "it's that there are snake_case variables throughout, and then they are replaced by camelCase variables by Vantiq. ... presetValues should probably be annotation_data: annotationData, assigning the replacement annotationData to the python annotation_data. The reason for this change was because of parameters like \"line\" which would be indistinguishable by the replacement process." Fix applied session-wide (`globals().get('trainingId', None)` -> `globals().get('training_id', None)`, etc.).
- **source**: claudelogs/20251219_113437_*.md, 2025-12-19

### The connector executes exactly one substituted script; it cannot open or exec a sibling document, and the execution environment is not user-controllable

- **id**: DM-58
- **area**: service interface
- **status**: verified
- **cost**: hours (a long detour building wrapper/diagnostic patterns that could never work)
- **symptom**: A diagnostic wrapper script that loaded and exec'd another connector script from disk failed with FileNotFoundError.
- **cause**: Scripts live in Vantiq Documents; at call time the one requested script is fetched, has its substitution variables filled, is written down, and is exec'd. Sibling documents are not materialized, and nothing else can be placed into that environment.
- **fix**: Every connector script must be fully self-contained (which is why the repo later adopted build-time INSERT splicing rather than imports).
- **evidence**: `io.vantiq.pyexecsource.execution.exception: Executing code raised exception: FileNotFoundError :: ... File "ModelBuilder/python/annotation_processor_diagnostic.py", line 54, in <module> FileNotFoundError: [Errno 2] No such file or directory: 'ModelBuilder/python/annotation_processor.py'`. User: "the file doesn't live on disk - it lives in a database & is grabbed by the code & shoved down to disk, with substitution variables as input variables" and "I cannot reference anything else when I'm down there ... I have no control over that environment, and cannot put scripts down there."
- **source**: claudelogs/20251211_153517_*.md, 2025-12-11

### An unhandled Python exception in a connector script surfaces on the calling VAIL procedure as HTTP 400 carrying the full Python traceback

- **id**: DM-59
- **area**: service interface
- **status**: verified
- **cost**: hours (spent on server-side log archaeology while the diagnosis sat in the procedure error the whole time)
- **symptom**: A failing connector call looks like "finished in a flash, 0 processed, no log entry"; server log files hold nothing useful.
- **cause**: The connector propagates the exception to Vantiq, which fails the executing procedure with `io.vantiq.pyexecsource.execution.exception` containing the complete traceback - the script's Document path appears as the traceback's pseudo-filename.
- **fix**: When a connector call misbehaves, get the procedure's error text from Vantiq first; it contains the exact Python exception and line number. Server-side logs are the wrong first place to look.
- **evidence**: `HTTP Status 400 () (while executing Procedure 'com.<company>.<app>.ModelBuilder.processSendToModel'): io.vantiq.pyexecsource.execution.exception: Executing code raised exception: FileNotFoundError :: Traceback (most recent call last): File "/usr/local/lib/python3.14/site-packages/pyExecConnector.py", line 660, in run_python_code exec(compiled_code, global_vars, None) ...`
- **source**: claudelogs/20251211_153517_*.md, 2025-12-11

# types and data

### `Context.username()` is not a stable identifier - it returned a UUID on one check and the login name on a token-authenticated call; the immutable anchor is `system.users._id` (24 hex chars, namespace-scoped)

- **id**: DM-12
- **area**: types and data
- **status**: verified
- **cost**: hours (a UNIQUEIDENTIFIER column and two stored-proc signatures had to change across two repos)
- **symptom**: Code treating `Context.username()` as "the username" sends a UUID where a name is expected - `SELECT ... FROM system.users WHERE username == <login name>` matches nothing, silently, presenting as "this user has no profile". Later, a column typed for "the account UUID from Context.username()" never populated, because on a token-authenticated call the same function returned the login name, byte-identical to `preferredUsername()`.
- **cause**: Two observations, both live, two weeks apart: 2026-08-06, `Context.preferredUsername()` returned the login name and `Context.username()` returned a Users-resource UUID; 2026-08-21, a token-authenticated call returned the login name from BOTH functions. Which value `username()` carries depends on how the call authenticated. The stable per-record id is `system.users._id`: 24 hex characters, assigned at creation, never reissued - and issued per namespace, so a namespace migration gives every user a new one.
- **fix**: Resolve people by `Context.preferredUsername()`; never key anything on `Context.username()`. For an immutable audit anchor, read `_id` from the `system.users` record (`SELECT ONE FROM system.users WHERE preferredUsername == ...`), type the receiving column CHAR(24), and treat a namespace migration as an anchor-rebinding step.
- **evidence**: 2026-08-06: "`Context.preferredUsername()`, the login name ... NOT `Context.username()`, which under this identity provider returns the Users-resource UUID ... Verified against the live tenant." 2026-08-21 probe output: `ctx_username "<user>" <- useless: same as the login name` / `rec_id "6914dfcdead63c5bace5f10b" <- immutable per-record id`. Shipped comment: "Context.username() returns the LOGIN NAME, byte-identical to preferredUsername (observed 2026-08-21) ... An anchor equal to the key is not an anchor."
- **source**: claudelogs/20260806_130030_*.md, 2026-08-06; claudelogs/20260821_092650_*.md, 2026-08-21

### `system.users` has no active/enabled field - a Vantiq account cannot be deactivated from VAIL at all

- **id**: DM-13
- **area**: types and data
- **status**: verified
- **cost**: minutes (probe; it decided where deactivation had to live)
- **symptom**: Designing user deactivation, there is nothing on the platform user record to flip.
- **cause**: The user record simply carries no such field.
- **fix**: Deactivate in the application's own store and refuse there; the person may keep a Vantiq login and still be refused by the application.
- **evidence**: Commit record: "Deactivation turned out to be catalog-side, and not by preference: system.users has no active or enabled field at all ... There is nothing for VAIL to do."
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21

### The Python Connector wraps every script result in `pythonCallResults`; a procedure returning the raw SOURCE response hands its caller nulls

- **id**: DM-14
- **area**: types and data
- **status**: verified
- **cost**: a day or more
- **symptom**: The Python script's logs show `result` fully populated, but the calling VAIL fails with a runtime exception on a null object; hours went into rewriting the (already-correct) Python.
- **cause**: The connector delivers all JSON-encodable script globals inside a `pythonCallResults` object. A procedure doing `var result = SELECT one FROM SOURCE ... / return result` returns the wrapper, so every property access downstream resolves against the wrong level.
- **fix**: Unwrap in the procedure that touches the source: `return result.pythonCallResults.result` (likewise `.success` / `.error`).
- **evidence**: `HTTP Status 400 () (while executing Procedure '...sendAnnotations'): io.vantiq.runtime.exception: Encountered exception during execution: Cannot get property 'Result' on null object` - fixed by the one-line change `return result` -> `return result.pythonCallResults.result` (user: "yes! awesome!").
- **source**: claudelogs/20251219_091040_*.md, 2025-12-19

### The connector JSON-encodes every script global on completion and silently skips the unencodable ones at DEBUG level

- **id**: DM-15
- **area**: types and data
- **status**: verified
- **cost**: hours (mid-session these skips were blamed for a null return they did not cause - see DM-14)
- **symptom**: Connector DEBUG logs show one "Could not encode ... Skipping it." line per module/class/instance left in `globals()` at script end.
- **cause**: On completion the connector serializes the whole global namespace into `pythonCallResults`; anything not JSON-serializable is dropped with a DEBUG line, not an error. A misdirected mass-delete of globals also deleted the connector's own `connector_connection`/`connector_context` variables.
- **fix**: Keep the global namespace clean by design (initialize `result`/`success`/`error` at top, put logic in functions) rather than mass-deleting globals at the end; never delete connector-owned globals.
- **evidence**: `2025-12-19 02:35:04,141 - DEBUG - Could not encode global os to JSON.  Skipping it.` ... `Could not encode global processor to JSON.  Skipping it.` - and after cleanup only `__builtins__` and `logger` skipped, while the null persisted (its real cause was DM-14).
- **source**: claudelogs/20251219_091040_*.md, 2025-12-19

# REST and MCP

### Instances of a custom type insert at `/resources/custom/<Type>`, not `/resources/types/<Type>` - the latter is the type-definition resource and 400s

- **id**: DM-16
- **area**: REST and MCP
- **status**: verified
- **cost**: hours
- **symptom**: POSTing a record to `/api/v1/resources/types/<Type>` with a valid token returns HTTP 400; the identical payload to `/resources/custom/<Type>` returns HTTP 200 and stores the record.
- **cause**: `/resources/types/` addresses the type definitions (system.types metadata), which does not accept instance inserts; instances live under `custom`. The session also burned time because a wrong port answered with a FastAPI `{"detail":"Not Found"}` body mistaken for a Vantiq error - Vantiq errors always look like `[{"code":"io.vantiq...","message":...}]`, so the error-body shape tells you which server answered.
- **fix**: Insert at `/api/v1/resources/custom/<TypeName>`; expect HTTP 200 (not 201) with the stored record echoed back including `ars_namespace`, `ars_version`, `ars_createdAt`, `ars_createdBy`.
- **evidence**: `[{"code":"io.vantiq.bad.request","message":"The operation null is not supported on system.types.","params":[],"isFormatted":true}] HTTP Status: 400` - then to `/custom/`: `{"script_name":"test_curl",...,"ars_namespace":"<namespace>","ars_version":1,...,"ars_createdBy":"loggingtoken__<namespace>"} HTTP Status: 200` (user: "that went through - it's in the type!").
- **source**: claudelogs/20260128_150415_*.md, 2026-01-28

### Malformed JSON in a REST body gets a full Java stack trace back, with the exact line and column of the bad byte

- **id**: DM-17
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: A curl POST whose quoted JSON acquired literal newlines (terminal line-wrapping of a long command) returns an enormous `io.vantiq.server.error` body containing an entire vertx/Jackson stack trace.
- **cause**: The JSON decode is strict (Jackson default: unescaped control characters in strings are illegal), and the server returns the complete DecodeException in the error body.
- **fix**: Keep the `-d` payload on one physical line (or `-d @-` with a heredoc); the `column:` in the error is precise - use it.
- **evidence**: `[{"code":"io.vantiq.server.error","message":"Failed to decode:Illegal unquoted character ((CTRL-CHAR, code 10)): has to be escaped using backslash to be included in string value\n at [Source: REDACTED ... line: 1, column: 84]",...`
- **source**: claudelogs/20260128_150415_*.md, 2026-01-28

### Inserting into the procedures resource takes the VAIL under `script`, named `Service.operation`, with the package declared inside the source - not `contents` with a fully-qualified name

- **id**: DM-18
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: An insert with the code under a `contents` key and a fully-qualified dotted `name` did not take; the corrected call compiled clean.
- **cause**: The procedures resource expects the code in `script`; the package lives in the source's `package` statement, with `name` as `Service.procName`.
- **fix**: `insert system.procedures {name: "<Service>.<operation>", script: "package com.<company>.<app>\n\nSTATELESS PROCEDURE <Service>.<operation>(): Object ..."}`.
- **evidence**: Failing call: `"instance": { "name": "com.<company>.<app>.<Service>.syncCurrentUser", "contents": "..." }`; after re-reading the MCP's `procedures/context/format.txt`, the succeeding call: `"instance": { "name": "<Service>.syncCurrentUser", "script": "..." }` - "Compiled clean." (The rejection body itself was not archived; the failing/fixed call pair is verbatim.)
- **source**: claudelogs/20260810_122113_*.md, 2026-08-10

### The Python-connector SOURCE invocation key is `script` with a bare document name - not `code` with a path

- **id**: DM-19
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: A first-draft service spec wrote `code: "ForPythonConnector/runSQL.py"`; checking it against the known-good live procedure showed it wrong on both counts.
- **cause**: The connector source takes `WITH script = "<bare document name>"`; there is no directory component because the name resolves against Vantiq Documents (see DM-36), not a filesystem.
- **fix**: `SELECT ONE FROM SOURCE <ns>.PythonSource WITH script = "runSQL.py", presetValues = {...}`; unwrap exactly one layer (`.pythonCallResults.result`, DM-14).
- **evidence**: "**CORRECTED 2026-08-06** -- the first draft of this section said `code: \"ForPythonConnector/runSQL.py\"` and was wrong on both counts: The key is **`script`**, not `code`, matching the known-good [procedure]. The value is the **bare filename**, no directory."
- **source**: claudelogs/20260806_130030_*.md, 2026-08-06

### Access tokens are namespace-scoped, not source-scoped - the `sources =` line in server.config routes a connector, and the token cannot

- **id**: DM-20
- **area**: REST and MCP
- **status**: verified
- **cost**: a day or more (a dev connector failed for weeks while the routing model was believed backwards)
- **symptom**: Working premise going in: "what dictates routing is actually the token in use", making a dev source look redundant. Meanwhile the dev connector failed on a token believed valid.
- **cause**: Both sources sat in one namespace (`ars_namespace` identical on both source records), and every token in a namespace carries the same rights - a token has nothing with which to discriminate between sources. What attaches a connector to a source is exclusively the `sources =` line in its `server.config`. The actual dev failure was a dead (deleted) token; the prod token worked for the dev source too, being namespace-wide.
- **fix**: Treat the token purely as namespace authentication and the `sources =` config line as the routing mechanism. A second source exists to keep a second connector process off the first source.
- **evidence**: "**There is one namespace** ... Both [sources] sit inside it (`ars_namespace: ...` on both source records). So the token *cannot* be what routes - it has nothing to discriminate between ... What routes is the **`sources =` line in `server.config`**." And: "[the dev config] carried a 44-character token returning `401 Authentication failed` ... since tokens are namespace-scoped, the *same* token works for the dev source."
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21 (premise stated in the user's opening message of the same session)

### REST installs land in whatever namespace the auth token belongs to, with no failure signal - a day's procedures silently went into the wrong namespace

- **id**: DM-21
- **area**: REST and MCP
- **status**: verified
- **cost**: hours (four procedures reinstalled; staging litter cleaned)
- **symptom**: Procedures installed all day via one connector's token were absent from the intended new namespace; nothing errored at any point.
- **cause**: A token is a namespace credential. Everything created with it lands in its namespace, and the token cannot even see the other namespace's projects - so there is nothing to fail.
- **fix**: Before installing anything by REST, GET a resource you just created and read `ars_namespace` - do not believe an install you have not checked. Use a token minted in the target namespace.
- **evidence**: "`requirePrivilege ars_namespace: [the production namespace]` created by: `cli_token__...` / projects visible: [the production project] only ... **Your [dev project] isn't even visible to that token at all.** Everything I installed today - the four user-management procedures included - went into the namespace you're abandoning."
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21

### curl glob-expands `[` and `]`, so any Vantiq REST URL with `props=[...]` fails silently without `-g`

- **id**: DM-22
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes per bite, and it bites repeatedly
- **symptom**: A query using `props=["name"]` or `where={...}` returns nothing - an empty HTTP code, no error - and the failure looks like the API's.
- **cause**: curl's URL globbing consumes the brackets before the request is made.
- **fix**: Always pass `-g` (or percent-encode the brackets).
- **evidence**: "curl glob-expands `[` and `]`, so any Vantiq URL with `props=[...]` fails silently without `-g`; that one cost me a round." Repo note: "`curl -g` is not decoration ... fails silently without it, returning an empty HTTP code rather than an error."
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21; repo scripts/pythonConnector/KNOWLEDGE.md

### The two Vantiq MCP servers document different product generations, and neither necessarily matches the instance you are editing

- **id**: DM-23
- **area**: REST and MCP
- **status**: verified
- **cost**: hours (cumulative; it is the root cause of DM-10)
- **symptom**: The knowledge-base MCP answers only about the released browser-based product (zero coverage of the next-generation tooling); the development MCP's own bundled context docs describe a newer pre-release runtime whose APIs (`Concurrent.Value`, `updateAndGet`) do not exist on the instance being edited.
- **cause**: One server is curated from released-product docs; the other is a pre-release build whose docs run ahead of deployed servers.
- **fix**: Treat both doc sources as version-labeled. Confirm an API exists on the target instance - or mirror known-good code already in the namespace - before shipping code from either server's docs.
- **evidence**: User: "VIA is the next generation Vantiq product. All of the responses make sense in that context, and do not generally apply to the released version of Vantiq."
- **source**: claudelogs/20260708_103249_*.md, 2026-07-08; claudelogs/20260721_142353_*.md, 2026-07-21

### The MCP `whoami` puts the bearer token into the transcript, and the MCP has no from-disk document upload

- **id**: DM-24
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: Uploading a 43KB script to Documents offered only two routes: reproduce the file verbatim inline in a tool call, or REST multipart with the token on the command line - and the token-exposure worry turned out to be already moot.
- **cause**: The MCP can insert document content only inline; and `whoami`'s response already contains the token, so any session transcript that ran it holds the credential regardless.
- **fix**: For anything large, prefer REST multipart (exact bytes from disk) or IDE drag-and-drop. Treat the session transcript as containing the token from the first `whoami` on - which matters wherever transcripts are archived or pushed.
- **evidence**: "**MCP insert** - [the script] is 43KB / 1002 lines, and that route means me reproducing it verbatim in a tool call ... Worth knowing: **the token is already in the transcript** from `whoami`, so the incremental exposure is nil."
- **source**: claudelogs/20260810_122113_*.md, 2026-08-10

### `readDocument` returns document content base64-encoded

- **id**: DM-25
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: A `.py` document read back via the MCP's `readDocument` is not text.
- **cause**: The tool delivers raw content base64-encoded.
- **fix**: Base64-decode before diffing against source.
- **evidence**: "Base64. Decoding and diffing against `built/`" - followed by the working `base64.b64decode` step and a successful diff.
- **source**: claudelogs/20260814_092319_*.md, 2026-08-14

# ops and cost

### Executing a procedure against an extension source with no connector attached fails with "not recognized as an open EXTENSION session"

- **id**: DM-26
- **area**: ops and cost
- **status**: verified
- **cost**: minutes
- **symptom**: A freshly created, cleanly compiling service procedure fails at execution even though the source resource exists and the VAIL is correct; the error reads like an auth or session problem.
- **cause**: An extension source is just a resource declaration; until a connector opens an extension session against the namespace, any invocation dies at the source boundary. The error names the missing session, not the missing connector.
- **fix**: Read it as wiring status, not a bug - it proves compile, identity, and dispatch all worked. Attach the connector, retest.
- **evidence**: "executing `syncCurrentUser` in the sandbox reached `PythonSource` and failed with *\"not recognized as an open EXTENSION session\"*. VAIL compiles, identity resolves, dispatch works. Only the connector is missing."
- **source**: claudelogs/20260810_122113_*.md, 2026-08-10

### A connector that fails authentication logs nothing but a repeating "is connecting" line - diagnose by cadence, not content

- **id**: DM-27
- **area**: ops and cost
- **status**: verified
- **cost**: hours
- **symptom**: The container looks healthy; Vantiq says the source is not active; docker logs contain no auth error at all - only the same connect line every ~45 seconds.
- **cause**: The websocket handshake rejection is not surfaced in the connector's log. Success looks like the same line printed once followed by silence (it sits waiting on the websocket).
- **fix**: One "is connecting" line then silence = connected; the line repeating every ~45s = auth/registration failing. Test the token out-of-band: `curl -H "Authorization: Bearer <token>" https://<server>/api/v1/resources/sources`.
- **evidence**: `Connector for source pythonSource is connecting to Vantiq at: wss://<server>/api/v1/wsock/websocket` [45 seconds later, identical line]. Source-side: `io.vantiq.sourcemgr.source.not.active: The source <namespace>:pythonSource is not currently active.`
- **source**: claudelogs/20251205_140015_*.md, 2025-12-05

### Deleting a token does not disturb an already-connected connector - and a dead token produces a container that starts cleanly, logging the same line as a healthy one

- **id**: DM-28
- **area**: ops and cost
- **status**: verified
- **cost**: hours (both connectors were discovered one reconnect away from an outage)
- **symptom**: Tokens rotated in Vantiq; both containers keep serving normally - on tokens that no longer exist.
- **cause**: The websocket predates the deletion, and authorization is not re-evaluated until the next reconnect.
- **fix**: After any token change, verify by asking Vantiq (curl the baked token; `GET /api/v1/resources/tokens`) - never by watching the connector log or by "it still works".
- **evidence**: "Both containers are alive only because their websockets predate the token deletion." Repo note: "a dead token produces a container that starts cleanly and logs `is connecting to Vantiq at: wss://...` exactly like a healthy one."
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21; repo scripts/pythonConnector/KNOWLEDGE.md

### A connector with a bad credential crash-loops forever, silently - it does not park, back off, or alert

- **id**: DM-29
- **area**: ops and cost
- **status**: verified
- **cost**: hours (and an unknown period of dev-path outage before discovery)
- **symptom**: A connector instance had racked up 914 restarts and nothing surfaced it; the instance a whole work track targeted was a wall waiting for whoever picked the track up.
- **cause**: On an authentication failure this connector version exits and Docker restarts it, indefinitely; an instance no deploy tooling touches has no other observer. (Note the two observed failure modes: this fatal-exit crash loop, and DM-27's silent in-process retry - both exist.)
- **fix**: Health-check connector containers by restart count/status; an expiring credential in `serverConfig/server.config` produces a loop, not a message to anyone.
- **evidence**: "`vantiq-python-connector-dev` is in a crash loop - 914 restarts. `VantiqConnectorConfigException: Connect call failed: 400 :: io.vantiq.authentication.failed: Failed to authenticate supplied credentials.`"
- **source**: claudelogs/20260806_130030_*.md, 2026-08-06

### A stale connector session can block the new one from claiming the source - CONNECT_EXTENSION deactivation timeouts against a phantom cluster member

- **id**: DM-30
- **area**: ops and cost
- **status**: verified
- **cost**: hours
- **symptom**: After restarting the connector with a fresh token, Vantiq pops repeated timeout errors trying to activate the source - while the connector may in fact be connected (disconnect notices appeared when Docker was later stopped), so the error state is ambiguous.
- **cause**: The cluster still holds the previous connector session as owner of the source; the new CONNECT_EXTENSION triggers a Deactivation against the phantom member, which times out.
- **fix**: Stop the connector first, deactivate (or delete and recreate) the source, wait ~30s for cluster state to clear, generate a fresh token, then start the connector - and verify by behaviour (a test query, or the disconnect popup on stop), not by the presence of the timeout error alone.
- **evidence**: `The CONNECT_EXTENSION operation on data source <namespace>:pythonSource did not complete successfully: The Deactivation operation to claim ownership on member 9491b244-... failed for source <namespace>:pythonSource: Timed out waiting for reply from io.vantiq.consumer.monitored.cluster...`
- **source**: claudelogs/20251205_140015_*.md, 2025-12-05

### The connector's server.config is baked into the image by COPY - editing it and restarting changes nothing; even `--build` can serve a cached COPY layer

- **id**: DM-31
- **area**: ops and cost
- **status**: verified
- **cost**: hours (multiple crash-loop rounds; re-bitten seven weeks later)
- **symptom**: Token corrected on disk, container restarted, identical failure continues: `Connect call failed: 400 :: io.vantiq.authentication.failed`.
- **cause**: The stock Dockerfile does `COPY serverConfig/logger.ini serverConfig/server.config ./` - config lives in the image, not a mount. `docker-compose restart` reuses the old image; a rebuild can serve a CACHED copy layer.
- **fix**: `docker-compose up -d --build` (with `--no-cache` if the COPY step reports CACHED), then verify what the running image holds: `docker exec <container> grep -i '^authToken' server.config` against the on-disk file.
- **evidence**: "`server.config` is baked into the image at build time (the `COPY serverConfig/... ./` step), so a plain `restart` keeps the old token"; the same 400 recurred after a rebuild - "the rebuild didn't pick up your edit (Docker cached the `COPY` ...) -> `docker-compose build --no-cache`".
- **source**: claudelogs/20260701_083008_*.md, 2026-07-01; claudelogs/20260821_092650_*.md, 2026-08-21

### The Python connector leaks memory - a known Vantiq product defect; bouncing the container does not reclaim it

- **id**: DM-32
- **area**: ops and cost
- **status**: verified
- **cost**: a day or more (diagnosis), plus a standing weekly server reboot as the workaround
- **symptom**: Host memory exhaustion on the server running the connector; restarting the container does not recover the memory.
- **cause**: The connector itself leaks; diagnosed on our deployment and acknowledged as a known problem with the product.
- **fix**: Schedule a host-level reboot as a documented workaround, and keep long-running or memory-heavy work (image handling, frequent pumps) out of connector scripts - run those as host-resident processes instead.
- **evidence**: User, dictated for the system narrative: "Actually diagnosing the leak has been done and it was determined that the Python connector was the leak. It is a Vantiq product and is known to have this problem." Follow-on design consequence: "WHY the move: the connector leaks (same finding that bars images from it)."
- **source**: claudelogs/20260813_072859_*.md, 2026-08-13; claudelogs/20260814_061952_*.md, 2026-08-14

### Namespace invites are emailed by the installation's default EMAIL source, which you may not control - and a failed source will not retry on its own

- **id**: DM-33
- **area**: ops and cost
- **status**: verified
- **cost**: hours
- **symptom**: "Authorize User" on a namespace fails: the invite email bounces with an SMTP auth error from a source the developer never created.
- **cause**: An invite is two operations - the delegated-auth request, then a publish that emails the link via the installation-default EMAIL source (seeded at deploy time with the installer's SMTP credentials, living where a namespace developer cannot fix it). Two documented behaviours compound the trap: a rotated Secret is not picked up until the source is deactivated/reactivated, and an unhealthy source auto-retries once within 5 minutes then goes `isUnavailable: true` - so repeating the invite genuinely does nothing.
- **fix**: Create an EMAIL source in your own namespace with credentials you control, set `from` explicitly, and select it in the Invite Source dropdown instead of "Default". If you own the failing source, reactivate first - it distinguishes a stale-cached secret from a genuinely rejected credential, since there is no "validate this secret" call.
- **evidence**: `Failed to send invite with the following error: The attempt to publish email message SMTP Source 'GenericEmailSender' using server 'smtp.office365.com:587' failed with io.vertx.ext.mail.SMTPException: 'AUTH LOGIN failed: 535 5.7.139 Authentication unsuccessful, the user credentials were incorrect.' ... Email headers were: [subject:Vantiq -- Namespace Authorization, from:support@vantiq.com, ...]`
- **source**: claudelogs/20260821_114754_*.md, 2026-08-21

### Two connectors presenting the same source's credentials both attach, and Vantiq distributes calls across them - asserted, never watched

- **id**: DM-34
- **area**: ops and cost
- **status**: unverified
- **cost**: n/a (avoided by creating a second source before it could happen)
- **symptom**: Predicted hazard only: a dev connector sharing prod's source would receive a share of prod's calls non-deterministically.
- **cause**: Stated mechanism from a 2026-07-01 session: "two connectors both authenticating to [the source] ... both attach to the **same** source ... Vantiq distributes calls across them." A second source was created instead, so the split-stream behaviour was never observed. The same reply's companion claim ("each Vantiq source has its own token") was later disproven (DM-20), so treat this mechanism as unconfirmed.
- **fix**: Keep one connector per source regardless; a per-environment source is the mechanism that keeps a second connector process off production's source.
- **evidence**: Assertion only; no observed failure.
- **source**: claudelogs/20260701_083008_*.md, 2026-07-01

### A long-running connector script times out when invoked from a Vantiq procedure (~30 s observed)

- **id**: DM-60
- **area**: ops and cost
- **status**: verified
- **cost**: minutes
- **symptom**: A blob-scanning analysis script (several minutes of work over ~17,000 files), written correctly against the connector pattern, dies when run through Vantiq.
- **cause**: The synchronous procedure -> source -> connector call path has an execution time limit a multi-minute script cannot fit inside. (The timeout event is the user's direct report; no error text was captured and the exact limit is unconfirmed - ~30 s was the working assumption that matched the behaviour.)
- **fix**: Run bulk/one-time jobs standalone outside the connector; reserve connector calls for work that finishes in seconds.
- **evidence**: User: "how long might the analysis take?  longer than 30 seconds?  if so... yep, it timed out.  Please hard-code the variables in there to use the values from .env, for both scripts.  they're one-time use and I will remove them after." Assistant: "Yes, for ~17,000 files this will take several minutes" - both scripts were then rewritten as standalone.
- **source**: claudelogs/20251220_180155_*.md, 2025-12-20

# deploy and export

### A Vantiq deploy pushes the source project over the target and deletes whatever the target has that the project does not - nothing inside Vantiq can safely carry an environment marker

- **id**: DM-35
- **area**: deploy and export
- **status**: verified
- **cost**: hours (overturned a dual-source design built and tested earlier the same day)
- **symptom**: A dev-only source plus per-environment procedure twins were built, installed, and verified - then torn out entirely, because a deploy would carry the dev binding to prod and remove prod-only objects.
- **cause**: The deploy model is overwrite-and-prune. Anything environment-specific inside a Vantiq project travels with the project; anything outside the project (procedures not added as project members) is what a deploy can remove.
- **fix**: Same source names, same services, same procedures in every environment; carry the environment in host-side connector config the deploy cannot reach (an env var in docker-compose), with connector-side code refusing rather than falling back when the scoped variables are unset.
- **evidence**: User (the correction that triggered the redesign): "The problem is that every deploy zaps whatever's not on prod, so working on dev with a dev source means that that's what would go over to prod. Choose: rebuild a connector, or delete a spare connector." Assistant: "it kills the per-server-binding idea outright ... Anything environment-specific in Vantiq is unsafe by construction."
- **source**: claudelogs/20260821_092650_*.md, 2026-08-21; repo scripts/pythonConnector/KNOWLEDGE.md

### A custom connector source type depends on a `sourceimpls` resource that is namespace-local and that subset exports silently drop

- **id**: DM-56
- **area**: deploy and export
- **status**: verified
- **cost**: hours (two separate incidents)
- **symptom**: Creating the connector source in a fresh namespace fails in a way that reads as "the source is broken"; importing an exported project subset onto another server leaves the source type missing. Import order compounds it - the importer decides its own order, and a source arriving before its implementation fails.
- **cause**: A custom source type (e.g. a Python execution connector type) is not a Vantiq built-in: stock types report `ars_namespace: system`, a custom one reports the namespace it was hand-created in. Its definition is a `sourceimpls` resource (four fields: `name`, `baseType: EXTENSION`, `verticle: service:extensionSource`, `config`), and a Custom View / hand-picked subset export omits it even when the parent project contains it. There is no seed zip; the extension-sources repo ships only the bare JSON for `vantiq load sourceimpls`.
- **fix**: Register the sourceimpl first (`vantiq -s <profile> load sourceimpls <Type>.sourceimpl.json`, or an MCP/REST insert on `sourceimpls`), then create the source. Keep the sourceimpl JSON in your repo - recreating four lines is faster than the export round trip.
- **evidence**: User: "It puked on adding the source for the PythonConnector, though - there's some sooper seekrit thing that you have to do to install it." And later, the other direction: "gotcha - I was missing 'sourceimpls' when I exported a subset. there must be a .zip somewhere that you import to get the initial information in there." (There isn't - confirmed against the namespace and the extension-sources repo.) Diagnosis: "Every stock type ... shows `ars_namespace: system`; yours shows `ars_namespace: [the production namespace]`. So in a new namespace the type simply doesn't exist yet, and creating a source of that type fails before it starts."
- **source**: claudelogs/20260821_092650_*.md and claudelogs/20260821_114754_*.md, 2026-08-21; claudelogs/20260806_165346_*.md, 2026-08-06

### A connector script goes live as a Vantiq document - `WITH script = "x.py"` names the document, and a copy on the connector host's filesystem never runs

- **id**: DM-36
- **area**: deploy and export
- **status**: verified
- **cost**: hours (a wrong deploy model had been documented and a deploy directive shipped scripts to a directory the connector has never opened)
- **symptom**: Scripts pushed to the host directory look deployed and never run; "is my change live?" gets answered from a file the container cannot even see.
- **cause**: Vantiq stores the script as a document, substitutes the `presetValues` into the script text, and pushes that down the websocket per call - preset variables exist as module-level globals when the code runs, read with `globals().get("<key>")` using distinctive snake_case keys (the substitution is textual - see DM-57). The container has no mount of the staging directory.
- **fix**: Install the built `.py` into the Vantiq project's Documents bucket (`POST /api/v1/resources/documents`); never check liveness from a host copy - and note nothing diffs the document against your source unless you do. Asymmetry worth remembering: replacing the script is a Vantiq-side install with no container action, while changing container env requires a recreate.
- **evidence**: "`/mnt/data/pythonConnector` is **not mounted into the container** - `docker exec vantiq-python-connector ls /mnt/data/pythonConnector` returns \"No such file or directory\"". Commit record: "A connector script goes live by installing the built .py into the VANTIQ PROJECT'S DOCUMENTS BUCKET; Vantiq substitutes the presetValues JSON into the script text and pushes that down to the connector ... so anything scp-ed there could never run." The mechanism in the user's own words (Dec 2025): "I tell the connector 'run this .py file and replace someToken with this value' and then that's what gets passed down to the environment: a modified .py file with what looks like a hardcoded value, replacing that token." Earliest statement 2025-12-11: "the file doesn't live on disk - it lives in a database & is grabbed by the code & shoved down to disk, with substitution variables as input variables."
- **source**: claudelogs/20260806_130030_*.md, 2026-08-06; claudelogs/20251211_153517_*.md, 2025-12-11; claudelogs/20251222_203458_*.md, 2025-12-22; repo scripts/pythonConnector/KNOWLEDGE.md

### Client event subscriptions cannot be round-tripped through a project export - some artifacts are IDE-only

- **id**: DM-37
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: Reproducing a working button -> service event -> collaboration loop by copying files in the exported project tree (`clients/.../controllers/dataStream/ce_*/onDataArrived.js`, collaborationtype JSON) stalls: the dataStream/client-event subscription wiring has no importable file form.
- **cause**: The export's `clients/` tree carries the handlers (onClick.js, onDataArrived.js), but the subscription behind a `ce_*` dataStream is created by the Vantiq UI tools and is not reconstructible by adding files and importing.
- **fix**: Treat procedures, service JSON, and collaborationtype JSON as file-editable; plan for client event subscriptions (and similar UI-built wiring) to be recreated in the IDE, and budget for that in any migration.
- **evidence**: User: "Some of these things aren't accessible via code and I can't import them - they're created using Vantiq UI tools and I need to consult someone who knows more about them."
- **source**: claudelogs/20251216_072044_*.md, 2025-12-16

### k8sdeploy_tools refuses to run unless targetCluster is a git repo with a fetchable origin, and `-Pcluster` names a branch in it, not a directory

- **id**: DM-38
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: Every gradle invocation dies at settings evaluation with `Invalid remote: origin` before any deploy task registers; when the JGit open fails, the vantiqSystem subproject silently never loads, so deploy tasks simply do not exist.
- **cause**: settings.gradle opens `targetCluster/` with JGit and pulls from `origin` at settings-evaluation time; the `cluster` property selects a branch. The workflow assumes Vantiq's internal clusters repo, which customers cannot reach (the 404 is not a permissions problem - it is not for customers). Also: use `-Pcluster=<name>`, not `-PtargetCluster=...`.
- **fix**: Create a local bare repo, `git init` targetCluster, `git checkout -B <cluster-name>`, add the bare repo as a `file://` origin, commit and push; invoke gradle with `-Pcluster=<branch-name>`. Long term, keep your own cluster-config repo.
- **evidence**: `Settings file '...\k8sdeploy_tools\settings.gradle' line: 73 ... > Invalid remote: origin`; "The vantiqSystem subproject isn't loading at all. The `include 'vantiqSystem'` is inside a conditional block"; "**k8sdeploy_clusters is NOT for us.** It's Vantiq's internal ops repo... That's why we got a 404".
- **source**: claudelogs/20260511_080018_*.md, 2026-05-11; claudelogs/20260603_125141_*.md, 2026-06-03. Vantiq 1.43.17 / k8sdeploy_tools 3.17.5 era.

### `configureVantiqSystem` recreates the targetCluster directory, destroying any git setup done before it

- **id**: DM-39
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: You initialized targetCluster as a git repo to satisfy settings.gradle (DM-38), and the very next run fails with `Invalid remote: origin` again as if you had done nothing.
- **cause**: The configureVantiqSystem task recreates targetCluster, wiping `.git`. On top of that, a root-owned directory makes the re-init's `git remote add` fail silently on "dubious ownership".
- **fix**: Do the git setup after configureVantiqSystem; add `git config --global --add safe.directory` first; use `git checkout -B` and remove-then-add the remote so stale state cannot break it.
- **evidence**: "First fix: added git init before configureClient - didn't work because configureVantiqSystem recreates targetCluster. Second fix: added git init after configureVantiqSystem - git init ran but `git remote add` failed silently due to 'dubious ownership'. Third fix: added `git config --global --add safe.directory`".
- **source**: claudelogs/20260511_080018_*.md, 2026-05-11

### The `provider` value drives StorageClass creation; there is no `openshift` provider and `other` has no storage template at all

- **id**: DM-40
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: `setupCluster` with `provider=other` fails outright; with `provider=aws` it happily creates AWS EBS StorageClasses on a local kubeadm VM with no AWS integration.
- **cause**: Storage classes are generated from per-provider templates; on-prem (`other`) ships no template, and `openshift` is not a recognized provider. Vantiq engineering's answer: use the underlying cloud provider (e.g. `provider=aws` on OpenShift-on-AWS) and fix provider-specific resources manually.
- **fix**: Set `provider` to the underlying cloud, then supply your own StorageClass.
- **evidence**: `> Cannot configure storage class, file .../k8sdeploy_tools/build/setup/vantiq-sc.yaml does not exist`; `kubectl get storageclass` on the local VM showing `gp2-wait kubernetes.io/aws-ebs`; engineering Q&A: "Does k8sdeploy_tools accept `provider=openshift`? No. Use the underlying cloud provider."
- **source**: claudelogs/20260511_080018_*.md, 2026-05-11; claudelogs/20260603_125141_*.md, 2026-06-03

### Gradle injects `storageClass: vantiq-sc` into the helm values, and `encryptVolumes=false` does not stop it

- **id**: DM-41
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: PVCs for influxdb/grafana/grafanadb sit Pending forever requesting a `vantiq-sc` StorageClass that does not exist; flipping `encryptVolumes=false`, cleaning, and redeploying still produces PVCs bound to `vantiq-sc`. No error anywhere - just Pending PVCs.
- **cause**: The injection happens in k8sdeploy_tools' gradle build logic, not in the chart values or generated overrides, so nothing you can regenerate removes it.
- **fix**: Stop fighting it: create a `vantiq-sc` StorageClass mirroring the cluster default (same provisioner/binding mode) and leave `encryptVolumes=true`.
- **evidence**: "There it is -- `storageClass: vantiq-sc` is being injected into the helm values by the gradle build logic (not from our overrides)"; "Still `vantiq-sc`. The gradle build logic is injecting this regardless of `encryptVolumes`."
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### The Vantiq chart's `mongo-available` init container uses an unqualified `mongo` image, which RHEL shortname aliasing redirects to an unauthorized registry

- **id**: DM-42
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: On RHEL/CRI-O nodes, vantiq-0 sits in Init:ImagePullBackOff pulling `mongo:5.0.18` from `bds-docker-release.jfrog.io`, although no mirror, proxy, or ImageContentSourcePolicy exists anywhere you look.
- **cause**: RHEL ships `/etc/containers/registries.conf.d/001-rhel-shortnames.conf` containing `"mongo" = "bds-docker-release.jfrog.io/mongo"`. The MongoDB statefulset honors `mongodb.image.repository`, but the vantiq statefulset's init container is a different template that renders bare `mongo:TAG`, so the override never reaches it. ImageTagMirrorSet cannot help - shortname resolution happens before CRI-O's mirror logic.
- **fix**: Set `mongodb.image.repository: docker.io/library/mongo` for the mongodb chart, and patch the vantiq statefulset's init container image post-deploy. Chart bug reported to Vantiq engineering.
- **evidence**: `initializing source docker://bds-docker-release.jfrog.io/mongo:5.0.18`; shortnames file: `"mongo" = "bds-docker-release.jfrog.io/mongo"`; "the `vantiq` statefulset's `mongo-available` init container uses bare `mongo:5.0.18` -- it's a different template that doesn't use `mongodb.image.repository`".
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### Every `deployVantiq` (helm upgrade) silently reverts the init-container image patch

- **id**: DM-43
- **area**: deploy and export
- **status**: verified
- **cost**: minutes, recurring on every deploy
- **symptom**: The mongo init container patched last week (DM-42) is back in Init:ImagePullBackOff after an otherwise unrelated redeploy.
- **cause**: The post-deploy patch is not part of the chart; each helm upgrade re-renders the unqualified image.
- **fix**: Re-apply the patch and delete the pod after every deployVantiq (bake it into a post-deploy script).
- **evidence**: "**helm upgrade resets init container every time**: Each `deployVantiq` reverts mongo init container to unqualified `mongo:TAG`. Fix: Re-apply patch and delete pod after every deploy."
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### The Vantiq pod mounts a `dbbackup-creds` secret even when backup is disabled

- **id**: DM-44
- **area**: deploy and export
- **status**: verified
- **cost**: minutes
- **symptom**: vantiq-0 stuck ContainerCreating with `MountVolume.SetUp failed` for a secret no config of yours mentions, on a deployment with backup disabled.
- **cause**: The chart mounts the secret unconditionally.
- **fix**: `oc create secret generic dbbackup-creds -n <ns> --from-literal=credentials=""`.
- **evidence**: "Vantiq pod mounts `dbbackup-creds` secret even when backup is disabled. Fix: `oc create secret generic dbbackup-creds -n <ns> --from-literal=credentials=\"\"`" (workaround recorded after the MountVolume.SetUp failure).
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### The shared chart pins a bitnami mongodb-exporter tag that no longer exists on Docker Hub

- **id**: DM-45
- **area**: deploy and export
- **status**: verified
- **cost**: minutes
- **symptom**: mongodb-0 stays 1/2 Ready forever; the metrics sidecar is in ErrImagePull with "manifest unknown".
- **cause**: The chart references `bitnami/mongodb-exporter:0.10.0-debian-9-r71`, removed from Docker Hub when Bitnami purged old images.
- **fix**: `mongodb.metrics.enabled: false` (or supply a live tag).
- **evidence**: "the `metrics` sidecar can't pull `bitnami/mongodb-exporter:0.10.0-debian-9-r71` (manifest unknown on Docker Hub -- this old tag has been removed)".
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### Vantiq's OpenShift SCC needs are broader than `anyuid`, and pods admitted before a grant keep their old SCC

- **id**: DM-46
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: After granting `anyuid`, grafana and telegraf-ds still FailedCreate, and vantiq-0 keeps running under `restricted-v2` even though its service account now has `anyuid`.
- **cause**: Grafana's init container needs the CHOWN capability (requires `privileged`); telegraf-ds uses hostPath. SCC admission is evaluated at pod creation, so an existing pod keeps its old SCC until deleted. And `deployShared` can recreate service accounts, dropping the grants.
- **fix**: Grant `anyuid` to the default/grafana/influxdb/telegraf-prom/unstructured-api service accounts and `privileged` to grafana and telegraf-ds; re-grant after deployShared; delete pods created before the grant, and confirm which SCC admitted a pod from its `openshift.io/scc:` annotation.
- **evidence**: "the `anyuid` SCC isn't enough because grafana's init container adds the `CHOWN` capability... It needs `privileged` SCC"; "The pod was created before our SCC grant, so it got admitted under restricted-v2. It needs a restart"; post-fix annotation `openshift.io/scc: anyuid`.
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### The license is bound to an FQDN audience; changing the ingress domain to fix a derived URL crashes the server

- **id**: DM-47
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: You change `ingress.host.domain` so a constructed URL resolves, and the previously healthy server goes into CrashLoop rejecting its own license.
- **cause**: The chart constructs URLs from `<installation>.<ingress.host.domain>`, and the license audience is checked against exactly that host. The license FQDN (a reusable one, CNAME'd per Vantiq practice so licenses survive rebuilds) need not match the cluster's router hostname, so anything deriving a URL from the ingress domain (the k8sworker CronJob's VANTIQ_URL) breaks while the domain itself is untouchable.
- **fix**: Never change the ingress domain to fix a derived URL; patch the consumer post-deploy, and permanently fix it with a DNS CNAME from the license FQDN to the router. For browser TLS a second Route on the apps domain is needed - the OpenShift wildcard cert only covers `*.apps.<cluster>`.
- **evidence**: Worker error: `failed opening Vantiq session to https://<installation>.vantiq.com: Failed to resolve <installation>.vantiq.com`; the attempted domain change "broke Vantiq: `server host URI does not match license audience [<installation>.vantiq.com]`"; "Actual fix: Revert domain, patch CronJob VANTIQ_URL separately."
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### The k8sworker's bundled fabric8 client (6.7.1) cannot parse the Kubernetes 1.34 `/version` response and dies with a bare `KubernetesClientException`

- **id**: DM-48
- **area**: deploy and export
- **status**: verified
- **cost**: a day or more
- **symptom**: vantiq-worker crashes with `io.fabric8.kubernetes.client.KubernetesClientException: An error has occurred.` - no stack trace, no detail; RBAC, TLS, DNS, and cert trust all check out. (FIPS was suspected repeatedly and ruled out.)
- **cause**: k8sworker 1.40.10 bundles fabric8 6.7.1, which cannot deserialize the K8s 1.34 `/version` response with its new `emulationMajor`/`minCompatibilityMajor` fields.
- **fix**: A newer k8sworker image is the real fix - Vantiq 1.43.15+ ships fabric8 7.3.2, natively K8s 1.34 compatible, so this no longer holds on current releases. The 1.40-era stopgap was an nginx proxy in front of the K8s API serving a static 1.29-style `/version` and passing everything else through. Check the release's supported K8s version before choosing cluster versions.
- **evidence**: `io.fabric8.kubernetes.client.KubernetesClientException: An error has occurred.` (nothing else); "Root cause: fabric8 6.7.1 cannot parse K8s 1.34 `/version` response with new fields. Fix: nginx proxy returning K8s 1.29-compatible `/version` response. Confirmation: Worker logs showed `Kubernetes Client Version: 6.7.1` and `No workItem available`."
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### The k8sworker's `vantiq-worker` token secret is not created by the deploy

- **id**: DM-49
- **area**: deploy and export
- **status**: verified
- **cost**: minutes
- **symptom**: The worker CronJob pod fails immediately on a missing secret, on a deployment that completed "successfully".
- **cause**: The chart expects a `vantiq-worker` secret carrying an admin access token, but nothing in the gradle flow creates it - the token only exists after you extract or mint one from the running server.
- **fix**: `oc create secret generic vantiq-worker -n <ns> --from-literal=token="<adminToken>"` after extracting the admin token.
- **evidence**: `Error: secret "vantiq-worker" not found`.
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### Vantiq 1.43.x will not start without an AI-assistant secret even when AI features are unused - and the log calls the fatal failure a WARN

- **id**: DM-50
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: A fresh 1.43 server logs `WARN ... Failed to deploy verticle guice:io.vantiq.aimanager.AiManager` / `No content to map due to end-of-input`, then startup aborts.
- **cause**: The AiManager verticle needs a `vantiq-ai-assistant-env` secret to parse at startup. The documented way to disable AI (`vectordb.enabled: false` AND `worker.enabled: false`) also disables the k8sworker, which you may need. Absent the secret, the WARN-level verticle failure aborts the server. Related same-version trap: an empty `vectorDbService.json` in BOTH the vantiq-config and loadmodel-config configmaps causes a fatal crash - patch both to `{}` when vectordb is disabled.
- **fix**: Create a placeholder: `oc create secret generic vantiq-ai-assistant-env -n <ns> --from-literal=.env="OPENAI_API_KEY=disabled"` and restart the pod.
- **evidence**: "The log says it's a WARNING (`WARN io.vantiq.vertx.BootstrapVerticle - Failed to deploy verticle`) but then `ERROR io.vantiq.vertx.BootstrapVerticle - Startup of Vantiq Server failed.` -- so it's fatal"; docs quote: "disable AI by setting both `vectordb.enabled: false` AND `worker.enabled: false`. But we WANT the worker."
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### There is no direct upgrade path 1.40.10 -> 1.43.17; the schema migrator is missing intermediate steps

- **id**: DM-51
- **area**: deploy and export
- **status**: verified
- **cost**: hours
- **symptom**: After swapping the image, the server refuses to start on a schema migration failure naming a method that does not exist in the shipped binary.
- **cause**: The 1.43.17 migrator steps schema 550 -> 588 through per-version migrate methods, and `migrate551()` is absent - intermediate release stepping stones are required. (A fresh 1.43 install initializes schema 588 cleanly.)
- **fix**: Revert; get the intermediate versions from Vantiq engineering before attempting a multi-minor jump - or clean-install if the data is expendable.
- **evidence**: `Schema migration failed. Current schema version is 550, target schema version is 588. MissingMethodException: migrate551()` - "Fix: Reverted to 1.40.10. Need intermediate version stepping stones from Engineering."
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### Gradle reads a snapshot kubeconfig at `targetCluster/kubeconfig`, so an `oc login` refresh never reaches it

- **id**: DM-52
- **area**: deploy and export
- **status**: verified
- **cost**: minutes, recurring (login tokens expire ~24h)
- **symptom**: `oc whoami` works, but every gradle-driven call gets 401s.
- **cause**: k8sdeploy_tools uses the copy at `targetCluster/kubeconfig`, not `~/.kube/config`; the copy silently goes stale.
- **fix**: Copy `~/.kube/config` over `targetCluster/kubeconfig` before every gradle invocation (wrap gradle in a helper that does it).
- **evidence**: "The kubeconfig in targetCluster has a stale token. The token in `~/.kube/config` is current (since `oc whoami` works), but the copy we made earlier has expired."
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### k8sdeploy_tools creates only Ingress resources, never OpenShift Routes; the InfluxDB databases are likewise never created

- **id**: DM-53
- **area**: deploy and export
- **status**: verified
- **cost**: minutes each
- **symptom**: Deployment "completes" but nothing is reachable from outside the cluster; Vantiq logs a steady stream of errors writing metrics.
- **cause**: The tooling predates OpenShift support (external access needs a hand-made Route with edge TLS termination), and the `system` / `vantiq_server` InfluxDB databases are assumed to exist but no task creates them (non-fatal - Vantiq runs, logging errors).
- **fix**: Create the Route and the two InfluxDB databases post-deploy; automate both in post-deploy scripts.
- **evidence**: "k8sdeploy_tools does NOT create Routes (only Ingress resources)"; "InfluxDB databases `system` and `vantiq_server` need to be created (Vantiq is logging errors trying to write metrics to non-existent databases)".
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### `generateSecrets` reports BUILD SUCCESSFUL even when secrets were not created or applied

- **id**: DM-54
- **area**: deploy and export
- **status**: unverified
- **cost**: minutes
- **symptom**: generateSecrets succeeds at the gradle level, but pods later fail on missing secrets; the generated YAMLs were never applied (or never written).
- **cause**: The gradle tasks are fire-and-forget; generateSecrets emits YAML files but does not reliably apply them, and reports success regardless.
- **fix**: After generateSecrets, verify the expected secret YAMLs exist and `oc apply` them explicitly.
- **evidence**: Session summary prose only ("`run_gradle generateSecrets` succeeds at the gradle level even if individual secrets fail"); no captured error text - hence unverified.
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### Admin credentials on a fresh install live in MongoDB, not in anything the tooling hands you - and on 1.43 the layout changed

- **id**: DM-55
- **area**: deploy and export
- **status**: unverified
- **cost**: hours
- **symptom**: Deployment is green but there is no way to log in; on 1.43 the token you expect from the pre-1.43 location is not there and the `system` user has no password.
- **cause**: The documented path is reading the admin token out of server logs; in practice it was extracted by querying MongoDB directly. On 1.43 the database is `ars02` (not `<installation>_system`) and the token field moved; on a fresh 1.43 install no admin token is stored, the `system` user exists passwordless, and a stored service token (the AI assistant's) carried system-level access and was used to mint a proper admin token.
- **fix**: Query MongoDB via the mongodb pod with the root password from the `mongodb` secret; on 1.43, authenticate with a stored service token, then create a real admin token/password.
- **evidence**: Narrative only ("on a fresh install, the system user exists with no password... The AI assistant token works and has system access") - no error text, hence unverified.
- **source**: claudelogs/20260603_125141_*.md, 2026-06-03

### The Vantiq mongo backup export can emit every document of a type roughly twice; raw row counts are ~2x the unique-key counts, and the doubling is intermittent

- **id**: DM-61
- **area**: deploy and export
- **status**: verified
- **cost**: hours (a clean pull was misdiagnosed as a partial export, a cycle report was rewritten into a data-integrity hold, and the next action blocked on it)
- **symptom**: Two pulls of the "same" data disagree ~2x on everything (67,113 assessments vs 33,595), and the natural reading - the smaller, newer file is a partial export - is exactly backwards.
- **cause**: The doubled file is the raw, un-deduped mongo dump from the Vantiq server's backup process: 67,113 rows but only 33,504 unique primary keys, with whole top-level documents repeated ("nearly every assessment appears twice", though not exactly 2x). It is a property of the export, not the data, and it is intermittent - a 2026-06 pull was doubled while 2026-07 pulls profiled clean at a 1.00x duplication factor. The mechanism inside the backup process was never root-caused, so which pulls double and why remains open.
- **fix**: Always dedup by the type's unique key (first occurrence wins) before counting anything from a backup export; never conclude "partial export" from a smaller newer file without first comparing unique-key counts. Harden counting scripts to dedup and print how many rows they dropped.
- **evidence**: Assistant, misdiagnosing: "An older backup cannot legitimately hold ~2x more Reviewed annotations than a newer one, so the 2026-07-13 pull is most likely a **PARTIAL export**". User's correction: "It's the full backup - some of the annotation review scripts know how to deal with this, as the json itself needs to be modified in order to continue. Something about the mongo backup process does this." Resolution: "**July is clean** (33,595 rows, 33,595 unique WAIDs, zero duplicates). **June was doubled** - 67,113 rows but only 33,504 unique WAIDs; nearly every assessment appears twice."
- **source**: claudelogs/20260713_173546_*.md, 2026-07-13; clean-pull profiling in claudelogs/20260716_101615_*.md, 2026-07-16

### A Vantiq complete backup contains TWO same-named JSON files per type - the type schema and the data - at parallel paths

- **id**: DM-62
- **area**: deploy and export
- **status**: verified
- **cost**: minutes
- **symptom**: A `find` by filename returns two hits per backup directory; grabbing by name alone can hand you the type definition instead of the records.
- **cause**: The backup layout exports both the type definition and the type's documents under the same leaf filename: `vantiq_complete_backup_YYYYMMDD_HHMMSS/types/com/<company>/<app>/<Type>.json` (schema) and `.../data/com/<company>/<app>/<Type>.json` (the data).
- **fix**: Always take the `data/` copy; treat `types/` as schema only.
- **evidence**: find output listing both `/types/com/.../<Type>.json` and `/data/com/.../<Type>.json` in each backup directory; note recorded in-session: "**Two copies per backup**: `data/...` = the actual assessment DATA (use this); `types/...` = the Vantiq type/schema (NOT the data)."
- **source**: claudelogs/20260716_101615_*.md, 2026-07-16

## Gaps

- transcripts scanned: 586 enumerated (570 markdown session archives in a local log repo, 2025-11-04 to 2026-09-03, plus 16 raw `.jsonl` under `~/.claude/projects`), in two passes. Pass 1 scored all files on generic Vantiq-platform vocabulary: 115 candidates (>=10 term hits), 93 with correction-patterns co-located near the terms, ~36 transcripts deep-read by five parallel review passes. Pass 2 re-scored everything on Python Connector and MongoDB vocabularies specifically (presetValues, pythonCallResults, server.config, mongo/mongodump, backup paths), which surfaced 41 qualifying files pass 1's vocabulary had missed plus five pass-1 candidates never deep-read; ~15 of those with co-located hits were then read by two further review passes (DM-57 through DM-62 came from pass 2). Sampling in both passes was by term density and correction-pattern co-location, not by date - a session with no correction-shaped language would still be missed.
- date range: 2025-12-05 to 2026-08-21 for the entries above (sessions exist from 2025-11-04 and to 2026-09-03; the ends contained no qualifying Vantiq learnings).
- could not verify: VAIL short-circuit evaluation (DM-07, asserted in shipped code, never watched); two connectors sharing one source splitting the call stream (DM-34); generateSecrets fire-and-forget (DM-54); fresh-install admin-credential extraction detail (DM-55); the exact connector call-timeout limit (DM-60 - the timeout itself was observed, the ~30 s figure was the working assumption); the mechanism behind the intermittent mongo-export doubling (DM-61 - the doubling is verified, its cause is not); an `ars_version` MCP version-conflict was never actually hit in any session despite the workflow documenting it.
- deliberately excluded: everything predictable from documentation once read (secrets being unreadable after write; Vantiq type-system limits - no CHECK constraints, no JOIN; the `with profiles` escalation; connector-SDK README gotchas; the 2-day invite expiry); generic Kubernetes/OpenShift/bash/git/Docker lessons with nothing Vantiq-specific; Azure SQL/pyodbc behaviour; our own application's design decisions (allowlist dispatcher envelope, fail-closed provisioning) and our own infrastructure conventions (a backup `latest/` symlink that vanished; deploy directives in our build system); Claude Code harness behaviours (sandbox networking, `.mcp.json` auto-load, oversized tool results landing as one-line JSON files); one engagement-audit project that involved reading a Vantiq-based codebase rather than building on the platform; observations about documentation quality (e.g. how thinly SELECT is covered) rather than platform behaviour; annotation-app data-shape observations with no failure behind them (free-text status fields, dimensions living only on boxes).
- concentration warning: this is essentially ONE engagement's history - one company's namespaces on one self-hosted single-node Vantiq (1.40-era edge cluster), one OpenShift partner-lab platform install (1.40.10 and 1.43.17, k8sdeploy_tools 3.17.5, May-Jun 2026), and one test.vantiq.com namespace via the pre-release MCP tooling (Jul-Aug 2026). The connector entries describe the Python Execution Connector specifically; the install entries are version-pinned where known (DM-48 is confirmed fixed in 1.43.15+); the identity-provider entries (DM-12) may be tenant-configuration-dependent. Nothing here has been checked against a second, unrelated namespace or installation.
