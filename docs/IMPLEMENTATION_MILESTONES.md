# AI Office — Implementation milestone roadmap

Status: planning only. No milestone has been implemented by creating this document.

Architecture source of truth: [AI_OFFICE_BLUEPRINT.md](../AI_OFFICE_BLUEPRINT.md).

This roadmap sequences that architecture into independently reviewable increments. It does not replace the blueprint or authorize starting implementation. Complete and review one sub-milestone before starting the next. M6 and M7 are each single milestones.

## Delivery principles

- Exactly three employee kinds: Manager, Developer, Reviewer. The Developer occupies the blueprint's Worker position; it is not a fourth agent. Keep the configurable specialization/role separate from the workflow position. Use one canonical naming convention in contracts and document this mapping in M1.1.
- One active run across the application, one active task execution, and sequential agent invocations. The three employees are identities, not three continuously running processes.
- The Manager proposes decisions; deterministic Python code validates and applies them.
- Agents exchange structured briefs, submissions, reviews, and decisions through shared state. They do not exchange entire conversation histories.
- The Reviewer cannot change the Developer's output. Every review refers to a specific submission version.
- Token and estimated-cost attribution begin with the first provider integration. SQLite durability comes later without changing those records' meaning.
- Default review limit: three total review rounds, allowing the initial review and two revisions. Infrastructure retries are counted separately and also bounded.
- Do not claim filesystem or command isolation stronger than the implementation provides. Approved project commands execute trusted local code; an allowlist is not an OS sandbox.
- Automated tests use deterministic provider responses and controlled tools. Live-provider checks are explicit, bounded, and separately reported; the default test suite must not require credentials or spend money.
- Keep every completed gate runnable. Before a browser exists, use a small development CLI/harness, not a throwaway second application.
- No Redis, Kubernetes, microservices, distributed workers, vector database, agent marketplace, multi-user authentication, agent browser automation, or game engine. Browser-based UI tests are test infrastructure, not an agent capability.

## Sequencing changes and reasons

| Decision | Placement | Reason and trade-off |
|---|---|---|
| Typed state, event envelopes, and storage boundary | M2, before SQLite | Prevents orchestration from depending on an in-memory implementation. Use only a narrow interface needed by the workflow, not a generic repository framework. |
| Pause, cancellation flags, execution generations, and retry limits | M2; extended in M3–M4 | Real file tools must not arrive before execution can be bounded and interrupted. M7 hardens these controls rather than introducing them. |
| Real file and command experiments | M3, disposable workspaces only | Proves tools independently of persistence. Until M4 recovery passes, this is not suitable for valuable personal workspaces. |
| Cost calculation | Basic in M1.2; durable aggregation in M4.1 | Usage and estimates must be attributable from the first real call, even before a dashboard or database exists. |
| Baseline restart recovery | M4.2, before frontend work | A browser-controlled application should not lose history or blindly replay side effects after a restart. |
| Snapshot API and baseline SSE | M4.3, before M5 and M6 | Both the functional UI and office visualization need the actual event stream. Avoid a temporary polling UI and a later transport rewrite. |
| Editable employee/provider settings UI | M5.2 | Early milestones use validated configuration files and backend-only credentials. A settings UI is not needed to prove agent behavior. |
| Office styling and animations | M6 | Task evidence, controls, and backend recovery must work before visual polish. |
| Comprehensive failure matrix and release verification | M7 | Exercises already implemented guarantees together. It must not become a place to postpone basic correctness. |

The blueprint's full schema and frontend are introduced progressively. Pre-M4 in-memory history is explicitly temporary. No production durability is implied during those milestones.

## Review gates and shared Definition of Done

Every milestone below must satisfy its own Definition of Done **and** this shared gate:

1. Only the current milestone's implementation is included; no future-feature scaffolding beyond a necessary interface.
2. Its acceptance criteria pass, relevant existing regression tests still pass, and its documented entry point runs from a clean setup.
3. The manual verification procedure is performed and its actual result recorded. Report separately any live-provider check not performed and why; do not call a required live integration gate complete without it.
4. Known limitations are explicit, especially temporary in-memory state and trusted-command execution.
5. No credentials, user secrets, generated workspaces, or runtime databases are committed.
6. Update the contract documentation, concise session handoff, and verification record described below.
7. Stop for review. Do not begin the next milestone automatically. Revisions requested during review remain part of the current milestone.

Tests should prove meaningful behavior and boundaries, not mirror method implementations. Avoid snapshotting nondeterministic model prose. Live checks assess structure, attribution, and usable behavior rather than requiring a model to produce an exact sentence or a particular accidental defect.

## Context management and documentation

Paths below are proposed future paths, not files created by this planning task:

- `API` = `apps/api/app/`
- `TESTS` = `apps/api/tests/`
- `WEB` = `apps/web/src/`

Every future implementation session reads:

1. Its milestone section in this roadmap.
2. `docs/CURRENT_MILESTONE.md`, if it exists.
3. Only the cited sections of the blueprint and relevant sections of `docs/contracts.md`.
4. The explicitly listed implementation modules and their tests.

"Not needed" below means normally unnecessary context, not a prohibition on reading a dependency when a concrete issue requires it. Do not read the whole repository by default. Read source at an interface boundary before changing that interface.

Create these documents during the milestones that first need them, then maintain them incrementally:

| Document | Purpose |
|---|---|
| `docs/CURRENT_MILESTONE.md` | Latest completed gate, implementation status, current interfaces, evidence, limitations, and next handoff; target roughly 80–120 lines |
| `docs/contracts.md` | Compact index of public contracts, invariants, owning modules, and relevant tests; source schemas remain authoritative |
| `docs/decisions.md` | Short entries for material implementation decisions, with blueprint references |
| `docs/verification.md` | Per-gate commands, actual outcomes, manual checks, environment prerequisites, and live-provider verification status |
| `README.md` | Current supported setup and execution path; no future capabilities presented as implemented |

At the end of **every** milestone, update `CURRENT_MILESTONE.md`, the relevant contracts, and `verification.md`; update decisions and README when applicable. An empty or planned test is not a passing test.

### Planned handoff format

```markdown
# Current milestone

## Status
Last completed gate:
Review status:
Next proposed gate:

## Implemented
Concrete capabilities and relevant paths.

## Architectural decisions
New decisions and links to durable explanations.

## Current contracts
Public interfaces, owning files, versions, and invariants to preserve.

## Verification
Commands run, actual results, manual checks, and live-provider status.

## Known limitations
Missing capabilities, safety boundaries, and unresolved issues.

## Next milestone handoff
Read these files; preserve these interfaces; next bounded objective.
```

Do not create a misleading completed handoff during planning. M1.1 creates the first implementation handoff after its work is verified.

---

## M1 — Agent Core

### M1.1 — Agent contracts and isolated runtime

**Goal:** Independently invoke each of the three employee kinds with appropriate context and validate its result using a deterministic test provider.

**Why this milestone exists:** Role boundaries and structured output should be testable before provider behavior or workflow scheduling complicates diagnosis.

**Scope:** Minimal Python package/test setup; configurable employee definitions; role-specific context selection; a provider interface; a shared invocation runtime; validation errors; context/configuration manifests; a development command that invokes one selected agent against fixtures. Provider doubles belong in testing/development support and are visibly labeled.

**Expected modules/files:** `apps/api/pyproject.toml`; `API/domain/agents.py`; `API/agents/contracts.py`; `API/agents/runtime.py`; `API/context/builder.py`; `API/providers/base.py`; `API/dev/cli.py`; `config/agents/`; `TESTS/agents/`; `TESTS/fixtures/`; initial README and documentation described above. These may start as small files rather than elaborate packages.

**Key contracts/data structures:** `AgentDefinition`; canonical three-kind enum; separate specialization/role; `ContextPolicy`; `ContextManifest`; `AgentInvocation`; Manager plan/decision/final-result schemas; Developer submission schema; Reviewer result and criterion findings; normalized provider request/response/error types. Tool calls may be represented as data, but no real tool executes.

**Tests:** Three valid outputs; missing/extra/invalid fields; Reviewer verdict validation; context restricted by role; missing essential context reported rather than silently truncated; configuration snapshots unaffected by later edits; no implicit conversation-history sharing.

**Manual verification:** Invoke Manager, Developer, and Reviewer separately with labeled fixture input. Inspect the context manifest and structured result. Feed malformed output and confirm a typed error without execution or hidden retries.

**Acceptance criteria:** All three agents can be exercised independently. Validation failures are actionable. No agent has undeclared tools, and no invocation performs a real file mutation, command, or provider request.

**Explicitly NOT included:** Live LLM integration, orchestration, real tools, database, FastAPI endpoints, frontend.

**Definition of Done:** Shared gate plus a reproducible offline demonstration of all three role contracts and their negative cases.

**Dependencies:** Existing blueprint only.

**Context handoff:** Read blueprint §§6, 8–10, 15 and this gate. No frontend, database, or tool implementation is needed. Preserve the three-role separation and structured context boundary. Update contracts for agent/provider interfaces and record the canonical Developer/Worker naming mapping.

### M1.2 — One provider, bounded calls, and usage attribution

**Goal:** Each agent works independently with one real LLM provider, with validated output and attributable usage.

**Why this milestone exists:** Proves the abstraction against a real provider before the workflow relies on it.

**Scope:** One provider adapter; backend-only credentials; declared capabilities; output validation and bounded repair; request timeouts; bounded transient retries; token normalization; basic decimal cost estimation from configured rates. Extend the CLI to select a live provider explicitly. Choose and document the initial provider here, using the user's available credentials and required capabilities.

**Expected modules/files:** `API/providers/<chosen_provider>.py`; `API/usage/records.py`; `API/usage/pricing.py`; `API/agents/runtime.py`; `API/dev/cli.py`; `config/model-pricing/`; `.env.example`; `TESTS/providers/`; `TESTS/usage/`; opt-in live smoke checks.

**Key contracts/data structures:** `ProviderCapabilities`; `LLMCallRecord`; usage provenance/completeness; input/output/cached-token categories; price snapshot; request and invocation IDs; typed provider failures; per-invocation call budget. Failed or canceled calls can have unknown usage rather than fabricated zero cost.

**Tests:** Provider response normalization; unsupported capability rejection; invalid structured result; retry exhaustion using a fake clock; each retry recorded separately; cached-token overlap; unknown pricing; missing credentials; secrets excluded from ordinary logs. Default tests make no real network calls.

**Manual verification:** Configure one provider and invoke each role on a bounded fixture. Inspect structured output and per-call usage/cost. Run a deterministic rate-limit/error fixture and inspect the retry count. Record live-call results without committing credentials or sensitive payloads.

**Acceptance criteria:** Three separate real invocations return validated role outputs. Every submitted provider request has a call record, including retry attempts. Unsupported models fail clearly. Unknown billing information is labeled.

**Explicitly NOT included:** Multi-provider implementation, workflow execution, tools, durable usage storage, usage dashboard, model routing, budget optimization.

**Definition of Done:** Shared gate plus successful live verification for all three roles and deterministic failure/retry tests.

**Dependencies:** M1.1.

**Context handoff:** Read M1.1 contracts, `providers/base.py`, runtime, context builder, relevant tests, and blueprint §§15, 17–18. No orchestration, database, or frontend source is needed. Preserve role schemas and provider-neutral errors. Update contracts with usage semantics and README with credential setup and explicit live-check commands.

---

## M2 — Orchestration

### M2.1 — Shared state, planning, and legal transitions

**Goal:** Turn a Manager plan into approved, dependency-valid tasks in structured in-memory project state.

**Why this milestone exists:** Scheduling correctness needs a deterministic model independent of model wording and later database details.

**Scope:** Project/run/task models; task and agent states; requirements and decisions; plan approval; dependency validation; task readiness; one active run; event envelopes; a narrow state-store interface and in-memory implementation. The Manager proposes plans; the workflow validates and commits them. Select the next ready task without executing the full agent loop yet.

**Expected modules/files:** `API/domain/projects.py`; `API/domain/tasks.py`; `API/domain/events.py`; `API/orchestration/transitions.py`; `API/orchestration/planning.py`; `API/persistence/store.py`; `API/persistence/memory.py`; CLI extensions; `TESTS/orchestration/test_planning.py`; `TESTS/persistence/test_store_contract.py`.

**Key contracts/data structures:** `ProjectState`; `RunState`; `Task`; `Requirement`; `Decision`; dependency edges; `DomainEvent`; entity versions; configuration snapshot; approve-plan command. State changes and associated events are one logical store operation, implemented atomically in memory and later in SQLite.

**Tests:** Reject cycles, self-dependencies, missing prerequisites, duplicate identifiers, invalid transitions, unapproved execution, and a second active run. Test dependency readiness and consistent state/event updates. Ensure canceled tasks are not counted as completed.

**Manual verification:** Generate or load a plan with dependent tasks, inspect it, approve it, and print the ready task. Submit a cycle and inspect the rejection. Attempt to start another run.

**Acceptance criteria:** Readiness and legal transitions have deterministic outcomes. A plan cannot execute before approval. Scheduling never depends on UI state or unrestricted agent conversation.

**Explicitly NOT included:** Complete Developer/Reviewer loop, real tools, SQLite, crash recovery, HTTP API, frontend.

**Definition of Done:** Shared gate plus repeatable planning/dependency demonstrations and store-contract tests usable by M4.

**Dependencies:** M1.2.

**Context handoff:** Read agent output contracts, blueprint §§6–12 and 17, and new domain/store tests. Provider adapter internals and pricing arithmetic should not need rereading. Preserve provider/runtime interfaces. Document transition guards, event semantics, and the minimal store boundary; state explicitly that history is still in memory.

### M2.2 — Complete workflow and bounded human controls

**Goal:** Complete Manager → Developer → Reviewer → revision or acceptance → final result using controlled tools.

**Why this milestone exists:** Establishes workflow reliability before agents can alter real files.

**Scope:** Deterministic execution loop; approved task dispatch; synthetic immutable submissions; review routing through Manager; revision briefs; acceptance and finalization checks; review and technical retry limits; invocation/run/task-creation/replanning limits; pause/block/resume; instructions at safe boundaries; cancellation flags; generation-based stale-result rejection. Controlled in-memory tools implement the future gateway interface.

**Expected modules/files:** `API/orchestration/runner.py`; `API/orchestration/controls.py`; `API/orchestration/limits.py`; `API/agents/runtime.py`; `API/tools/contracts.py`; `API/domain/submissions.py`; `API/domain/reviews.py`; `TESTS/orchestration/`; controlled-tool fixtures; CLI run/control commands.

**Key contracts/data structures:** `TaskAttempt`; `SubmissionManifest`; `ReviewRound`; `ReviewResult`; `RevisionBrief`; `ExecutionLimits`; `ToolRequest/Result`; `Intervention`; execution generation; blocked reason/resume phase; final result with evidence references. Technical errors remain distinct from a valid FAIL verdict.

**Tests:** Initial PASS; FAIL→revision→PASS; persistent FAIL→BLOCKED exactly at the limit; Manager cannot bypass failed criteria; missing evidence; malformed reviews; dependency ordering; exhausted call/replan limits; pause at boundaries; resume without duplicate assignment; cancel and late result; stale submission review; changed requirements invalidating affected acceptance. Reopening/replacing tasks cannot reset cumulative run safeguards.

**Manual verification:** Run three scripted scenarios: PASS, FAIL then PASS, and repeated FAIL. Pause a slow fixture, verify no new operation starts, resume it, then test cancellation and a late response. Run one bounded live-provider workflow with controlled tools after deterministic tests pass.

**Acceptance criteria:** Only the orchestrator applies transitions. The Reviewer never modifies a submission. Review rounds default to three total, technical retries do not add quality rounds, and limits persist for the lifetime of the run. Completion requires accepted current submissions for all required tasks.

**Explicitly NOT included:** Real filesystem tools, subprocesses, restart durability, web API, frontend.

**Definition of Done:** Shared gate plus all controlled end-to-end scenarios and the live controlled-tool smoke check. The backend workflow is demonstrable without UI.

**Dependencies:** M2.1.

**Context handoff:** Read domain/state/store contracts, role outputs, runtime, blueprint §§3, 6–10, 15, 17, and workflow tests. No provider-specific networking code or frontend source is normally needed. Preserve M1 attribution and M2.1 event/state semantics. Document counters, cancellation versus pause, and which interrupted scenarios await persistence.

---

## M3 — Developer Tools & Permissions

### M3.1 — Workspace file tools and immutable submissions

**Goal:** Let the Developer read and change a disposable real workspace through enforced permissions, then let the Reviewer inspect a captured submission.

**Why this milestone exists:** Separates filesystem boundary correctness from the additional risks and lifecycle of commands.

**Scope:** List/read/write/edit tools; workspace root validation; traversal/symlink protection; protected paths; output-size bounds; expected-hash conflict checks; role-specific gateway permissions; file-operation records; changed-file manifests/diffs and captured review evidence. Check pause/cancel state before each mutation. Keep runtime artifacts outside agent-writable project content.

**Expected modules/files:** `API/tools/files.py`; `API/tools/gateway.py`; `API/permissions/policy.py`; `API/tools/submissions.py`; `API/domain/artifacts.py`; controlled runtime wiring; `TESTS/tools/test_files.py`; `TESTS/permissions/`; temporary workspace fixtures.

**Key contracts/data structures:** `WorkspacePolicy`; `PermissionDecision`; resolved path; expected content hash; `ToolCallRecord`; file-change record; immutable artifact reference; submission content hashes. Reviewer reads the captured evidence, not whichever bytes happen to be in the live workspace later.

**Tests:** Valid list/read/edit; traversal and absolute-path escape; symlink escape; protected-secret/application paths; denied Reviewer mutation; denied Manager mutation; conflicting external edits; oversized reads/results; cancellation before write; submission stability after live files change. Document any unresolved filesystem race limitations rather than claiming hostile-process isolation.

**Manual verification:** Copy a tiny fixture into a disposable workspace. Let Developer make one change and submit it. Inspect the diff and Reviewer evidence. Attempt an outside-root write and a Reviewer edit; verify denials and unchanged target files. Edit a captured source file afterward and verify the stored submission stays unchanged.

**Acceptance criteria:** Every file operation passes through the gateway and has an attributable outcome. Denied mutations do not alter files. Reviewer evidence identifies the reviewed version. No arbitrary personal directory is used for validation.

**Explicitly NOT included:** Terminal/commands, package installation, deletion tool, deployment, OS sandbox, durable audit log, valuable workspace use.

**Definition of Done:** Shared gate plus passing boundary/conflict tests and one real-file implementation/review demonstration without command execution.

**Dependencies:** M2.2.

**Context handoff:** Read tool contracts, execution-control boundary, submission models, blueprint §§9–10, 15–17, and permission tests. Provider HTTP code, future SQL schema implementation, and frontend are unnecessary. Preserve orchestrator-only transitions and read-only Reviewer authority. Document file permissions, snapshot contents, and the temporary in-memory operation history.

### M3.2 — Approved commands, test evidence, and tool limits

**Goal:** Run explicitly approved development commands and attach their results to the reviewed submission.

**Why this milestone exists:** Useful development needs verifiable command evidence, but command execution must have explicit authorization and bounded behavior.

**Scope:** Structured executable/argument requests; scoped approval/denial; approved working directory and environment; time/output limits; one command at a time; process cancellation/cleanup; exit-code/stdout/stderr capture; tests as an approved command profile; evidence tied to the workspace/submission version tested. Surface unverified criteria accurately.

**Expected modules/files:** `API/tools/commands.py`; `API/tools/gateway.py`; `API/permissions/policy.py`; `API/orchestration/controls.py`; `API/tools/submissions.py`; `TESTS/tools/test_commands.py`; `TESTS/integration/test_workspace_workflow.py`; harmless local command fixtures.

**Key contracts/data structures:** `CommandRequest`; approval scoped to executable, arguments, working directory, and relevant version; pending permission intervention; `CommandResult`; timeout/cancellation outcome; test evidence with run time, exit status, log reference, and content-version association.

**Tests:** Denied/unapproved command; approval mismatch; safe argument passing without shell expansion; working-directory escape; restricted environment; output truncation; timeout; stop during execution; descendant cleanup on the supported local OS; pause before launch; failed test evidence; file changes after tests making evidence stale. Reviewer receives no command authority by default.

**Manual verification:** Complete a small fixture implementation with an approved test command. Deny another request and inspect the block reason. Run a harmless slow command, stop it, and inspect the process outcome. Verify a Reviewer can read the submission and test evidence without editing files or rerunning commands.

**Acceptance criteria:** No unrestricted shell is exposed. Every request and approval decision is recorded, including denial. A terminated process is not reported as successful. Stale test results cannot silently establish acceptance of different content. The full workflow changes and reviews real files in a disposable workspace.

**Explicitly NOT included:** Network/deployment/email tools, automatic dependency installation, Reviewer command execution, guaranteed OS-level containment, persistence/restart guarantees.

**Definition of Done:** Shared gate plus command lifecycle tests and one real-provider small-project smoke run with bounded approved tools. Repeated FAIL scenarios remain deterministic test fixtures, not a requirement that the live model make a mistake.

**Dependencies:** M3.1.

**Context handoff:** Read gateway/policy, controls, submission/evidence contracts, blueprint §§15–17, and subprocess tests. No frontend or provider adapter internals are needed. Preserve call accounting and tool result contracts. Document trusted-command limitations, supported OS, cleanup behavior, and exact manual approval flow.

---

## M4 — Persistence & Observability

### M4.1 — SQLite state, event history, and durable accounting

**Goal:** Persist complete workflow history and usage without changing the established orchestration behavior.

**Why this milestone exists:** State, tool outcomes, and cost must survive process exit before the application becomes a personal working tool.

**Scope:** SQLite schema/migrations; concrete store implementation; projects, agents, runs, tasks, dependencies, attempts, reviews, decisions, artifact metadata, invocations, LLM/tool calls, interventions, and events; transactional state/event writes; stable sequences; durable call attribution and aggregates; tool intent persisted before execution. Keep file artifacts on disk with database metadata.

**Expected modules/files:** `API/persistence/sqlite.py`; `API/persistence/models.py`; `API/persistence/store.py`; `apps/api/migrations/`; `API/usage/aggregation.py`; runtime/gateway persistence wiring; `TESTS/persistence/`; `TESTS/usage/`; `data/` ignore rules.

**Key contracts/data structures:** Existing domain records mapped to SQLite; migration version; event sequence; atomic state-and-event commit; durable call IDs; unique intervention keys; active-run constraint; artifact hash/reference; price snapshot. Current tables remain authoritative; events are an append-only history, not the sole reconstruction mechanism.

**Tests:** Run existing store-contract/workflow cases against SQLite; constraint violations; transactional rollback; state/event atomicity; reopen database and compare history; unique active run; recorded tool intent; missing artifact detection; decimal cost aggregation; duplicate record handling; unknown usage/pricing; schema migration on test databases.

**Manual verification:** Complete a disposable run, exit cleanly, reopen its database through the CLI, and inspect tasks, reviews, events, artifacts, and per-agent costs. Compare aggregates to individual call records. Confirm no credentials or protected file contents leaked into ordinary records.

**Acceptance criteria:** Clean shutdown preserves all committed history. Aggregates reconcile with call records. A state transition and its event cannot persist independently. Orchestration does not contain SQL or depend on the concrete SQLite adapter.

**Explicitly NOT included:** Automatic crash resume, full interruption recovery, SSE, browser UI, multiple writer processes, event-sourced reconstruction, budget enforcement.

**Definition of Done:** Shared gate plus SQLite/store parity, clean-restart history verification, and persisted tool-intent records ready for reconciliation.

**Dependencies:** M3.2.

**Context handoff:** Read store contract, domain records, usage records, gateway operation boundaries, blueprint §§9–12, 17–18. Agent prompts and frontend are unnecessary. Preserve event/usage semantics and acceptance rules. Update contracts with transaction boundaries, migrations, artifact storage, and remaining crash-recovery limitations.

### M4.2 — Restart reconciliation and durable execution controls

**Goal:** Recover safely from an interrupted backend without losing history or blindly repeating side effects.

**Why this milestone exists:** Durable rows alone do not establish whether a model request or tool actually completed.

**Scope:** Persisted phase checkpoints; startup reconciliation; interrupted invocation/tool states; explicit resume; durable limits/generations; permission and instruction state; uncertain outcomes; artifact consistency checks; controlled reconciliation decisions. Identify tracked processes conservatively and never kill an arbitrary reused PID. Resume only from a reconciled safe phase.

**Expected modules/files:** `API/orchestration/recovery.py`; `API/orchestration/controls.py`; runner/checkpoint updates; `API/persistence/sqlite.py`; gateway operation-status updates; `TESTS/recovery/`; controlled crash/failure fixtures; CLI inspect/reconcile/resume commands.

**Key contracts/data structures:** `ExecutionCheckpoint`; operation outcome certainty; interrupted status; durable blocked reason/resume phase; reconciliation result; execution generation; idempotent control command. An unknown provider charge remains unknown; cancellation does not erase usage.

**Tests:** Restart before tool execution, after mutation but before outcome persistence, during a provider call, while paused, during review, and after committed completion. Verify no blind mutation retry, no automatic unsafe continuation, stable review limits, no duplicate completed task, stale-generation rejection, and missing/corrupt artifact blocking.

**Manual verification:** Use a disposable fixture and controlled failure points to interrupt a run during a file operation and during a slow provider/tool call. Restart, inspect the interrupted state and evidence, resolve uncertainty, explicitly resume, and confirm prior changes are neither lost nor blindly repeated. Use deterministic fixtures for destructive timing tests.

**Acceptance criteria:** Every unfinished operation is classified or visibly unresolved. Restart never silently launches new work. Committed history and attempt counts survive. Uncertain side effects block until reconciliation rather than assuming success or failure.

**Explicitly NOT included:** Exactly-once external side effects, automatic rollback, automatic recovery of all crashes, distributed leases/workers, frontend.

**Definition of Done:** Shared gate plus controlled restart tests proving the documented safe recovery contract. This is a mandatory gate before browser development.

**Dependencies:** M4.1.

**Context handoff:** Read runner/controls, SQLite transaction methods, gateway intent/outcome records, blueprint §§3, 12, 16–18, and recovery tests. Agent prompt text, pricing internals, and UI code are unnecessary. Preserve recorded history and uncertain-usage semantics. Document exact restart behavior and the user's reconciliation choices.

### M4.3 — FastAPI control surface and baseline SSE

**Goal:** Expose the validated backend through typed HTTP commands, consistent snapshots, and durable live events.

**Why this milestone exists:** The frontend must control one authoritative backend and consume committed execution facts from its first version.

**Scope:** One FastAPI process and supervised execution loop; create/open projects; plan/approve/start; inspect tasks, agents, evidence, usage, settings; pause/resume/stop/cancel; permissions/instructions/scope changes; snapshot plus cursor; SSE replay, keepalives, duplicate handling contract, and reconnect recovery. Backend runs independently of request/stream lifetimes. Bind locally and restrict origins/hosts and mutation access without introducing multi-user accounts.

**Expected modules/files:** `API/main.py`; `API/api/projects.py`; `API/api/runs.py`; `API/api/events.py`; `API/api/settings.py`; `API/api/schemas.py`; `TESTS/api/`; `TESTS/integration/test_event_stream.py`; documented OpenAPI/type-generation boundary.

**Key contracts/data structures:** `ProjectSnapshot` with consistent event cursor; command acknowledgment with pending/applied/rejected status; idempotency key; expected entity version; artifact access references; redacted settings views; SSE schema/version and event IDs. Active `Last-Event-ID` governs reconnection; unavailable cursors trigger a defined snapshot reset flow.

**Tests:** Typed API validation; duplicate control requests; stale-version conflicts; one active run; snapshot/stream race; events arriving during replay; reconnect from cursor; duplicate delivery; unavailable cursor; disconnect not canceling execution; slow reader not blocking work; protected artifact paths; credential redaction; rejected origins/mutations.

**Manual verification:** Use API docs or a small HTTP client to create, plan, approve, run, pause, and resume a fixture project. Observe SSE while work occurs. Disconnect and reconnect the stream, then verify the final snapshot and usage. Confirm the API responds while an agent or command is running.

**Acceptance criteria:** The complete backend workflow is operable through HTTP. Snapshots and replay cannot miss committed updates. Commands are acknowledged separately from eventual state changes. Real provider/tool work continues correctly without an open browser connection.

**Explicitly NOT included:** Frontend, office animation, WebSocket transport, external hosting, multi-user authentication, comprehensive failure-combination polish reserved for M7.

**Definition of Done:** Shared gate plus API-driven end-to-end verification and baseline replay tests. Backend correctness, tool permissions, durability, and live updates are ready before UI work starts.

**Dependencies:** M4.2.

**Context handoff:** Read application/service interfaces, event/store contracts, recovery behavior, blueprint §§12–14, 16, 20. Provider internals and tool implementation details should not need rereading. Preserve workflow authority, snapshot consistency, and backend-only credentials. Document API/SSE contracts and supported local startup commands.

---

## M5 — Functional Web UI

### M5.1 — Browser-operated project workflow

**Goal:** Create, approve, run, inspect, and control a project from a functional browser interface.

**Why this milestone exists:** Proves the product's core interaction without spending effort on decorative office scenes.

**Scope:** Next.js/TypeScript setup; project list/create/open; goal/requirements entry; editable plan approval; task board and task details; real activity feed; basic agent summaries; visible run controls; permission/input prompts; final result; consistent snapshot loading and one SSE connection per project view. A small reducer/context store is sufficient.

**Expected modules/files:** `apps/web/package.json`; `WEB/app/`; `WEB/features/projects/`; `WEB/features/tasks/`; `WEB/features/activity/`; `WEB/features/runs/`; `WEB/lib/api/`; `WEB/lib/events/`; `WEB/lib/state/`; frontend contract/reducer tests and browser integration tests.

**Key contracts/data structures:** Generated or derived TypeScript API types; snapshot/event reducer; selected project/task; pending command state; connection state. Backend task, agent, and run states remain authoritative. The board displays IDs, assignees, dependencies, and review counts.

**Tests:** Snapshot plus event application; duplicate event delivery; initial load racing with events; pending pause versus acknowledged pause; rejected command; stale-version refresh; plan edits; permission denial; final result; refresh restoring a project. Browser end-to-end tests use a deterministic backend provider fixture.

**Manual verification:** From the browser only, create a project, enter requirements, review/edit and approve the plan, grant or deny a scoped command, observe a revision, pause/resume, and inspect the final result. Refresh during execution and verify authoritative state is restored.

**Acceptance criteria:** No manual API calls are needed for this workflow. The UI never infers task completion from timers. Disconnection is visible, execution persists independently, and all board/activity changes come from actual backend state/events.

**Explicitly NOT included:** Illustrated office, handoff animations, elaborate styling, rich code editor, full settings/cost drill-down, backend workflow redesign.

**Definition of Done:** Shared gate plus browser end-to-end verification against the actual backend and established SSE transport.

**Dependencies:** M4.3.

**Context handoff:** Read API/SSE contracts and backend API tests, blueprint §§3–5, 13–14, and new frontend modules. No provider, SQLite, or subprocess implementation is normally needed. Preserve all backend controls and event identity/version semantics. Document frontend state ownership and current browser workflow.

### M5.2 — Evidence, employee details, usage, and settings

**Goal:** Make the browser workflow useful for supervised personal development, including inspecting evidence and understanding cost.

**Why this milestone exists:** A run button and task board are not enough to decide whether to trust, revise, or stop the work.

**Scope:** Agent detail panels; task attempts and review findings; structured sent/received messages; tool logs; artifact/diff inspection; final result links; total/per-agent token and cost display; call/review/retry counts; project and application settings; supported employee/model/permission configuration; interrupted-run reconciliation controls backed by M4.2.

**Expected modules/files:** `WEB/features/agents/`; `WEB/features/artifacts/`; `WEB/features/usage/`; `WEB/features/settings/`; task/recovery panels; UI tests; browser integration scenarios. Backend changes are limited to filling necessary read/view contract gaps, not changing workflow rules.

**Key contracts/data structures:** Agent detail projection; attempt/submission/review references; artifact/log view models; usage completeness and price provenance; redacted credential/configuration forms; pending configuration changes; recovery decision acknowledgment. Settings changes apply to future invocations, preserving existing configuration snapshots.

**Tests:** Correct submission shown for each review; unknown cost displayed without false zero; no duplicated totals on SSE replay; secret values absent from browser responses; denied permission cannot be enabled by UI alone; interrupted state and explicit resume; keyboard access to panels; baseline readable layouts at narrow widths.

**Manual verification:** Finish one small real-provider project in a dedicated workspace using only the browser. Inspect a file change, test evidence, review, and per-agent usage. Change an employee setting and verify its next-invocation behavior. Restart during a controlled fixture, inspect the interrupted run, reconcile, and resume from the UI.

**Acceptance criteria:** The user can understand what changed, what was checked, what remains uncertain, and what it cost without opening the database or using API tools. Required human interventions and baseline restart recovery are accessible from the browser.

**Explicitly NOT included:** Office scene, animation, integrated IDE, multi-user features, alternative Worker specializations, budget optimization, speculative analytics.

**Definition of Done:** Shared gate plus a fully browser-operated real-project check and a controlled restart/recovery check. This is the recommended first supervised personal-use release.

**Dependencies:** M5.1.

**Context handoff:** Read frontend state/API/event interfaces and backend evidence/usage/recovery contracts, blueprint §§4–5, 9, 16, 18, 20. No provider HTTP or SQL implementation is normally needed. Preserve immutable evidence and backend-owned permissions. Update README with supported personal-use workflow and limitations.

---

## M6 — AI Office Experience

**Goal:** Represent actual execution as an office containing exactly three employees and their workspaces.

**Why this milestone exists:** Adds the project's distinctive product experience after the underlying workflow is useful and observable.

**Scope:** CSS/SVG office layout; Manager, Developer, and Reviewer desks; status labels/current tasks; clickable employee panels; event-driven task/message handoffs; blocked/error indicators; responsive layout; keyboard access; reduced motion. Connect the office to the existing frontend state and event acknowledgment layer.

**Expected modules/files:** `WEB/features/office/OfficeScene.tsx`; `AgentDesk.tsx`; `HandoffLayer.tsx`; office styles/assets; agent-panel integration; `WEB/lib/events/` only where live-animation classification is needed; component and browser tests.

**Key contracts/data structures:** `OfficeViewModel` derived from canonical agent/task state; handoff visual reference keyed by committed event ID; connection/replay state. No independent simulated employee lifecycle. Replay updates state without reanimating historical handoffs; a slow animation never delays execution.

**Tests:** Exactly three employee positions; event-to-status/handoff mapping; no handoff for rejected commands; duplicate/replayed events do not repeat animation; reduced motion; keyboard interaction; connection loss indication; task/status details match the board. Component fixtures are clearly development fixtures, not a production activity generator.

**Manual verification:** Observe a real run and compare desk statuses, task board, and activity entries. Use a deterministic failure/revision fixture to inspect Reviewer → Manager → Developer routing. Disconnect/reconnect and refresh; verify correct state without historical animation playback. Navigate the office using only a keyboard and enable reduced motion.

**Acceptance criteria:** Every visible execution status and handoff traces to backend state or a committed event. The office remains understandable with animation disabled. No fake/random activity is generated, and the underlying functional UI stays usable.

**Explicitly NOT included:** Game engine, free-roaming characters, 3D world, idle work simulation, new agent kinds, new backend capabilities, elaborate asset production.

**Definition of Done:** Shared gate plus visual/event consistency and accessibility checks. The portfolio's distinctive office experience works on the already validated product.

**Dependencies:** M5.2, including M4.3 live-event foundations.

**Context handoff:** Read frontend event reducer, agent panels, status projections, blueprint §§5, 8, 13–14. Provider, orchestration, tools, and database internals should not need reading. Preserve canonical state ownership and event identity. Document animation triggers, replay suppression, and reduced-motion behavior.

---

## M7 — Real-Time & Reliability Polish

**Goal:** Validate the complete application against ordinary failures and make its personal/portfolio release reproducible.

**Why this milestone exists:** Integration exposes timing and recovery defects that component-level tests cannot fully establish. This phase fixes evidence-backed issues rather than introducing deferred core guarantees.

**Scope:** Full fault-injection matrix; SSE interruption/replay/reset; repeated browser refresh; pause/resume/stop/cancel races; provider timeouts/rate limits/malformed output; interrupted tools and backend restarts; stale-result protection; persistence and usage reconciliation; multi-tab control conflicts while preserving one active run; accessibility regressions; local startup and release instructions.

**Expected modules/files:** `TESTS/integration/`; `TESTS/recovery/`; frontend/browser end-to-end tests; test failure-injection helpers; targeted fixes only in affected modules; `docs/verification.md`; `docs/decisions.md`; README and a small sample project fixture. Avoid broad refactors unrelated to demonstrated failures.

**Key contracts/data structures:** Preserve all prior public contracts. Clarify existing recovery/reset outcomes when needed; any unavoidable change is documented, versioned where appropriate, and tested against its consumers. No parallel workflow engine or new persistence model.

**Tests:** Exercise the release matrix below across backend and browser. Verify each fault leaves a terminal, paused, recoverable, or explicitly blocked state with an explanation. Run normal offline regression suites and one bounded opt-in live-provider project. Check that cost, task counts, and review counters reconcile after replay/restart.

**Manual verification:** Install from clean local instructions. Complete a small project. During deterministic fault scenarios, disconnect the browser, refresh repeatedly, pause during a slow call, cancel during a command, restart at an uncertain side-effect boundary, and resume after reconciliation. Inspect retained evidence and final usage.

**Acceptance criteria:** No silent loss of committed history; no automatic duplicate side effect after an uncertain interruption; no stale result advancing a canceled/revised run; no replay-induced duplicate UI action or cost increment; no infinite retry loop; no new work after pause acknowledgment until resume. Any unavoidable uncertainty is visible and actionable.

**Explicitly NOT included:** Distributed correctness, high-scale load infrastructure, remote hosting, enterprise authentication, support for every OS/provider, new features, or claims of guaranteed exactly-once external execution.

**Definition of Done:** Shared gate plus completed release matrix, documented actual results and remaining limits, clean-install verification, and a reproducible demonstration of the blueprint's end-to-end acceptance scenario.

**Dependencies:** M6 and every earlier gate. Reliability defects discovered earlier must be fixed in their current gate, not postponed to M7.

**Context handoff:** Read public contracts, current handoff, verification record, blueprint §§3, 12, 14, 16–18, 20, and the failing scenario's modules/tests. Do not initially read the whole repository; expand only along the observed failure path. Update the handoff with release status, verified guarantees, known limitations, and the next proposed work rather than assuming a new milestone is authorized.

### Release verification matrix

| Scenario | Required observation |
|---|---|
| First submission passes | Manager accepts current evidence and advances or completes |
| FAIL then PASS | Feedback flows through Manager; new submission is reviewed; prior evidence remains inspectable |
| Review limit exhausted | Task blocks at configured limit without hidden counter resets |
| Provider failure/retry | Bounded requests and attributable records; uncertainty represented |
| Permission denied | No denied action executes; user sees a resolvable reason |
| Conflicting external file edit | Existing content is not silently overwritten; evidence is reassessed |
| Pause during a call/tool | Pausing is distinct from Paused; no next operation begins after acknowledgment |
| Cancel with a late response | Old result cannot advance state; usage is retained |
| Restart near a file mutation | Intent/outcome reconciliation; no blind replay |
| Restart during review | Correct submission and review-round history remain linked |
| Snapshot followed by SSE | No committed update is missed between initial load and subscription |
| Disconnect/reconnect/replay | Current state converges; activity/cost/animations are not duplicated |
| Unavailable event cursor | Defined snapshot reset and continued stream |
| Two tabs send controls | Idempotency/version checks prevent conflicting duplicate execution |
| Missing/corrupt artifact | Review or resume blocks visibly rather than fabricating evidence |
| Final result after restart | Requirements, accepted submissions, usage, and summary remain inspectable |

## When the application becomes useful

| Point | Practical status |
|---|---|
| M1.2 | Agent technical prototype: individual live invocations work |
| M2.2 | Workflow prototype: coordination and limits work with controlled tools |
| M3.2 | Real development demonstration: disposable workspace only; restart durability is not established |
| M4.3 | Usable backend for a technical user comfortable with CLI/API; permissions, history, recovery, and live events exist |
| **M5.2** | **Best first personal-use release:** complete supervised browser workflow with evidence, controls, usage, and baseline recovery |
| M6 | Distinctive visual office suitable for a portfolio demonstration |
| M7 | Hardened personal/portfolio V1 with verified failure behavior and repeatable setup |

M5.2 is the best point to begin using AI Office for small, supervised personal projects in dedicated workspaces. M6 adds the visual identity; it is not a prerequisite for usefulness. M7 increases confidence through full-system verification. Valuable projects still deserve normal version control/backups and the documented trusted-command boundary.

## Compact roadmap

```text
M1  Agent Core
    M1.1 Contracts and isolated runtime
    M1.2 One provider, bounded calls, usage
 ↓
M2  Orchestration
    M2.1 Shared state, planning, transitions
    M2.2 Complete workflow and bounded controls
 ↓
M3  Tools & Permissions
    M3.1 Workspace files and submissions
    M3.2 Approved commands and test evidence
 ↓
M4  Persistence & Observability
    M4.1 SQLite history and accounting
    M4.2 Restart reconciliation
    M4.3 FastAPI snapshots, commands, baseline SSE
 ↓
M5  Functional Web UI
    M5.1 Browser-operated workflow
    M5.2 Evidence, usage, settings, recovery  ← First personal-use release
 ↓
M6  AI Office Experience
 ↓
M7  Real-Time & Reliability Polish          ← Hardened portfolio V1
```

There are 13 review gates. Each leaves a working, testable increment and a concise handoff for the next implementation session. The first implementation request should cover M1.1 only.
