> **Redacted for public release.** This file was written for internal pooling
> and is published with customer, namespace and deployment identifiers removed.
> Angle-bracket placeholders (`<pkg>`, `<ns>`, `<namespace>`, `<deployment>`,
> `<installation>`, `<backend repo>`) stand in for names that were here. Vantiq
> platform error codes and `dev.vantiq.com` are kept verbatim, because they are
> what you would search for.

### PROCEDURE headers must use `Name(params): ReturnType` — no `END` terminator, and the return type needs a leading colon

- **id**: NC-01
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: `createProcedure` / `confirmAndExecute` returns a bare, line-less error — `{"error":"Errors found parsing VAIL text:","code":"com.accessg2.ag2rs.parse.errors"}` — for a procedure written in the "textbook" form the platform's own bundled documentation shows (`PROCEDURE Service.name(params) ReturnType ... return x ... END`). The local `validateVAIL` lint check passes this code with zero warnings, so the failure is a surprise.
- **cause**: The real compiler on this platform version does not accept a trailing `END` on a procedure body, and requires a colon before the return type (`(params): ReturnType`, not `(params) ReturnType`). Neither divergence is caught by the offline lint tool.
- **fix**: Write procedure headers as `PROCEDURE Service.name(params): ReturnType` with no `END` terminator on the body.
- **evidence**: Failing form: `PROCEDURE com.example.temperature.AlertService.findOpenAlert(targetSensorId String) Alert\nvar found = SELECT ONE FROM Alert WHERE sensorId == targetSensorId AND status == "open"\nreturn found\nEND` → `{"error":"Errors found parsing VAIL text:","code":"com.accessg2.ag2rs.parse.errors"}`. Working form after the fix: `PROCEDURE AlertService.findOpenAlert(targetSensorId String): Alert\nvar found = SELECT ONE FROM Alert WHERE sensorId == targetSensorId AND status == "open"\nreturn found` → created successfully.
- **source**: 08ceff2b-91cb-4eb2-8f71-8f153d290a5a.jsonl, 2026-08-26

### `PUBLIC` (and presumably `PRIVATE`) as a procedure visibility modifier is a hard parse failure

- **id**: NC-02
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: Same opaque `com.accessg2.ag2rs.parse.errors` failure as NC-01, but isolated to a single token change — everything else (colon return type, no `END`, short service-qualified name) already fixed and working.
- **cause**: Adding a `PUBLIC` visibility modifier in front of `PROCEDURE` breaks the parser outright on this platform version. No modifier is needed — procedures appear callable by default.
- **fix**: Omit visibility modifiers on `PROCEDURE` declarations entirely.
- **evidence**: `PROCEDURE AlertService.pingTest(): String\nreturn "pong"` succeeded. Changing only the first line to `PUBLIC PROCEDURE AlertService.pingTest2(): String` (body unchanged) reproduced `{"error":"Errors found parsing VAIL text:","code":"com.accessg2.ag2rs.parse.errors"}`.
- **source**: 08ceff2b-91cb-4eb2-8f71-8f153d290a5a.jsonl, 2026-08-26

### A multi-segment, package-qualified name in a `PROCEDURE` header can fail to parse even when the short form works

- **id**: NC-03
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: `PROCEDURE <long.dotted.package.Service>.procName(...)` fails with the same generic `com.accessg2.ag2rs.parse.errors`, while `PROCEDURE ServiceName.procName(...)` (short, undotted service reference) compiles.
- **cause**: The `PROCEDURE` header grammar's tolerance for dots in the service qualifier is narrower than the platform's own service-naming rules allow (services themselves can be created with fully dotted, multi-segment names). The exact boundary was not cleanly isolated — a separate engagement saw a 3-segment dotted qualifier parse without complaint (it failed later, at binding, for an unrelated reason) while a 4-segment qualifier here failed immediately at parse time. Don't assume any particular dot count is safe.
- **fix**: When a `PROCEDURE` header won't parse with a dotted service qualifier, retry with the shortest, undotted service name first to isolate whether qualification depth is the problem before investigating anything else.
- **evidence**: `PROCEDURE com.example.temperature.AlertService.pingTest(): String\nreturn "pong"` → `{"error":"Errors found parsing VAIL text:","code":"com.accessg2.ag2rs.parse.errors"}`. `PROCEDURE AlertService.pingTest(): String\nreturn "pong"` → created successfully, same session, same service.
- **source**: 08ceff2b-91cb-4eb2-8f71-8f153d290a5a.jsonl, 2026-08-26

### `Array` and `void` are not valid `PROCEDURE` return-type keywords — they get parsed as type references

- **id**: NC-04
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: A procedure compiles and previews clean, but `confirmAndExecute` comes back with a binding-phase `vailErrors` entry saying a type could not be found — for a return-type keyword, not a real user type.
- **cause**: `Array` and `void` in the return-type position are resolved as ordinary type-name lookups, not recognized as built-in keywords. Since no user `Type` named `Array` or `void` exists in the namespace, binding fails with a "referenced resource not found" error instead of a syntax error.
- **fix**: Omit the return type entirely for procedures that would otherwise return `Array` or `void`, or use `Object` if a type annotation is required.
- **evidence**: `PROCEDURE AlertService.findOpenAlerts(): Array\n...` → `"code": "io.vantiq.rulemgr.vail.referenced.resource.not.found", "message": "The type 'Array' referenced by the procedure 'AlertService.findOpenAlerts' could not be found.  Please either define the type or remove the reference."`. Dropping the `: Array` annotation compiled clean. `void` hit the same failure class on a different procedure in the same session ("`void` isn't resolvable either (same class of problem as `Array`)") — omitting the return type fixed it the same way, though the raw error text for `void` specifically wasn't captured.
- **source**: 08ceff2b-91cb-4eb2-8f71-8f153d290a5a.jsonl, 2026-08-26

### A rule's `WHEN` clause needs an explicit `AS event` alias even for `MESSAGE ARRIVES FROM` — the trigger payload is not implicitly bound to `event`

- **id**: NC-05
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: A rule that reads `event.message` in its body compiles and previews with no lint warnings, but fails at bind time with "use of undeclared variable 'event'" — even though the platform's own bundled documentation example for `MESSAGE ARRIVES FROM` uses bare `event.message` with no alias.
- **cause**: The trigger payload variable is not implicitly named `event`; it must be bound with an explicit `AS <name>` clause on the `WHEN`, the same as is documented for `WHEN EVENT OCCURS ON`.
- **fix**: Always add `AS event` (or another explicit alias) to the `WHEN` clause, regardless of trigger type, and reference that alias in the body.
- **evidence**: `RULE IngestTemperatureReading\nWHEN MESSAGE ARRIVES FROM TemperatureSensorSource\n\nvar payload = event.message\n...` → `"code": "io.vantiq.vail.syntax.error", "message": "use of undeclared variable 'event'"`. Adding the alias — `WHEN MESSAGE ARRIVES FROM TemperatureSensorSource AS event` — with the body otherwise unchanged compiled and ran successfully.
- **source**: 08ceff2b-91cb-4eb2-8f71-8f153d290a5a.jsonl, 2026-08-26

### A Visual Event Handler's package/service name must be a compound (dotted) name — a plain single-word name is rejected

- **id**: NC-06
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: `createCollaborationType` (Visual Event Handler) fails immediately with an explicit, well-formed error naming the exact problem — unlike most VAIL parse failures, which are opaque.
- **cause**: The platform requires VEH/collaboration-type package names to contain at least one package separator (`.`). This is the opposite of the constraint on plain `PROCEDURE` headers (NC-03), where a short, undotted service name is the safe choice — so the two resource kinds can't be reasoned about with a single "always/never use dots" rule.
- **fix**: Give the owning service/package a compound dotted name (e.g. `com.example.TemperatureMonitor`) before attaching a Visual Event Handler to it.
- **evidence**: `"error": "The package name 'TemperatureMonitor' is a simple name.  Packages must be compound names with at least one package separator ('.')."`
- **source**: f24d70a6-0afd-4135-9c7f-6f482f550823.jsonl, 2026 (session spans Jul-Aug)

### `INSERT {...} INTO Type` (object-literal form) fails to parse; the working form is `INSERT Type(field: value, ...)`

- **id**: NC-07
- **area**: types and data
- **status**: verified
- **cost**: minutes
- **symptom**: `var x = INSERT {...} INTO Type` fails with `'{' encountered when parsing VAIL name.` Removing the `var x =` and leaving `INSERT {...} INTO Type` as a bare statement produces the identical error — so the object-literal form itself is the problem, not the assignment.
- **cause**: The real compiler does not accept the `INSERT { field: value, ... } INTO TypeName` object-literal shape at all on this platform version, regardless of whether the result is captured in a variable.
- **fix**: Use the function-call form instead: `INSERT TypeName(field: value, field2: value2, ...)`. To get the created record back (no `RETURNING` clause exists), follow with a separate `SELECT ONE ... WHERE <natural key>`.
- **evidence**: `INSERT {\n    sensorId: targetSensorId,\n    ...\n} INTO Alert` (both as `var created = INSERT {...}` and as a bare statement) → `"code": "io.vantiq.vail.syntax.error", "message": "'{' encountered when parsing VAIL name."`. `INSERT Alert(\n    sensorId: targetSensorId,\n    ...\n)` → compiled and ran clean.
- **source**: 08ceff2b-91cb-4eb2-8f71-8f153d290a5a.jsonl, 2026-08-26

### REST/MCP updates must strip server-managed fields before re-submitting a record — the platform doesn't ignore them cleanly

- **id**: NC-08
- **area**: REST and MCP
- **status**: verified
- **cost**: hours
- **symptom**: A PUT built by taking a fetched resource and sending it back with a small change fails or silently corrupts fields the client didn't intend to touch.
- **cause**: The platform assigns `_id` and the various `ars_*`/binding/compiler fields on save; if a client echoes them back on a PUT, `_id` causes a hard rejection (the backing Mongo store refuses to re-write the immutable `_id`) and the others are either ignored or double-written.
- **fix**: Before issuing a PUT, strip all server-managed fields from the body: `_id`, `ars_version`, `ars_createdAt`, `ars_createdBy`, `ars_modifiedAt`, `ars_modifiedBy`, `ars_namespace`, `ars_relationships`, `compilerOCC`, `currentState`, `resourceBinding`, `vailErrors`.
- **evidence**: Code comment written into the fix itself: `// Strip server-managed/immutable fields before issuing a PUT. Vantiq rejects\n// bodies that carry \`_id\` (Mongo refuses to re-write the immutable _id field)\n// and ignores or double-writes the other \`ars_*\`/binding fields. The platform\n// assigns these on save; clients MUST NOT echo them back.` followed by the literal `IMMUTABLE_FIELDS` list quoted above.
- **source**: f24d70a6-0afd-4135-9c7f-6f482f550823.jsonl, 2026 (session spans Jul-Aug)

### Passing the offline `validateVAIL` lint check is not evidence the real compiler will accept the code

- **id**: NC-09
- **area**: ops and cost
- **status**: verified
- **cost**: minutes
- **symptom**: Code that the local lint tool reports as `"No lint rules triggered"` / zero warnings still fails outright against the live namespace, with no advance warning from the offline check.
- **cause**: The bundled lint-rule catalog checks a narrower set of issues (e.g. it does catch `var`-scoping-inside-`if`) than the real compiler's actual grammar and binding rules. `END` terminators, `PUBLIC` modifiers, and missing-colon return types (NC-01, NC-02) all previewed as lint-clean and then failed hard on `confirmAndExecute`.
- **fix**: Treat a clean local lint pass as necessary but not sufficient. Confirm new VAIL syntax against a real `createProcedure`/`confirmAndExecute` round trip (or an equivalent live compile) before assuming it's correct, especially for syntax copied from static documentation rather than a previously-proven-working example.
- **evidence**: `PUBLIC PROCEDURE com.example.temperature.AlertService.findOpenAlert(targetSensorId String) Alert\n...\nEND` previewed with `{"warningCount": 0, "warnings": []}`, then failed at `confirmAndExecute` with `{"error":"Errors found parsing VAIL text:","code":"com.accessg2.ag2rs.parse.errors"}`.
- **source**: 08ceff2b-91cb-4eb2-8f71-8f153d290a5a.jsonl, 2026-08-26

### A subagent's listed MCP tool set is not proof those tools are actually callable in that invocation

- **id**: NC-10
- **area**: ops and cost
- **status**: verified
- **cost**: hours
- **symptom**: A specialized subagent (architect/builder-style) is dispatched with instructions saying the Vantiq MCP servers are "registered and connected," and its own tool listing includes `mcp__vantiq-agentic__*` / `mcp__vantiq-help__*` entries, but every call to those tools is unavailable — the subagent is left with only generic tools (Read/Grep/Glob) and correctly refuses to fabricate namespace state rather than proceed.
- **cause**: MCP server registration for the Vantiq plugin is scoped per project directory and only takes effect after Claude Code is restarted. A session (or subagent spawned from it) started before that registration completed carries a stale tool list that doesn't match what's actually wired up.
- **fix**: After registering or changing the Vantiq MCP profile for a project, restart Claude Code (or start a fresh session) before dispatching any subagent that depends on `vantiq-agentic`/`vantiq-help` tools — don't trust a tool-list entry as confirmation the underlying server is live.
- **evidence**: Subagent's own report: `"I reviewed my actual tool set for this session, and it is limited to Read, Grep, Glob. There are no mcp__vantiq-agentic__* or mcp__vantiq-help__* tools available to me ... This directly contradicts the task instruction that 'MCP servers vantiq-agentic and vantiq-help are now registered and connected.' From where I sit, that is not true for this invocation."`
- **source**: 08ceff2b-91cb-4eb2-8f71-8f153d290a5a.jsonl, 2026-08-26

### Creating a `system.projects` resource with a `description` property fails outright

- **id**: NC-11
- **area**: deploy and export
- **status**: verified
- **cost**: minutes
- **symptom**: `createProject`-style calls that include a `description` field fail with a schema-rejection error, and every subsequent step that assumed the project existed (attaching sources, services, event handlers, clients to it) then fails too, cascading one root cause into five reported failures.
- **cause**: `system.projects` does not define a `description` property, unlike most other Vantiq resources.
- **fix**: Omit `description` when creating a Project. If a downstream step reports "the requested instance of the projects resource could not be found," check whether the project-creation step itself actually succeeded before debugging the downstream step.
- **evidence**: `"error": "The property: system.projects.description is not defined."` — followed by five cascading `"error": "The requested instance ('{name=<ProjectName>}') of the projects resource could not be found."` failures on the dependent attach calls.
- **source**: f24d70a6-0afd-4135-9c7f-6f482f550823.jsonl, 2026 (session spans Jul-Aug)

## Gaps

- transcripts scanned: 16 of 16 top-level session transcripts on this machine, pattern-matched for compiler errors, tool failures, and correction language; 2 of those (08ceff2b, 234edd2f) read in full manually; targeted-error-scanned in full (not just pattern-sampled) across all 16. 117 subagent sub-transcripts were counted and hit-density-scanned but not individually opened — the 5 subagent files most likely to carry Vantiq-specific findings (under the 08ceff2b session) were covered instead via that session's own task-notification summaries, which relay each subagent's full final report inline.
- date range: 2026-07-15 to 2026-09-03.
- could not verify: the exact grammar boundary for how many dotted segments a `PROCEDURE` header's service qualifier can carry (NC-03) — two sessions gave different-looking results and weren't isolated cleanly enough to state a rule; the raw error text for `void` as an invalid return-type keyword (NC-04) was not captured, only the assistant's contemporaneous note that it hit "the same class of problem as `Array`."
- deliberately excluded: the 8 transcripts and ~112 subagent files from an unrelated clinical-imaging project, by far the largest share of this machine's history. That project's only Vantiq usage is a single stable "generic Access service" pattern (one unchanging service forwarding JSON to an allowlisted SQL dispatcher) that never surfaced a live VAIL compiler error or platform correction in a full-transcript error scan; what that project's history does contain is React/TypeScript/SQL/.NET debugging, which is out of scope here. Also excluded: raw documentation snippets retrieved from the Vantiq plugin's bundled wiki/knowledge-base search tool during these sessions — that content is pre-existing shipped reference material, not something learned firsthand through this history's own trial and error, so it doesn't meet the evidence bar here even where it was accurate.
- everything above comes from effectively one narrow slice of activity: two sessions scaffolding small demo/sandbox apps through the Vantiq Claude Code plugin's architect/builder agents (one MQTT temperature-alert demo, one logistics-industry demo build), plus one longer sandbox session exercising the plugin's own MCP client code and a semantic-index workflow. None of it comes from a production customer engagement, and none of it should be read as broad platform coverage — it's what one person hit while building small demos with one particular toolchain (the `claude-code-vantiq` plugin) over about seven weeks.
