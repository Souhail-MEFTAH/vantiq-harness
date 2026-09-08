> **Redacted for public release.** This file was written for internal pooling
> and is published with customer, namespace and deployment identifiers removed.
> Angle-bracket placeholders (`<pkg>`, `<ns>`, `<namespace>`, `<deployment>`,
> `<installation>`, `<backend repo>`) stand in for names that were here. Vantiq
> platform error codes and `dev.vantiq.com` are kept verbatim, because they are
> what you would search for.

# VANTIQ-LEARNINGS-PS

### VAIL rule resource names cannot contain a dot

- **id**: PS-01
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: a rule named `<Service>.<handler>` (matching the service it belongs to) will not save.
- **cause**: the rule/ruleset resource-name grammar rejects `.`; only the dotted service-event path *inside* `WHEN EVENT OCCURS ON "..."` may contain dots.
- **fix**: name rules `<Service>_<handler>` with an underscore (`AlertService_onAnomaly`), keep the dotted path in the `WHEN` clause unchanged.
- **evidence**: repeated forced deviation across independent task reports; distilled in the milestone-2 plan: "VAIL rule resource names cannot contain `.` — use `Service_handler` (underscore). The dotted service-event path inside `WHEN EVENT OCCURS ON` is fine."
- **source**: Vantiq-EDA-Usecase docs/superpowers/plans/2026-08-28-milestone-2-widen-detection.md + task reports in 785a052c-*.jsonl, 2026-08-27/28

### A `package` line in a topic-triggered rule corrupts the event-binding path

- **id**: PS-02
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: a rule with `WHEN EVENT OCCURS ON "/demo/eda/simTick"` compiles but never fires; the stored rule shows an unrecognized-resource error and the internal WHEN-path has been rewritten to something like `/demo.eda/demo/eda/simTick`.
- **cause**: a leading `package demo.eda` statement gets prepended to the topic path in the rule's event binding, so the binding no longer matches the real topic.
- **fix**: create topic-triggered rules with **no `package` line**. (Service-event-triggered rules are unaffected.)
- **evidence**: `{"code":"io.vantiq.rulemgr.vail.resource.unrecognized","message":"The resource associated with the event binding '/demo/eda/simTick' is not recognized."}`; task-8 report: "`onTick` rule's `package demo.eda` was prefixing the topic WHEN-path — removed it (recreated as unpackaged rule, deleted the old one)". ENVIRONMENT.md records the same for `SimulatorService_onRawFeedTick`: "**no `package` line**".
- **source**: Vantiq-EDA-Usecase 785a052c-2dab-47b0-8e6e-b36412a6d1f8.jsonl + vantiq/ENVIRONMENT.md, 2026-08-27

### `random()` throws at runtime in this namespace and silently kills the enclosing handler

- **id**: PS-03
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: a scheduled/handler procedure that calls `random()` produces no downstream effect at all; no VAIL compile error, the pipeline just goes dead.
- **cause**: both `random()` and `random(n)` throw a Groovy cast exception at execution time; the throw aborts the handler before any `PUBLISH`.
- **fix**: do not use `random()` in this namespace; substitute a fixed value or build jitter arithmetically.
- **evidence**: `org.codehaus.groovy.runtime.typehandling.GroovyCastException: Cannot cast object 'null' with class 'null' to class 'int'. Try 'java.lang.Integer' instead`; task-8 report: "`random()` throws 'cast null to int' at runtime in this namespace and silently killed every tick — replaced with `noise = 0.0`."
- **source**: Vantiq-EDA-Usecase 785a052c-*.jsonl (msg 168/171) + subagents/agent-a6b121097e08c3c0f.jsonl, 2026-08-27

### No `dateDiff` / `dateAdd` builtin; a bare call is silently package-qualified and fails at store/compile time

- **id**: PS-04
- **area**: VAIL
- **status**: verified
- **cost**: hours
- **symptom**: `dateDiff(...)` / `dateAdd(...)` passes the `createProcedure` lint gate but the stored resource carries a `vailErrors` entry / throws a compilation error when executed.
- **cause**: the builtins do not exist here, so `dateDiff` resolves to `demo.eda.dateDiff` (a nonexistent procedure in the current package). The lint gate does not resolve identifiers, so it does not catch it.
- **fix**: use the exposed `java.time.Instant` methods — epoch millis via `toDate(ts).toEpochMilli()` (`toDate` accepts a DateTime *or* an ISO-8601 string), epoch seconds via `dt.getEpochSecond()`, backdating via `nowTs.minusSeconds(n)` / `plusSeconds(n)`. Note `.toMillis()` *binds* but throws at runtime: `No signature of method: java.time.Instant.toMillis()`.
- **evidence**: `io.vantiq.rulemgr.vail.referenced.resource.not.found` (121 occurrences across transcripts); ENVIRONMENT.md "Date arithmetic in VAIL (confirmed Task 4)": "This namespace ... has **no `dateDiff` and no `dateAdd` builtin**. A bare `dateDiff(...)` ... is silently package-qualified to `demo.eda.dateDiff` ... and fails at store/compile time ... (lint via `createProcedure` does NOT catch this)".
- **source**: Vantiq-EDA-Usecase vantiq/ENVIRONMENT.md, 2026-08-28

### VAIL reserved words (`rule`, `state`) are rejected as variable/parameter names and lint does not flag it

- **id**: PS-05
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: a procedure written to a spec that used `rule` and `state` as parameter names does not compile on the platform, though `validateVAIL` reported nothing.
- **cause**: `rule`, `state`, `select`, `insert`, `update`, `delete`, `filter`, `map`, `publish`, etc. are reserved; the built-in lint gate does not detect reserved-word identifiers.
- **fix**: rename (`rule` → `detectionRule`, `state` → `sensorState`); calls are positional so downstream contracts hold.
- **evidence**: task-4 report: "param `rule`→`detectionRule` and `state`→`sensorState` (both reserved keywords, not caught by validateVAIL; calls are positional so Task 5 contract holds)"; milestone-2 plan bullet: "VAIL reserved words `rule` and `state` cannot be local var names — use `detectionRule` / `sensorState`."
- **source**: Vantiq-EDA-Usecase 785a052c-*.jsonl task-4 report + docs/superpowers/plans/2026-08-28-milestone-2-widen-detection.md, 2026-08-27/28

### `createProcedure`/`createRule` built-in lint: `single-quotes-invalid` and `var-scoping-in-if` are known false positives, and it never catches missing builtins

- **id**: PS-06
- **area**: VAIL
- **status**: verified
- **cost**: minutes
- **symptom**: every VAIL preview in the agentic session returns 1–2 warnings; `mcp__vantiq-help__validateVAIL` is not available in that session so there is no second opinion.
- **cause**: `single-quotes-invalid` fires on apostrophes inside `/** */` doc comments (e.g. a quoted `'null'` in an error-message comment); `var-scoping-in-if` fires on a `var` deliberately block-scoped to an `if`. Neither is a real defect. The gate also does no identifier resolution, so unknown builtins/procedures pass.
- **fix**: treat those two rule ids as noise when the trigger is a doc comment or an intentional block scope; verify builtins separately (execute the procedure, or check `vailErrors` on the stored resource).
- **evidence**: recurring "Platform learnings ... APPLY" preamble in task reports: "`mcp__vantiq-help__validateVAIL` unavailable — lint = the `createProcedure` built-in gate. single-quote-in-comment / var-scoping-in-if warnings are known FALSE POSITIVES; confirm through them ... Lint does NOT catch missing builtins."
- **source**: Vantiq-EDA-Usecase subagent transcripts under 785a052c-*/subagents/, 2026-08-27/28

### `no sleep()`, `no array.remove(0)` in VAIL

- **id**: PS-07
- **area**: VAIL
- **status**: unverified
- **cost**: minutes
- **symptom**: test/util code using `sleep(...)` or `someArray.remove(0)` does not work.
- **cause**: `sleep()` does not exist; `array.remove(0)` is rejected.
- **fix**: poll with a bounded `for (i in range(0, N))` loop instead of sleeping; rebuild an array with a `range()` loop instead of removing the head element.
- **evidence**: milestone-2 plan bullet only (no error text captured): "No `sleep()` (does not exist — tests use a bounded `for (i in range(0, N))` poll loop). No `array.remove(0)` (rejected — rebuild arrays with a `range()` loop)."
- **source**: Vantiq-EDA-Usecase docs/superpowers/plans/2026-08-28-milestone-2-widen-detection.md, 2026-08-28

### A mid-procedure `return null` does not stop VAIL execution

- **id**: PS-08
- **area**: VAIL
- **status**: unverified
- **cost**: minutes
- **symptom**: a detector written with an early `return null` guard still runs the rest of the body.
- **cause**: reported as lint rule 25 behaviour — an early `return` in the middle of a procedure does not short-circuit.
- **fix**: restructure to hoist all vars above the branch and use a single trailing `return`.
- **evidence**: task-4 report: "mid-procedure `return null` doesn't stop execution in VAIL (lint rule 25) so restructured to a single trailing `return`." No raw error captured.
- **source**: Vantiq-EDA-Usecase 785a052c-*.jsonl task-4 report, 2026-08-27

### A Service with an explicit interface rejects any owned procedure that is not declared in that interface

- **id**: PS-09
- **area**: service interface
- **status**: verified
- **cost**: hours
- **symptom**: adding a helper procedure to a package that owns a service breaks compilation of the *entire* service, not just the new procedure.
- **cause**: when `hasExplicitInterface: true`, every package procedure must appear as a declared operation; an undeclared one is an ERROR-severity binding failure.
- **fix**: either declare the procedure in the interface (which forces `REQUIRED` params + a declared return type on it), or move it out of the service's package.
- **evidence**: `{"code":"io.vantiq.service.procedure.no.operation","message":"The service demo.eda.SimulatorService contains the procedure tick which is not part of the declared interface."}`; ENVIRONMENT.md: "`demo.eda.SimulatorService` has `hasExplicitInterface: true` and rejects any package procedure not declared in the interface with `io.vantiq.service.procedure.no.operation` (severity ERROR, blocks compilation of the whole service)."
- **source**: Vantiq-EDA-Usecase subagents/agent-a74f201515c7bd6fc.jsonl (msg 127) + vantiq/ENVIRONMENT.md, 2026-08-27/28

### Service interface says a param is `required: true` but the VAIL source omits the `Required` keyword → whole service fails to bind

- **id**: PS-10
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: a service that "should" be fine shows `vailErrors` after an interface/procedure sync; the procedures look correct in isolation.
- **cause**: the interface entry and the VAIL declaration disagree on parameter optionality. The platform's own `vailErrors` check catches it; nothing else does.
- **fix**: add `Required` to the VAIL parameter declaration to match the interface (or drop `required: true` from the interface).
- **evidence**: `{"code":"io.vantiq.service.operation.parameter.required","message":"Operation com.vantiqse.demo.DroneControl.sendCommand: expected the parameter command to be required, but found an optional parameter."}`; session note: "declared `required: true` in the service interface but the VAIL source lacked `Required` — caught by `vailErrors`, fixed, verified via live `execute` calls".
- **source**: dev/drone_demo c7990dee-51f6-44b0-92b7-3a65ba1f5448.jsonl (msg 163, 224), 2026-08-07

### An INBOUND service event type with no implementing resource is an ERROR, not a warning

- **id**: PS-11
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: creating a service with an inbound event type before wiring its handler leaves the service in a non-compiling state.
- **cause**: an inbound event type must name an implementing resource (a bound handler); until then it is a checker-phase ERROR.
- **fix**: create and attach the handler in the same change, or add the event type only once the consumer exists.
- **evidence**: `{"code":"io.vantiq.service.eventType.implementation.missing","message":"The event type demo.eda.IngestService.rawReading does not specify an implementing resource."}`
- **source**: Vantiq-EDA-Usecase subagents/agent-a74f201515c7bd6fc.jsonl (msg 29, 34), 2026-08-27

### A rule cannot `PUBLISH` to a service OUTBOUND event; `PUBLISH ... TO SERVICE EVENT` is inbound-only

- **id**: PS-12
- **area**: service interface
- **status**: verified
- **cost**: hours
- **symptom**: a rule that publishes to a `<service>/<event>` outbound event to fan work outward throws at runtime.
- **cause**: `PUBLISH ... TO SERVICE EVENT "<svc>/<event>"` only accepts *inbound* event types. There is no VAIL path to emit an outbound service event from a rule.
- **fix**: make the fan-out seam a Topic (`PUBLISH ... TO TOPIC "/path"`) and have downstream subscribers listen on the topic; reserve outbound service events for service-to-service pipeline hops defined by binding, not by `PUBLISH`.
- **evidence**: wiki gotcha `publish-service-event-inbound-only`: "Throws *'event name must be inbound'* at runtime"; first-hand in RUNBOOK pipeline map: "(a rule cannot PUBLISH a service OUTBOUND event, so the fan-out seam is a Topic)".
- **source**: Vantiq-EDA-Usecase vantiq/RUNBOOK.md + wildfire_demo agent-acc75d84a62d1efd7.jsonl (msg 44), 2026-08-27/30

### A `private` service procedure rejects a direct external `execute`

- **id**: PS-13
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: calling a service procedure via `execute` / `POST /resources/procedures/<fq>` returns a not-visible error even though the procedure exists and compiles.
- **cause**: the procedure is `private` — reachable only from inside the service (e.g. a collaboration-type node), not from an external caller.
- **fix**: expected behaviour for `private`; call it through its intended in-service path, or make it public if it genuinely needs external callers.
- **evidence**: session note: "`Chat.publishResponse` correctly rejected direct external execution (`io.vantiq.rulemgr.vail.procedure.not.visible`) since it is intentionally `private`".
- **source**: dev/drone_demo c7990dee-51f6-44b0-92b7-3a65ba1f5448.jsonl (msg 224), 2026-08-07

### A ScheduledEvent cannot publish to a `/services/<svc>/<event>` path

- **id**: PS-14
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: pointing a scheduled event's `topic` at `/services/demo.eda.SimulatorService/tickRequest` is rejected on save.
- **cause**: the scheduled-event target must be a user-defined topic; a service-event path is not one.
- **fix**: create a plain `topics` resource (e.g. `/demo/eda/simTick`), publish the scheduled event to that, and subscribe the rule via `/topics/demo/eda/simTick`.
- **evidence**: task-7 report: "brief's first choice `/services/demo.eda.SimulatorService/tickRequest` was rejected (\"not a valid user defined topic\") → used fallback plain topic `/demo/eda/simTick`. Required 3 extra steps: create a `topics` resource, subscribe via `/topics/demo/eda/simTick`, and remove the now-unused `tickRequest` INBOUND event type".
- **source**: Vantiq-EDA-Usecase 785a052c-*.jsonl task-7 report, 2026-08-27

### A Service-Builder scheduled procedure's interval must be an even multiple of 60,000 ms

- **id**: PS-15
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: setting a service's scheduled procedure to run every 15 s is rejected.
- **cause**: the minimum scheduling interval for a service scheduled procedure is 60,000 ms and the configured interval must be an even multiple of it. (A standalone `scheduledevents` resource does not have this constraint — 5,000 ms and 10,000 ms intervals were used successfully in the same namespace.)
- **fix**: use an interval that is a multiple of 60,000 ms, or move the cadence to a standalone scheduled event → topic → rule.
- **evidence**: `{"code":"io.vantiq.service.scheduled.invalid.interval.multiple","message":"The interval (15,000 ms) for the procedure com.vantiq.ps.wildfire.EscalationService.ActiveCollabsWriteAll is not an even multiple of the minimum scheduling interval (60,000 ms)."}`
- **source**: wildfire_demo 77a1b2cc-9241-4e54-b7e3-c0a35d9ab879.jsonl, 2026-08-31

### `createScheduledEvent` publishes a message to a topic — it cannot invoke a procedure

- **id**: PS-16
- **area**: service interface
- **status**: verified
- **cost**: minutes
- **symptom**: expecting a scheduled event to "call" a procedure directly; nothing runs.
- **cause**: a scheduled event only publishes its `message` to its `topic`. Something else has to react. There is no `ruleToFire` field.
- **fix**: pair every scheduled event with a rule: `WHEN EVENT OCCURS ON "/topics/<path>"` that calls the procedure.
- **evidence**: milestone-1 plan, first-hand: "`createScheduledEvent(...)` — it **publishes `message` to `topic`**; a rule reacts to that topic. It cannot call a procedure directly."
- **source**: Vantiq-EDA-Usecase docs/superpowers/plans/2026-08-27-milestone-1-vertical-slice.md:44, 2026-08-27

### Deleting/fetching a record by resource id requires the Mongo `_id`, not your `naturalKey`

- **id**: PS-17
- **area**: types and data
- **status**: verified
- **cost**: minutes
- **symptom**: `getResource` / `deleteResource` with your business key (`"INC-001"`, `"smm-baseline"`) returns an invalid-identifier error.
- **cause**: the resource-id path parameter is the `_id` property's value; a `naturalKey` value is not accepted there.
- **fix**: `SELECT` the row by its natural key first, read `_id`, then address the record by that; or operate by query (`UPDATE ... WHERE naturalKey == ...`).
- **evidence**: `{"code":"io.vantiq.dbservice.invalid.identifier","message":"The value 'INC-001' given as a resource identifier is not legal. Please confirm that you have supplied the contents of the _id property."}` (recurred with `'smm-baseline'`).
- **source**: wildfire_demo 77a1b2cc-9241-4e54-b7e3-c0a35d9ab879.jsonl, 2026-08-31

### This namespace has no data-generator Source implementation type

- **id**: PS-18
- **area**: types and data
- **status**: verified
- **cost**: hours
- **symptom**: a plan that calls for a "data generator / simulated feed" Source cannot be built — there is no such `sourceimpl`.
- **cause**: `listResources({ resourceType: "sourceimpls" })` returns only `SMS, EMAIL, AMQP, KAFKA, CHATBOT, EXTENSION, MOCK, MQTT, PUSH_NOTIF, REMOTE, GCPS, VIDEO`; `createSource` only accepts `REMOTE/MQTT/AMQP/KAFKA/GCPS/EMAIL/SMS/VIDEO/CHATBOT`.
- **fix**: fall back to a scheduled event → rule → procedure that publishes synthetic messages into the same inbound event the real feed would use, so swapping in a real Source later is a no-downstream-change edit.
- **evidence**: ENVIRONMENT.md "RawSensorFeed external vendor feed (Task 11)": quotes the full `sourceimpls` enumeration and the `createSource` accepted list verbatim; "No Source resource was created."
- **source**: Vantiq-EDA-Usecase vantiq/ENVIRONMENT.md, 2026-08-28

### `rulesSuppressed` defaults on for new types, which kills the type-CRUD live-update path

- **id**: PS-19
- **area**: types and data
- **status**: unverified
- **cost**: hours
- **symptom**: a browser subscribed to `/types/<fq>/insert|update` receives nothing for a type whose rows the VAIL is clearly writing.
- **cause**: `rulesSuppressed` is on by default; with it on, writes do not raise CRUD events, so nothing is delivered to subscribers.
- **fix**: set `rulesSuppressed: false` explicitly on every type whose insert/update must reach a subscriber; leave it `true` (the quiet default) only on high-volume types nothing subscribes to.
- **evidence**: design/schema docs treat it as a known hazard and set the flag explicitly on every type — "hazard: default-on silently kills the type-CRUD push path" — but no observed failure is in the transcripts; this was designed around, not hit.
- **source**: wildfire_demo docs/wildfire-type-schemas.md + agent-ae59920b4ddc2c195.jsonl, 2026-08-31

### `mcp__vantiq-agentic__executeProcedure` with an empty `service` string silently creates a stray service resource

- **id**: PS-20
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: after running a bare procedure through the agentic MCP with `service: ""`, a junk service of the same name as the procedure appears in the namespace.
- **cause**: the empty `service` argument is interpreted as "create/address a service", not "no service".
- **fix**: for package-level procedures call `mcp__vantiqVIA__execute` with the fully-qualified name only; never pass `service: ""` to `executeProcedure`. Stray services are inert but must be deleted by hand.
- **evidence**: task-5 and task-6 reports: "`mcp__vantiq-agentic__executeProcedure` with `service:""` created a stray service resource"; codified as a warning in both CLAUDE.md and RUNBOOK: "Do NOT pass an empty `service` ... (creates stray services)."
- **source**: Vantiq-EDA-Usecase 785a052c-*.jsonl task reports + vantiq/RUNBOOK.md §8, 2026-08-27

### `mcp__vantiq-help__validateVAIL` is not available inside the Vantiq agentic MCP session

- **id**: PS-21
- **area**: REST and MCP
- **status**: verified
- **cost**: minutes
- **symptom**: the documented pre-submit VAIL validation step cannot be run; only the `createProcedure`/`createRule` preview's built-in lint is available.
- **cause**: the `vantiq-help` server / `validateVAIL` tool is not loaded in the agentic session used for building.
- **fix**: rely on the create-preview lint gate plus an actual `execute` (or a `vailErrors` read on the stored resource) for anything the gate cannot see (missing builtins, reserved words); see PS-06.
- **evidence**: recurring task-report preamble: "`mcp__vantiq-help__validateVAIL` unavailable — lint = the `createProcedure` built-in gate."
- **source**: Vantiq-EDA-Usecase subagent transcripts under 785a052c-*/subagents/, 2026-08-27/28

### VAIL `PUBLISH ... TO TOPIC` does not reach WebSocket subscribers

- **id**: PS-22
- **area**: UI and documents
- **status**: verified
- **cost**: a day or more
- **symptom**: a browser client subscribed to a topic over the Vantiq WebSocket never receives the messages a VAIL rule publishes to that topic.
- **cause**: topic publishes from VAIL are not delivered to WebSocket subscribers on this platform lineage (confirmed empirically, and consistent with `publish-service-event-inbound-only` blocking the outward path too).
- **fix**: make a database write the delivery mechanism — subscribe the client to type CRUD events (`/types/<fq>/insert|update`) or `system.collaborations` insert/update, and have the VAIL `INSERT`/`UPSERT` the row that carries the state change. CRUD/collaboration events deliver in ~1s with the full instance as `event.value`.
- **evidence**: code comment at `wildfire_demo/src/lib/notifications/NotificationsProvider.tsx:142`: "Subscribed to type CRUD rather than `PUBLISH TO TOPIC` because topic publishes don't reach WebSocket subscribers on the Vantiq platform (verified empirically); `system.collaborations` insert/update events deliver in real time (~1s) and carry the full instance as `event.value`".
- **source**: wildfire_demo src/lib/notifications/NotificationsProvider.tsx + 2c7c1d66-f188-49df-869a-e21893a7396b.jsonl, 2026-08-30

### A VAIL wrapper around a GenAI procedure defeats streaming

- **id**: PS-23
- **area**: agents and LLM
- **status**: verified
- **cost**: hours
- **symptom**: a chat endpoint that routes the GenAI call through a thin VAIL `send` procedure returns the whole answer at once instead of streaming tokens.
- **cause**: any user VAIL sitting between the GenAI flow procedure and the HTTP layer materialises the entire token sequence before returning.
- **fix**: make the GenAI Procedure itself the direct call target from the client. GenAI Procedures always take exactly `input (Any)` and `config (Object)`, which matches a `{input, config}` call site.
- **evidence**: code comment at `wildfire_demo` `ChatService.ts:145-149`: "then the generated GenAI flow procedure `SubmitChatPrompt` is streamed directly. Any user VAIL between the flow and the HTTP layer (like the old `send` wrapper) materializes the full token sequence before responding, so the flow procedure must be the direct target."
- **source**: wildfire_demo agent-acc75d84a62d1efd7.jsonl (msg 144/146), 2026-08-31

### Turning on the GenAI-Agent (A2A) checkbox auto-creates a *separate* dispatch LLM and an empty secret

- **id**: PS-24
- **area**: agents and LLM
- **status**: unverified
- **cost**: hours
- **symptom**: after enabling "GenAI Agent" on a service, agent discovery works but every dispatch fails — even though the service's own `OpenAI` LLM resource holds a valid key.
- **cause**: the checkbox auto-creates its own `io.vantiq.a2a.agentDispatch` LLM (default `openai/gpt-4.1`) and a `VANTIQ_A2A_SECRET` that ships **empty**. The dispatch path uses that secret, not your LLM resource's credential.
- **fix**: populate `VANTIQ_A2A_SECRET` with a valid provider key before testing discovery/dispatch.
- **evidence**: assistant analysis in-session, drawn from the platform knowledge base rather than an observed dispatch failure: "`VANTIQ_A2A_SECRET` — Auto-created **empty**. Must be populated with a valid OpenAI API key or dispatch fails ... the A2A secret is a distinct store and ships blank".
- **source**: wildfire_demo 2c7c1d66-f188-49df-869a-e21893a7396b.jsonl (msg 213) + agent-acc75d84a62d1efd7.jsonl, 2026-08-31

## Gaps

- transcripts scanned: 129 of 129 (grep pass over every `~/.claude/projects/**/*.jsonl`); ~40 read closely around hits, plus first-hand defect logs in `Vantiq-EDA-Usecase/vantiq/ENVIRONMENT.md`, the two milestone plans, `RUNBOOK.md`, and `wildfire_demo/src/**` code comments.
- date range: 2026-06-02 to 2026-09-03.
- concentration: this history is dominated by **one namespace**, `<namespace>` (a sensor-anomaly / tsunami EDA app), built 2026-08-27/28 across a large subagent fan-out. a wildfire-detection demo (`<namespace>`, 2026-08-30/31) is the second source. Several entries (PS-03, PS-04, PS-09) are explicitly scoped by their own authors to "this namespace" and may be environment- or version-specific rather than platform-wide. The drone demos, a real-time video/mobile project, and a wearables-integration project contributed almost no server-side VAIL learnings (mostly LiveKit, Docker, and React work).
- could not verify: PS-07 (`sleep()` / `array.remove(0)` — plan bullet only, no error text or failing/fixed code captured); PS-08 (mid-procedure `return null` — assertion referencing "lint rule 25", no raw error); PS-19 (`rulesSuppressed` default — designed around as a hazard, never observed failing in a transcript); PS-24 (`VANTIQ_A2A_SECRET` — knowledge-base-sourced in-session analysis, no observed dispatch failure).
- deliberately excluded: wiki / `searchDocs` / knowledge-base "gotcha" content that appears in transcripts only as retrieved reference (e.g. `SELECT` returns a Sequence not an Array under `FOR`/`MAP`/`FILTER`; single-quotes-invalid as a real rule; `import metadata` is schema-only; `Concurrent.Map` has no subscript assignment) — none of these were watched failing here, and a lint tool built on exactly this kind of unwitnessed rule produced 166/166 wrong findings. Also excluded: in-memory service state is lost on redeploy/restart (documented, predictable — a fact, not a learning), and async-service-event test flakiness handled with retry×3 (predictable consequence of documented async semantics).
