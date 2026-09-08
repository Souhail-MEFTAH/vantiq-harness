> **Redacted for public release.** This file was written for internal pooling
> and is published with customer, namespace and deployment identifiers removed.
> Angle-bracket placeholders (`<pkg>`, `<ns>`, `<namespace>`, `<deployment>`,
> `<installation>`, `<backend repo>`) stand in for names that were here. Vantiq
> platform error codes and `dev.vantiq.com` are kept verbatim, because they are
> what you would search for.

### Saving a procedure returns 200 even when it does not compile; errors sit in `vailErrors` until execution

- **id**: NR-01
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: A POST or upsert of a procedure or rule returns 200 with a populated record, and the resource only fails when it is first executed or opened in the IDE.
- **cause**: The write endpoint persists the source regardless of compile result. Compile errors are stored on the record in a `vailErrors` array and are not reflected in the HTTP status.
- **fix**: After every VAIL write, read the resource back (`selectOne` on `system.procedures` or `system.services`) and treat a non-empty `vailErrors` as failure. Re-saving a resource unchanged forces a recompile, which is how a namespace-wide check after a platform upgrade was done.
- **evidence**: User's own words: "the platform *accepts the save* of a procedure with these errors (the record is created with a populated `vailErrors` array) and the failure surfaces when you execute it." Stored error read back from a previously "successful" save: `{"error":{"code":"io.vantiq.rulemgr.vail.method.chain.async.statement","message":"Chained expressions cannot be applied to a VAIL procedure invocation."},"severity":"ERROR","location":{"startPosition":{"line":8,"column":42}}}`
- **source**: 293a4e52-c075-40fa-a395-16425e389e95.jsonl, 2026-08-07; f2155b10-42b0-4320-9c71-337b54e6d7b7.jsonl, 2026-08-05

### `validateVAIL` passes code that the real compiler rejects on deploy

- **id**: NR-02
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: The MCP `validateVAIL` tool reports zero warnings, then the `update` deploy of the same code lands with a syntax error in `vailErrors`.
- **cause**: `validateVAIL` is a lighter static check, not the platform compiler. It missed an `instanceof` expression the compiler does not accept.
- **fix**: Treat `validateVAIL` as a pre-filter only. The gate is `vailErrors` on the record after the real insert or update.
- **evidence**: `validateVAIL` returned `{"warningCount":0,"warnings":[]}`; the deploy returned `vailErrors: "'instanceof' encountered when expecting a closing paren (')')"`. Seen in two separate sessions.
- **source**: a6ccb088-57e2-455c-85bc-b5920a4058dd.jsonl, 2026-08-27; d2939399-afc9-4468-8587-6045ee5c1a89.jsonl, 2026-08-24

### Chaining a method call onto a procedure invocation is a compile error

- **id**: NR-03
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: `Hash.md5(x).encodeHex().toString()` is flagged at the column of the first chained call.
- **cause**: A procedure invocation is treated as async and cannot have further expressions applied in the same statement.
- **fix**: Assign the invocation result to a variable, then call methods on the variable in a separate statement.
- **evidence**: `{"code":"io.vantiq.rulemgr.vail.method.chain.async.statement","message":"Chained expressions cannot be applied to a VAIL procedure invocation."}`. Failing code `Hash.md5(report.filename).encodeHex().toString()` was replaced by `var failedHash = Hash.md5(report.filename); var failedId = failedHash.encodeHex().toString()` and compiled clean.
- **source**: 2d7dceef-a88a-4a0e-a312-fb433be846ca.jsonl, 2026-08-21; f2155b10-42b0-4320-9c71-337b54e6d7b7.jsonl, 2026-08-05

### A chained String call inside a compound `&&` condition compiles, then fails at runtime with a Groovy syntax error

- **id**: NR-04
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: The procedure saves with empty `vailErrors`, and every execution fails with `startup failed` pointing at a line that begins with a bare `.`.
- **cause**: `typeOf(name) == "String" && row.memberName.toLowerCase().contains(lowered)` transpiled to Groovy with the receiver expression dropped from the chained call.
- **fix**: Split the chain into local variables before combining into a boolean.
- **evidence**: `{"code":"com.accessg2.ag2rs.execution.reference.compile.failed","message":"The code for : <pkg>.searchMembers could not be compiled. ... startup failed:\nio.vantiq.procedures.<ns>.<pkg>_searchMembers.groovy: 112: unexpected token: . @ line 112, column 2.\n   (.indexOf(scratchpad.lowered) >= 0) ) {\n    ^"}`
- **source**: 225b78cd-1505-447c-8bf1-ebe63ae7cdec.jsonl, 2026-08-06

### `map` is an illegal parameter name

- **id**: NR-05
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: A procedure with a parameter named `map` fails with a syntax error plus an "undeclared variable" error at every use.
- **cause**: `map` is reserved by the compiler and cannot be shadowed by a parameter or variable.
- **fix**: Rename the parameter.
- **evidence**: `{"code": "io.vantiq.vail.syntax.error", "message": "illegal parameter name 'map'"}` followed by `"use of undeclared variable 'map'"` at each reference. Renamed to `keyMap` and compiled.
- **source**: 22759b47-5d80-4bea-a4fc-34440ad64dd5.jsonl, 2026-09-02

### A local variable named `match` with a method call is resolved as a procedure reference

- **id**: NR-06
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: `var match = ""; ... match.length()` fails with a "procedure could not be found" error naming `<package>.match.length`.
- **cause**: The binder resolved `match.length` as a procedure path rather than a method on the local String.
- **fix**: Rename the variable. Only `match` was tried, so it is unknown whether other names collide.
- **evidence**: `"code":"io.vantiq.rulemgr.vail.referenced.resource.not.found","message":"The procedure '<pkg>.match.length' referenced by the procedure '<pkg>.ReportScraper.stripSectionPrefix' could not be found."` Renamed to `bestKey`, and the re-read record showed `compilerOCC` incremented with no `vailErrors`.
- **source**: d63e378a-80b5-4f60-934a-9f479e82419d.jsonl, 2026-09-03

### A parameter declared as bare `Array` is resolved as a missing custom type

- **id**: NR-07
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: The compile error names a type `<package>.Array` that could not be found, not an array-typing problem.
- **cause**: Without an element type, `Array` is parsed as a reference to a user type named `Array` in the current package.
- **fix**: Always give array parameters an element type, for example `bareKeys String Array`.
- **evidence**: `"message":"The type '<pkg>.Array' referenced by the procedure '<pkg>.ReportScraper.stripSectionPrefix' could not be found. Please either define the type or remove the reference."` Declaration `bareKeys Array` changed to `bareKeys String Array` and compiled.
- **source**: d63e378a-80b5-4f60-934a-9f479e82419d.jsonl, 2026-09-03

### `stateless` on a procedure that is not part of a service is a compile error

- **id**: NR-08
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: Inserting a standalone scratch procedure copied from a service procedure fails on the modifier.
- **cause**: Procedure modifiers are only accepted on service procedures.
- **fix**: Drop the modifier on standalone procedures.
- **evidence**: `"code":"io.vantiq.rulemgr.vail.illegal.procedure.modifier","message":"Illegal use of the procedure modifier(s) 'stateless' for non-service procedure '<pkg>.probeDateMath'.  Procedure modifiers may only be applied to service procedures."`
- **source**: 52b5af17-60da-4406-91d4-02675b4f18d4.jsonl, 2026-08-27

### `DateTime` is a raw `java.time.Instant` at runtime, so `toInteger(now())` and most convenience methods throw

- **id**: NR-09
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: `toInteger(now())`, `.minusMinutes(n)`, `.getMillis()` and `DateTime.diff` compile but throw `MissingMethodException` on execution.
- **cause**: The value is a Java `Instant`, which only has the `Instant` API (`toEpochMilli`, `minusMillis`, `plusMillis`).
- **fix**: Use `now().toEpochMilli()` or `toMillis(dt)` and do millisecond arithmetic yourself.
- **evidence**: `groovy.lang.MissingMethodException: No signature of method: java.time.Instant.toLong() is applicable for argument types: () values: []`; `No signature of method: java.time.Instant.minusMinutes() is applicable for argument types: (Long) values: [10]\nPossible solutions: minusMillis(long), minusNanos(long)`; `No signature of method: java.time.Instant.getMillis() is applicable`. The probe procedure was executed live against a 1.44 namespace.
- **source**: 2d7dceef-a88a-4a0e-a312-fb433be846ca.jsonl, 2026-08-21; 52b5af17-60da-4406-91d4-02675b4f18d4.jsonl, 2026-08-27

### A `$regex` literal inside `WITH where` throws a `GStringImpl` cast error at runtime, but a parameter value works

- **id**: NR-10
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: `SELECT ... WITH where = {name: {"$regex": pattern}}` compiles and then fails on execution, even after `.toString()` on the pattern.
- **cause**: String values built in VAIL transpile to Groovy `GStringImpl`, which the Mongo layer rejects for `$regex`. In a different session the same clause worked when the value was a plain String procedure parameter, so the failure appears to depend on how the value was produced. The transcripts do not resolve the difference.
- **fix**: Pass the regex value straight from a String parameter, or select the candidate rows and match in VAIL.
- **evidence**: `java.lang.ClassCastException: class org.codehaus.groovy.runtime.GStringImpl cannot be cast to class java.lang.String (org.codehaus.groovy.runtime.GStringImpl is in unnamed module of loader 'app'; java.lang.String is in module java.base of loader 'bootstrap')`, three attempts. Working case on 2026-08-07: `needle=jon` returned one row, `needle=zzz` returned `[]`.
- **source**: 2d7dceef-a88a-4a0e-a312-fb433be846ca.jsonl, 2026-08-21; 293a4e52-c075-40fa-a395-16425e389e95.jsonl, 2026-08-07

### `WITH where = {...}` accepts a raw query document, which is the only substring search VAIL has

- **id**: NR-11
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: There is no `LIKE` or `.contains()` in a `WHERE` clause, and nothing near the SELECT reference says a raw document form exists.
- **cause**: `WITH where = <object>` passes a REST-style query document through, including `$regex` and `$options`.
- **fix**: `SELECT ... FROM T WITH where = {prop: {"$regex": needle, "$options": "i"}}` with `needle` a String parameter (see NR-10).
- **evidence**: A docs fetch in the session found no partial-match operator for `WHERE`. Live run: positive control returned one matching row, negative control returned `[]`.
- **source**: 293a4e52-c075-40fa-a395-16425e389e95.jsonl, 2026-08-07

### `.contains()` inside a `WHERE` clause is bound as a procedure reference, not a String method

- **id**: NR-12
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: `SELECT ... WHERE memberName.contains("x")` fails to compile with a missing-procedure error naming `<package>.memberName.contains`.
- **cause**: Identifiers in a `WHERE` qualification are resolved against the queried type and the procedure namespace, not as method calls. Reproduced on both a plaintext and an encrypted field to rule out encryption.
- **fix**: Filter in code after the query, or use the raw document form in NR-11.
- **evidence**: `{"error":{"code":"io.vantiq.rulemgr.vail.referenced.resource.not.found","message":"The procedure '<pkg>.memberName.contains' referenced by the procedure '<pkg>.searchMembers' could not be found."`
- **source**: 225b78cd-1505-447c-8bf1-ebe63ae7cdec.jsonl, 2026-08-06

### A bare procedure parameter inside `WHERE` is resolved against the queried type

- **id**: NR-13
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: `WHERE includeTest == true`, where `includeTest` is a procedure parameter, fails with "property not defined" on the type.
- **cause**: The left side of a `WHERE` comparison is treated as a property of the queried type.
- **fix**: Apply parameter-driven filtering in code after the query.
- **evidence**: Assistant quoting the compile result in the same turn: `"property Report.includeTest is not defined."` The raw tool result was not located, so this rests on the in-session quotation. A procedure deployed the next day carries the comment "Bare params in WHERE resolve as type properties, so alias before filtering", showing the fix was applied as a standing rule.
- **source**: 225b78cd-1505-447c-8bf1-ebe63ae7cdec.jsonl, 2026-08-06; 19796dbf-22ff-40b9-ab68-4693781c5ebd.jsonl, 2026-08-07

### `return` inside a `catch` block does not stop the statements after the `try`

- **id**: NR-14
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: A procedure with `catch (error) { ...; return false }` followed by a `PUBLISH` still publishes after the failure, so an empty event went out on every error.
- **cause**: The `return` set the value but execution continued past the try/catch.
- **fix**: Track success in a flag set inside the `catch` and gate the later statements on it.
- **evidence**: User's correction: "the OLD server reIngestReport has `return false` inside the catch — per the VAIL early-return gotcha that never exited early, so the current server version publishes an empty records list even after a failure." Fixed code comment: "Note VAIL `return` never exits early, so success/failure is tracked with a flag and the publish is gated on it." The original broken source was described but not quoted, and the behaviour was not re-tested in isolation.
- **source**: 2d7dceef-a88a-4a0e-a312-fb433be846ca.jsonl, 2026-08-21

### `SELECT ONE` throws when more than one row matches; it is not "take the first"

- **id**: NR-15
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: A queue hand-off using `SELECT ONE` to fetch the next waiting item stalls exactly when a backlog exists. The reference doc only describes the single-match and no-match cases.
- **cause**: With two or more matches the statement throws, and the exception was swallowed by a surrounding catch.
- **fix**: `SELECT * FROM T WITH LIMIT = 1 WHERE ...` and index `[0]`. `LIMIT` is a `WITH` option after `FROM`; a trailing `LIMIT 1` was rejected by the compiler.
- **evidence**: Diff: `-next = SELECT ONE * FROM <pkg>.LegacyReport WHERE indexed == false AND error == null AND pages != null AND id != currentId` to `+var waiting = SELECT * FROM <pkg>.LegacyReport WITH LIMIT = 1 WHERE ...` with "`SELECT ONE`, which throws exactly when 2+ reports are queued". The thrown error text itself was not captured.
- **source**: a6ccb088-57e2-455c-85bc-b5920a4058dd.jsonl, 2026-08-27

### `DELETE` with a filter that matches nothing throws `resource.not.found`

- **id**: NR-16
- **area**: VAIL
- **status**: unverified
- **cost**: minutes
- **symptom**: A cleanup `DELETE ... WHERE` throws instead of deleting zero rows.
- **cause**: Not established; only recorded as observed.
- **fix**: Select first and delete per row, or catch the error.
- **evidence**: Code comment dated in the source: "Runtime gotchas (verified live 2026-08-21) ... DELETE throws resource.not.found when nothing matches." No error body was captured in any transcript.
- **source**: `<backend repo>/procedures/.../ReportScraper_mintIngestToken.vail`, 2026-08-25

### An unqualified system service name inside a packaged file resolves into that package, and the compile failure silently kills the rule

- **id**: NR-17
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: A rule calling `Notification.sendPayloadToAll(...)` never fires. Nothing appears in the app or the error log; records just stay in their initial state.
- **cause**: `Notification` resolved to `com.vantiq.demo.triage.Notification`, the compile failed, and a rule with a compile error does not run.
- **fix**: `import service Notification` at the top of any packaged file that calls a system service.
- **evidence**: `The procedure 'com.vantiq.demo.triage.Notification.sendPayloadToAll' ... could not be found`; session finding: "bare `Notification` in package `com.vantiq.demo.triage` resolved into the package; the compile error also silently killed the insert rule (tickets stayed `status: "new"` with nothing in the error log)". Fixed with the import.
- **source**: 705a2c7c-01cd-4cd0-b7fa-734a9ac86972.jsonl, 2026-08-26

### An unqualified topic path in packaged VAIL is prefixed with the file's package, so publisher and subscriber can land on different topics

- **id**: NR-18
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: A scheduled publish loop runs without errors and the subscribing rule never fires.
- **cause**: A procedure in `package com.demo.missile` and a rule in `package com.demo.missile.SimControl` each resolved `"/missiledefense/tick"` under their own package.
- **fix**: `import topic "/missiledefense/tick"` in every packaged file that references an unpackaged topic.
- **evidence**: "Root cause of the dead tick loop: package-scoped topic resolution. Publishers (in `package com.demo.missile`) and the rule (in `package com.demo.missile.SimControl`) each got their topic reference silently prefixed with their own package, landing on two different topics. Fixed with `import topic \"/missiledefense/tick\"` in all three." Verified live after the fix.
- **source**: 8d17deb3-83fd-4a14-8dae-683f3483c49c.jsonl, 2026-08-28

### A topic event carries its payload in `event.value`; `event.newValue` is only on type events

- **id**: NR-19
- **area**: VAIL
- **status**: unverified
- **cost**: minutes
- **symptom**: A rule on `WHEN EVENT OCCURS ON "/topics/..."` reading `event.newValue` gets nothing.
- **cause**: Different event shapes for topic and type events.
- **fix**: Use `event.value` for topic events.
- **evidence**: Session summary only: "the rule passed `event.newValue`, which doesn't exist on topic events (`event.value` is correct) — found via `ArsRuleSnapshot` error records." The snapshot error text was not located, and this may be documented.
- **source**: 8d17deb3-83fd-4a14-8dae-683f3483c49c.jsonl, 2026-08-28

### A `PUBLISH ... TO TOPIC` from VAIL did not reach a WebSocket subscriber, while a REST publish to the same topic did

- **id**: NR-20
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: A browser subscribed to a topic over the WebSocket API receives nothing when a rule publishes, even though the rule's other effects happened.
- **cause**: Not established. Observed on dev.vantiq.com, 1.44, one namespace, one session.
- **fix**: Subscribe to the type's insert/update events instead, which delivered in about one second.
- **evidence**: Raw-socket probe: subscribe frame acknowledged with `"topic":"/topics/triage/escalations"`, then `INSERT status: 200`, then `timeout, closing` with no event frame. The record it should have announced was confirmed `status: 'escalated'`. A direct `POST /resources/topics/...` delivered a frame immediately.
- **source**: 705a2c7c-01cd-4cd0-b7fa-734a9ac86972.jsonl, 2026-08-26

### `INSERT system.collaborations` from VAIL requires `results` and `collaborators`, and `UPDATE` needs `id` inside the body

- **id**: NR-21
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: A VAIL insert fails on a required property that a REST insert of the same shape does not require, then the update resolves the resource id to `null`.
- **cause**: The VAIL path validates fields the REST path defaults, and `UPDATE ... WHERE id ==` does not supply the natural key to the update itself.
- **fix**: Populate `results` and `collaborators` on VAIL inserts, and include `id` in the update object.
- **evidence**: `The property: results is required but has not been assigned a value`; `The resourceId 'null' is not a valid resource identifier`. The first is quoted from the session's autopsy table, the second was also seen live.
- **source**: 705a2c7c-01cd-4cd0-b7fa-734a9ac86972.jsonl, 2026-08-26

### Two `$` operator keys in one VAIL object literal collapse to the last key

- **id**: NR-22
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: A date-range filter written as `{bookdate: {"$gte": start, "$lte": end}}` only applies one bound.
- **cause**: Object-literal construction kept only the last operator key on the nested object.
- **fix**: `{"$and": [{bookdate: {"$gte": start}}, {bookdate: {"$lte": end}}]}`.
- **evidence**: Code comment beside the fixed query: "Two "$" operator keys in one VAIL object literal silently collapse to the last key (the $gte bound was being dropped), so the range must be expressed as an $and of single-operator objects." No session record, so cost is a guess.
- **source**: `PSTracker/Vantiq/PS_Time_Tracker/procedures/com/vantiqse/ps/Project_getProjects.vail`, 2026-07-22

### A service with an explicit interface does not expose a new procedure until it is added to the interface, and a GenAI flow cannot bind to it either

- **id**: NR-23
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: The procedure compiles, but the service reports an error naming it, and any GenAI flow `Procedure` task targeting it reports the procedure "could not be found".
- **cause**: With `hasExplicitInterface`, only listed operations are exposed. Flow task binding resolves through the interface, not procedure existence.
- **fix**: Declare the procedure `WITH updateInterface = true`, or edit the service interface list.
- **evidence**: `{"code":"io.vantiq.service.procedure.no.operation","message":"The service <pkg>.ReportScraper contains the procedure rescrapeParameters which is not part of the declared interface."}`. On the flow: `"The configuration of the task 'handleComponentGeneration' contains an invalid value for the property 'procedure'.  The error was: The requested instance ('<pkg>.ReportGenAgent.handleComponentGeneration') of the procedures resource could not be found."` Both cleared after redeploying with `WITH updateInterface = true`.
- **source**: bcf6d9a9-5c82-4d70-a65f-55c2c0c43694.jsonl, 2026-08-21; 4e557744-fa08-4515-9009-5a225794b40b.jsonl, 2026-08-21

### An explicit service interface pins parameter names; renaming a procedure parameter breaks the service

- **id**: NR-24
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: Renaming `id` to `reportId` on a procedure that compiles clean produces a service-level error.
- **cause**: The interface operation records parameter names independently of the procedure.
- **fix**: Keep the name, or edit the interface entry in the same change.
- **evidence**: `io.vantiq.service.operation.parameter.name: expected parameter named id at position 1, but found reportId`
- **source**: d4e89b2f-b476-4915-8b85-45331dd8d566.jsonl, 2026-08-24

### Creating a Visual Event Handler over REST takes POST, PUT, a service edit, and a second PUT before it leaves `unbound`

- **id**: NR-25
- **area**: service interface
- **status**: verified
- **cost**: hours
- **symptom**: A `collaborationtypes` record with `isEventHandler: true` persists but stays `currentState: unbound` with `resourceBinding: null`, and never fires.
- **cause**: The IDE does two writes: create the handler, and add its path to the owning service's `internalEventHandlers`. `boundService` on the body does not do the second write.
- **fix**: POST, PUT, GET the service, append `/collaborationtypes/<name>` to `internalEventHandlers`, PUT the service with server fields stripped (NR-36), then PUT the handler again. Re-read and check `currentState.code == "complete"`.
- **evidence**: "Two fresh attempts left the CT with `"currentState": {"code": "unbound"}`, `"resourceBinding": null`, and the owning service missing the CT path." An IDE-created reference showed `ars_version: 2`, `compilerOCC: 5`, `currentState.code: "complete"`.
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-21-api-misuse-event-handler-wiring.md`, 2026-04-21; 6e9a934e-2da9-46ac-ba18-0fca8f5220cb.jsonl, 2026-08-28

### Querying a property marked `encrypted: true` returns zero rows with no error

- **id**: NR-26
- **area**: types and data
- **status**: verified
- **cost**: a day or more
- **symptom**: Equality, `IN` and `$regex` against an encrypted field all run cleanly and return nothing, so a search filter looks like "no data". This shipped to production before it was caught.
- **cause**: The literal is compared against ciphertext. No query form works on an encrypted property on this platform version.
- **fix**: Decrypt and match in a procedure, or keep a separate searchable derivative. Written up as a feature request on 2026-08-07.
- **evidence**: User's test doc: "Properties marked `encrypted: true` cannot be used in a query. There's no error — the query runs and silently matches nothing." Side-by-side table: same `==`, `IN` and `$regex` forms returned 1 row on a plaintext field and 0 on the encrypted field, with an id lookup proving the value existed. Repeated in a second session: "Equality and IN compile and run, then silently return nothing ... the control select proves the row is reachable and the query machinery works — but both forms matched zero."
- **source**: 293a4e52-c075-40fa-a395-16425e389e95.jsonl, 2026-08-07; 225b78cd-1505-447c-8bf1-ebe63ae7cdec.jsonl, 2026-08-06

### Reading `system.tokens` no longer returns `accessToken`; only the insert response has it

- **id**: NR-27
- **area**: types and data
- **status**: verified
- **cost**: hours
- **symptom**: A procedure that mints a token once and later selects it by name to build a URL embeds `?token=null`, and the failure shows up as a 401 far away.
- **cause**: On this platform version the token value is only present in the insert response. Whether it was ever returned on read is inferred from the old code having worked.
- **fix**: Mint at the point of use and take `accessToken` from the insert response.
- **evidence**: Old code read live from `system.procedures`: `var token = SELECT ONE * from system.tokens WHERE name == "Next" ... "?token="+token.accessToken`. Diagnosis after live reproduction: "this platform version no longer returns `accessToken` when *reading* `system.tokens`, so the old \"SELECT the Next token, embed in URL\" pattern silently embedded null."
- **source**: ecfab38e-b1bb-4110-9897-e204f0a1769b.jsonl, 2026-08-20

### `expiresAt` on a `system.tokens` insert is not honoured

- **id**: NR-28
- **area**: types and data
- **status**: unverified
- **cost**: minutes
- **symptom**: Tokens created with an expiry stay valid.
- **cause**: Not established.
- **fix**: Delete tokens explicitly.
- **evidence**: Code comment only: "Tokens are created permanent (expiresAt is not honored on insert) and the platform no longer returns accessToken when READING system.tokens, so every run must mint its own token." No probe output found.
- **source**: `<backend repo>/procedures/.../ReportScraper_mintIngestToken.vail`, 2026-08-25

### The `secrets` resource takes its value in a field named `secret`, and never returns it on read

- **id**: NR-29
- **area**: types and data
- **status**: verified
- **cost**: minutes
- **symptom**: `POST /api/v1/resources/secrets` with `{"name": ..., "value": ...}` is rejected, and once created, GET shows only metadata.
- **cause**: The field is `secret`, and reads mask it.
- **fix**: `{"name": ..., "secret": ...}`; keep the value on the client side.
- **evidence**: `"The property: system.secrets.value is not defined."` Create with `secret` returned 200 with metadata only, and GET returned the same.
- **source**: 9ec4a7bb-fd7d-46a0-a708-7e68589aa728.jsonl, 2026-08-20

### System resource REST paths take no `system.` prefix; the error says `system.system.<name>`

- **id**: NR-30
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: `GET /api/v1/resources/system.genaiflows` and `POST .../system.secrets` fail as unrecognised resources, even though the namespace listing labels them under `system`.
- **cause**: The server adds the prefix itself.
- **fix**: `/api/v1/resources/genaiflows`, `/api/v1/resources/secrets`.
- **evidence**: `The resource system.system.genaiflows is not recognized as a Vantiq system resource` (HTTP 500); `"The resource system.system.secrets is not recognized as a Vantiq system resource.  Either correct resource name or adjust access URI/prefix."`
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-22-api-misuse-genai-flow.md`, 2026-04-22; 9ec4a7bb-fd7d-46a0-a708-7e68589aa728.jsonl, 2026-08-20

### For `genaiflows` and `collaborationtypes`, POST stores the body but PUT is what compiles it

- **id**: NR-31
- **area**: REST and MCP
- **status**: verified
- **cost**: hours
- **symptom**: After POST the resource exists with no generated procedure or interface entry and `currentState: unbound`.
- **cause**: The compiler pipeline runs on PUT.
- **fix**: POST, then PUT the identical body.
- **evidence**: `ars_version: 1` after POST, `ars_version: 2` after a same-body PUT, and the state flip described in NR-25. Two independent sessions.
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-22-api-misuse-genai-flow.md`, 2026-04-22; `.../2026-04-21-api-misuse-collaboration-type.md`, 2026-04-21

### POST to an existing `mcpservers` name returns 200 and changes nothing

- **id**: NR-32
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: Redeploying an MCP server definition by POST looks successful and the record is unchanged.
- **cause**: `mcpservers` does not upsert on POST the way `documents` does.
- **fix**: GET by name, then POST to create or `PUT /api/v1/resources/mcpservers/<name>` to update.
- **evidence**: Script header written from the probe: "`mcpservers`: POST against an existing `name` returns 200 but does **not** apply the new field values (verified: a second POST with a different `version` field echoed back the original, unchanged record)." Same probe confirmed `documents` did change on re-POST. Vantiq 1.44.1. The raw HTTP output lives in a subagent transcript that was not recovered.
- **source**: 97a1c5cd-afa5-4b66-a420-fd2c2a1bd2e8.jsonl, 2026-08-31

### "Not found" is HTTP 400 with an error code, not 404

- **id**: NR-33
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: A `status === 404` check never triggers for a missing resource.
- **cause**: Missing `mcpservers` and `documents` resources return 400 with an error array.
- **fix**: Check the body for `io.vantiq.resource.not.found`.
- **evidence**: "**Not-found is HTTP 400**, not 404, with code `io.vantiq.resource.not.found` — the script checks the error code, not the status." Verified live against `GET /api/v1/resources/mcpservers/<missing>` and `.../documents/<missing>/content`, 1.44.1.
- **source**: 97a1c5cd-afa5-4b66-a420-fd2c2a1bd2e8.jsonl, 2026-08-31

### A document's stored name comes from the multipart filename, not the `name` field

- **id**: NR-34
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: You POST `name=probe/deep/nested-doc.md` and get a document called something else.
- **cause**: The `content` part's `Content-Disposition filename` is the name. Slashes are preserved.
- **fix**: Set the desired path as the Blob filename.
- **evidence**: "verified by uploading with `name=probe/deep/nested-doc.md` and a content-part filename of `totally-different-filename.txt`; the stored document was named `totally-different-filename.txt`." 1.44.1.
- **source**: 97a1c5cd-afa5-4b66-a420-fd2c2a1bd2e8.jsonl, 2026-08-31

### The documented `/documents/<name>/content` endpoint returns 400 for an existing document; `/docs/<name>` serves it, with no session

- **id**: NR-35
- **area**: REST and MCP
- **status**: verified
- **cost**: hours
- **symptom**: The content endpoint from the API docs reports not found. The `/docs/<name>` path works with a token, but a page's sub-resource requests 401 because there is no cookie or session.
- **cause**: On 1.44.1 the REST content sub-resource does not serve the document. `/docs/<name>` does, with the document's `fileType` as Content-Type, and every request must carry its own token.
- **fix**: Use `<baseUrl>/docs/<name>?token=...`. Do not try to host a multi-asset static site from documents.
- **evidence**: "not `/api/v1/resources/documents/<name>/content`, which 400s with `io.vantiq.resource.not.found` even for a document that exists — the wiki's documented content endpoint does not work against 1.44.1." "There is no session/cookie mechanism — every request needs its own token."
- **source**: 97a1c5cd-afa5-4b66-a420-fd2c2a1bd2e8.jsonl, 2026-08-31

### PUT of a GET result fails on `_id` unless server-managed fields are stripped

- **id**: NR-36
- **area**: REST and MCP
- **status**: verified
- **cost**: hours
- **symptom**: GET, change one field, PUT back, and the write is rejected on `_id`.
- **cause**: Responses carry `_id`, the `ars_*` audit fields, and compiler outputs (`compilerOCC`, `currentState`, `resourceBinding`, `vailErrors`). Mongo refuses the `_id` rewrite; the effect of echoing the others was not isolated.
- **fix**: Strip `_id`, `ars_version`, `ars_createdAt`, `ars_createdBy`, `ars_modifiedAt`, `ars_modifiedBy`, `ars_namespace`, `ars_relationships`, `compilerOCC`, `currentState`, `resourceBinding`, `vailErrors` before PUT.
- **evidence**: `WriteError{code=66, message='Performing an update on the path '_id' would modify the immutable field '_id'}`, hit three times before the pattern was recognised. Hit again on 2026-08-31 by a migration script doing a full-record PUT against a local Edge: `PUT /api/v1/resources/custom/<pkg>.Pathology/<id>` returned 400 `{"code":"com.accessg2.ag2rs.mongo.error","message":"Op update encountered MongoDB exception: ... WriteError{code=66, message='Performing an update on the path '_id' would modify the immutable field '_id''"}`, fixed by stripping `_id` and `ars_*` from the body.
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-21-api-misuse-event-handler-wiring.md`, 2026-04-21; 44944331-8d7b-4316-b8a7-296fc39cdb16.jsonl, 2026-08-31

### MCP server resources are exposed under a fixed `vantiq://` scheme, and the `mcpservers` REST shape is undocumented

- **id**: NR-37
- **area**: REST and MCP
- **status**: verified
- **cost**: hours
- **symptom**: Nothing in the platform docs gives the JSON for `/api/v1/resources/mcpservers`, and resource URIs are not `<serverId>://<path>`.
- **cause**: Only the IDE flow is documented. The shape was read off a live `io.vantiq.via.mcpServer` instance: `{ name, serverName?, version?, instructions?, resources?: [{name, path, mimeType, description}], resourceTemplates?: [{name, path, description}], tools?, organizationWide? }`. `path` values are bare document names; clients see `vantiq://<path>`.
- **fix**: Copy the shape from a live instance; generate `vantiq://<path>` URIs.
- **evidence**: "confirmed by reading a live MCP server's own `instructions` text, which links to `vantiq://via/common/context/getting-started.md`. The scheme is a fixed `vantiq://`, not `<mcpServerResourceId>://`". "this comment is the only place the shape is written down." 1.44.1.
- **source**: 97a1c5cd-afa5-4b66-a420-fd2c2a1bd2e8.jsonl, 2026-08-31

### REST create bodies for scheduled events, LLMs and rules differ from the obvious shape; `source` on a rule causes a server NullPointerException

- **id**: NR-38
- **area**: REST and MCP
- **status**: verified
- **cost**: hours
- **symptom**: 400s with unhelpful codes, and for rules a 500.
- **cause**: Scheduled events want `{name, active, periodic, interval, topic, message}` with `interval` in milliseconds and at least 1000. LLMs want `type` of `generative` or `embedding`. Rules want the body under `ruleText`, which the server stores as `source`.
- **fix**: Use those bodies. Never send `source` on a rule create or update.
- **evidence**: `400 io.vantiq.scheduledEvent.required.properties — "must specify either a topic or a resource"`; `400 io.vantiq.scheduledEvent.interval.positive`; `400 io.vantiq.llm.type.illegal — "Expected one of embedding, generative"`; `{name, source, active:true} and {name, source} both fail with a server-side NullPointerException (StringTokenizer.<init>)`; `{name, ruleText}` returned 200. dev.vantiq.com, 2026-08-19.
- **source**: 61210183-e701-44e2-9e2b-4eb4fe793483.jsonl, 2026-08-20

### PUT on an `llms` resource merges `config` instead of replacing it

- **id**: NR-39
- **area**: REST and MCP
- **status**: unverified
- **cost**: minutes
- **symptom**: After switching a provider, the old provider's config keys are still present on GET.
- **cause**: Not established beyond the observation.
- **fix**: Delete and re-insert when changing provider.
- **evidence**: Session autopsy only: "After PUT with an OpenAI-only config, GET still showed `azure_endpoint`/`azure_deployment` and `modelName: \"azure-openai\"` (ars_version bumped, config merged)." Raw request and response were not located.
- **source**: 705a2c7c-01cd-4cd0-b7fa-734a9ac86972.jsonl, 2026-08-26

### An access token is bound to the namespace it was minted in and nothing re-scopes it

- **id**: NR-40
- **area**: REST and MCP
- **status**: unverified
- **cost**: hours
- **symptom**: Every attempt to address another namespace with the same token fails.
- **cause**: Tokens are namespace-scoped; the only way found was to switch namespace in the IDE and mint a new one.
- **fix**: Mint a token per namespace.
- **evidence**: Autopsy lists `/authenticate?targetNamespace=`, `?namespace=`, `?nsContext=`, the `X-Vantiq-Namespace` header, `/changeNamespace`, `/currentNamespace` and a JSON body: "all failed to switch." No individual error text was recorded.
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-22-api-misuse-genai-flow.md`, 2026-04-22

### A Python connector reply sent from a background task races the connector's default echo and is dropped

- **id**: NR-41
- **area**: REST and MCP
- **status**: verified
- **cost**: hours
- **symptom**: A procedure querying the connector sometimes gets back only an echo of its inputs, while the work it triggered completes a few seconds later. The caller reports failure on a job that succeeded.
- **cause**: `send_query_response` from a `loop.create_task` coroutine competed with the synchronous default reply to the same query; whichever arrived first closed the query.
- **fix**: Generate the correlation id on the caller side and pass it in, so no reply is needed.
- **evidence**: "I reproduced this live: an `execute` of the procedure returned the echo with no runId, yet the run record appeared and reached `succeeded` 4 seconds later." After the change, "executing with `runId: \"verify-run-passthrough-001\"` produced a run record under that exact id that reached `succeeded`".
- **source**: e26fb283-0241-490f-b098-afd195bb8aaa.jsonl, 2026-08-21

### GenAI flow CodeBlock Python passes compile and fails at runtime under RestrictedPython

- **id**: NR-42
- **area**: agents and LLM
- **status**: verified
- **cost**: minutes
- **symptom**: The flow saves with empty `vailErrors` and every run fails inside the GenAI service container.
- **cause**: RestrictedPython forbids tuple-unpacking assignment and leading-underscore names, and flow validation does not check for them.
- **fix**: Index into sequences instead of unpacking, avoid underscore-prefixed names, and run the flow once before calling it done.
- **evidence**: Connector log: `received an error from the service connector GenAIFlowService: name '_unpack_sequence_' is not defined`. "Notably this one slipped past the flow compiler (`vailErrors` stayed empty) and only failed at execution time inside the GenAI service container."
- **source**: 52b5af17-60da-4406-91d4-02675b4f18d4.jsonl, 2026-08-26

### The `genaiflows` payload uses `assembly`, `children[]`, `positions[taskKey]` and a `subassemblies` array; it shares nothing with the `collaborationtypes` DAG shape

- **id**: NR-43
- **area**: agents and LLM
- **status**: verified
- **cost**: a day or more
- **symptom**: A flow built with `tasks`/`uuid`/`parentStreams`/`childStreams`/`terminals` is rejected or wrong, and sub-flows nested under `config.body` or `config.branches[].body` are ignored.
- **cause**: The real shape has an explicit `io.vantiq.ai.components.InitialInput` node, `serviceName` not `boundService`, `returnType` not `outputType`, and wrapper components (Branch, Map, Loop, Fallback, Optional, Assign, Repeat, Conversation) carry sub-flows in a top-level `subassemblies` array whose entry-node key varies per wrapper.
- **fix**: Export a live instance of the exact resource type and copy it. Do not extrapolate from a sibling type.
- **evidence**: "Our v1 Zod schema nested sub-flows in `config.body` / `config.branches[].body` / `config.primary` / `config.fallbacks[]` — all wrong," corrected against four exported fixtures and four purpose-built test flows.
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-22-api-misuse-genai-flow.md`, 2026-04-22

### `Optional`, `Repeat` and `SemanticIndexWithCompression` throw a server NullPointerException when `subassemblies` is omitted

- **id**: NR-44
- **area**: agents and LLM
- **status**: verified
- **cost**: a day or more
- **symptom**: Flow validation fails with a bare NPE and no field name.
- **cause**: These components require sub-flows and the validator dereferences the missing array. This was first filed as a platform bug and later re-attributed to the builder omitting the array; the missing null guard is real but cosmetic.
- **fix**: Emit one sub-flow for Optional and Repeat, and `documentCompressorCount` compressor sub-flows for SemanticIndexWithCompression.
- **evidence**: `NullPointerException at IComponentValidator.validateSubassemblyCardinality(IComponentValidator.java:82)` via `OptionalValidator$_validate_closure1` and `RepeatValidator$_validate_closure1`; `NullPointerException: Cannot invoke method size() on null object` for SemanticIndexWithCompression.
- **source**: `vantiq-builder/knowledge/autopsies/2026-05-19-vantiq-platform-npes-from-live-suite.md`, 2026-05-19

### Some GenAI component config properties are `unexposable` and cannot be targeted by Repeat, Assign or component exposure

- **id**: NR-45
- **area**: agents and LLM
- **status**: verified
- **cost**: hours
- **symptom**: Saving an exposure that targets a code-block or complex typed property fails.
- **cause**: The runtime component catalog marks such properties `initialConfig[<prop>].unexposable: true`. This flag was not in any docs available.
- **fix**: Check the catalog flag before targeting a property; Boolean, Enum and String keys are safe.
- **evidence**: `Attempting to expose the property "codeBlock" of node CodeBlock, which is not allowed be exposed.`
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-22-api-misuse-genai-flow.md`, 2026-04-22

### A Visual Event Handler VAIL task needs config key `VAIL` and `useEventValue: true`, and `SaveToType` rejects scratch properties on the event

- **id**: NR-46
- **area**: agents and LLM
- **status**: verified
- **cost**: hours
- **symptom**: Using `vailScript` as the key fails compilation. Once compiled, `event` in the script is a wrapper object rather than the payload. A later `SaveToType` fails on properties added by earlier Procedure tasks.
- **cause**: The key is `VAIL`. Without `useEventValue: true`, `event` is `io.vantiq.eventbus.Event`. `SaveToType` validates the event against the target type's closed schema.
- **fix**: Key `VAIL`, `useEventValue: true`, and `deleteKey(event, "...")` for scratch properties before the save.
- **evidence**: `vailScript` "fails compilation: \"missing parameter VAIL\""; without `useEventValue`, "`event` at runtime is the `io.vantiq.eventbus.Event` wrapper, not the payload (\"No such property: X for class: io.vantiq.eventbus.Event\")"; SaveToType "errors \"property X is not defined\"". Quoted from the note written in the session, marked "Live-verified on dev.vantiq.com (1.44, 2026-08-28)". Raw tool output was not re-pulled.
- **source**: 7892723b-7328-499b-a588-433f67e7166c.jsonl, 2026-08-28

### The typed `Procedure` component helper emits a shape the platform rejects

- **id**: NR-47
- **area**: agents and LLM
- **status**: unverified
- **cost**: hours
- **symptom**: A flow built with `procedure: "<name>"` and `parameters: {param: expr}` saves and lands with `vailErrors`.
- **cause**: The platform wants `procedure: {type: "procedures", value: "<name>"}` and `parameters: {code: "return {param: input}", language: "VAIL"}`. This is a bug in a local plugin, but the platform shape is the non-obvious part.
- **fix**: Use the pass-through `{component: "io.vantiq.ai.components.Procedure", config: {<raw shape>}}`.
- **evidence**: Only a memory note recalling a session from 2026-06-11 that is not in the transcripts: "The flow saves but lands with `vailErrors` (Union-type / \"code is required\")." No error body was recovered.
- **source**: 1584634d-4780-4ffe-a7c1-c8941d64f87c.jsonl, 2026-08-26

### Re-saving everything listed by `/resources/procedures` creates namespace-local copies of system-owned procedures

- **id**: NR-48
- **area**: ops and cost
- **status**: verified
- **cost**: hours
- **symptom**: After a "re-POST every procedure to force a recompile" sweep, the namespace holds hundreds of new procedures under services the project never defined.
- **cause**: The listing returns system-owned and inherited records alongside namespace-owned ones, with no `ars_namespace` filter, and POSTing one back materialises a local copy.
- **fix**: Filter the listing on `ars_namespace` before re-saving. Delete copies only after confirming a surviving original.
- **evidence**: Count query by `ars_createdAt` after the sweep: `{"count":522}` new procedures plus 5 rules, by service `ActivityPattern 65`, `Broker 61`, `Deployment 64`, `Test 35`, `Utils 21`. "Cleanup deleted 437 procedure copies and 5 rule copies, each verified against a surviving original first."
- **source**: f2155b10-42b0-4320-9c71-337b54e6d7b7.jsonl, 2026-08-05

### Credit quotas are per Manager; raising `credit.default` does not unblock GenAI 429s

- **id**: NR-49
- **area**: ops and cost
- **status**: verified
- **cost**: hours
- **symptom**: GenAI reads and writes keep returning 429 after the default credit percentage is set to 100.
- **cause**: Quotas are scoped to `ExecutionManager`, `ModelManager`, `RuleManager` and the others; GenAI needs explicit `credit.ExecutionManager` and `credit.ModelManager` entries.
- **fix**: Set those entries in the org quota JSON.
- **evidence**: HTTP 429 `io.vantiq.resource.quota.credit.exhausted` persisted after raising `credit.default.percentage`, and cleared only after the per-Manager entries were added.
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-22-api-misuse-genai-flow.md`, 2026-04-22

### A misspelled quota key (`rates.streams`) is accepted and then breaks every later org read

- **id**: NR-50
- **area**: ops and cost
- **status**: verified
- **cost**: hours
- **symptom**: The quota write succeeds, and every subsequent read of the org config returns 500.
- **cause**: The key is singular `rates.stream`; there is no validation of unknown keys at write time.
- **fix**: Copy the keys from the documented default JSON exactly: `rates.execution`, `rates.stream`, `rates.receiveMessage`.
- **evidence**: `Cannot cast object 'null' with class 'null' to class 'int'` (HTTP 500) on every org read after submitting `rates.streams`.
- **source**: `vantiq-builder/knowledge/autopsies/2026-04-22-api-misuse-genai-flow.md`, 2026-04-22

### A CLI profile's `namespace =` line can disagree with the namespace its token authenticates to

- **id**: NR-51
- **area**: ops and cost
- **status**: verified
- **cost**: minutes
- **symptom**: Resources written with a profile land in a different namespace than the profile file says.
- **cause**: The token decides. The profile field is only a label and had drifted after the profile was repurposed.
- **fix**: Check `ars_namespace` on a throwaway write, or the whoami output, before writing anything with a profile.
- **evidence**: A throwaway secret created through the profile came back with `"ars_namespace":"<other namespace>"`; "Token namespace wins over the profile field."
- **source**: 9ec4a7bb-fd7d-46a0-a708-7e68589aa728.jsonl, 2026-08-20

### `Context.serverUri()` came back without a trailing slash on one deployment

- **id**: NR-52
- **area**: deploy and export
- **status**: unverified
- **cost**: hours
- **symptom**: `Context.serverUri() + "docs/" + path` produced a URL with the host and path run together, and document fetches failed.
- **cause**: Deployment-specific; seen on one hosted instance.
- **fix**: Normalise the base URI before appending.
- **evidence**: Session summary: "Malformed document URL — Context.serverUri() on <deployment> has no trailing slash, so upload built a URL with the host and document folder run together." The malformed URL and the resulting error were not captured verbatim.
- **source**: ecfab38e-b1bb-4110-9897-e204f0a1769b.jsonl, 2026-08-20

### A Deployment fails with `No such property: resourceType for class: java.lang.String` on every retry

- **id**: NR-53
- **area**: deploy and export
- **status**: unverified
- **cost**: a day or more
- **symptom**: Deploying to an Edge instance fails repeatedly with the same Groovy error, and deleting the suspected record does not clear it.
- **cause**: Not established. The working theory was a bare string in the Configuration's resource list where an object was expected, but no live introspection was available and the session ended without a resolution.
- **fix**: None found. The next step recorded was to read the Edge server stack trace.
- **evidence**: User, repeated twice: "still getting Unable to deploy because failed to load resources with error: Encountered exception during execution: No such property: resourceType for class: java.lang.String".
- **source**: fc7fe419-8ce1-4207-b911-8097f9119544.jsonl, 2026-08-05

### Deleting a resource in the git export before deleting it in the namespace brings it back on the next export

- **id**: NR-54
- **area**: deploy and export
- **status**: unverified
- **cost**: minutes
- **symptom**: A file removed and committed reappears after the next export.
- **cause**: The namespace still holds the resource; export is one-directional.
- **fix**: Delete in the namespace, export, then commit.
- **evidence**: Project CLAUDE.md names the commit where the order was reversed and the file "came back". The commit exists and deletes the file, but the reappearance itself is not shown.
- **source**: `<backend repo>/CLAUDE.md`, 2026-08-25

## Gaps

- transcripts scanned: 429 of 429 grepped; 255 had candidate hits (1,710 hits, 841 strong); about 100 hits read in depth across roughly 40 transcripts by nine reader subagents. Repo docs mined: six autopsy files, CLAUDE.md files, and about ten `.vail` comment sites across the Vantiq projects.
- date range: 2026-05-14 to 2026-09-03 for transcripts; repo autopsies add 2026-04-21 to 2026-05-19. Platform versions seen were 1.44.x on dev.vantiq.com and a local Edge install; nothing here was re-tested on a later version.
- concentration: about 60% of all hits, and 27 of the 54 entries, come from one clinical-reporting customer engagement (a Next.js frontend plus a Vantiq namespace with VAIL services, GenAI flows and a Python connector). Most of the rest come from my own tooling repos (a component registry and an MCP builder) and two short demo builds. VAIL findings NR-05 through NR-15 are each a single observation in that one engagement's namespace, so treat them as reproducible reports, not platform rules.
- could not verify: NR-16, NR-19, NR-28, NR-39, NR-40, NR-47, NR-52, NR-53, NR-54 (each states what is missing). NR-13, NR-14 and NR-46 rest on in-session quotations rather than raw tool output. NR-32 through NR-37 come from one live probe on 1.44.1 whose raw HTTP output was in a subagent transcript I could not recover. NR-10 contains an unresolved contradiction between two sessions.
- deliberately excluded: an export/import error for `GenAIFlowService.json` that exists only as a screenshot; the Azure OpenAI concurrency ceiling on GenAI Map nodes (vendor throttling, not Vantiq); `PUBLISH ... TO SERVICE EVENT` only accepting inbound events, `exception()` using `{0}` MessageFormat placeholders, `log.*` using `{}` placeholders, `Array<String>` not being a property type, and resource identifiers rejecting spaces and hyphens, all of which are in the reference docs; the `~/.vantiq/profile` trailing-newline problem, `PUBLISH TO SOURCE` being ignored by the Python Exec connector, and the CLI `-b` flag rejecting underscore hostnames, which only appear as pre-written doc text copied between sessions with no observed failure; everything about Claude Code, pnpm, Next.js, Typst, Docker and the VS Code extension's own code. The 46-item hard-constraints list and 51-rule lint JSON shared by vantiq-builder and claude-code-vantiq were not imported as entries: they are distilled rules written mostly in April 2026, carry no failure records, and a scan of every tool result in the transcripts found the rules' error strings only where the skill text itself had been loaded into a session. The two exceptions with a live failure (`_id` on PUT, bare parameters in `WHERE`) are already NR-36 and NR-13.
- scrubbing: the transcripts contain live access tokens and JWTs in tool output. None are reproduced here. Customer, namespace, username and deployment identifiers are replaced with `<pkg>`, `<ns>`, `<user>`, `<deployment>` or a role.
