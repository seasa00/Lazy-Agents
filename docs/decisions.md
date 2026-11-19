# AI Office implementation decisions

## D1 — OpenRouter is the first live provider

Date: 2026-10-04

M1.2 uses OpenRouter's OpenResponses-compatible API with strict Structured
Outputs for the first real provider adapter. The standard-library adapter posts
to `https://openrouter.ai/api/v1/responses`, normalizes provider IDs and usage,
and preserves the provider-neutral runtime boundary. Model identifiers are
OpenRouter slugs; the initial example is `openai/gpt-4o-mini`, while the
adapter remains usable with other routed providers.

## D2 — Live integration is explicit and bounded

Date: 2026-10-04

The deterministic mock remains the default. Live use requires explicit CLI
selection, backend-only `OPENROUTER_API_KEY`, a request timeout, and caller-selected
bounded retry/repair budgets. Every submitted attempt is recorded; unknown
usage remains unknown. Structured-output calls set
`provider.require_parameters: true` so OpenRouter routes only to compatible
endpoints.

## D3 — Manager plans are proposals; state commits are deterministic

Date: 2026-10-04

M2.1 keeps the Manager output as a validated proposal. Deterministic planning
code rejects malformed plans, duplicate IDs, missing/self/cyclic dependencies,
and illegal lifecycle changes before the in-memory store commits anything.
Plan approval, task readiness, run uniqueness, entity versions, and domain
events are therefore controlled by Python state transitions rather than model
wording, UI state, or free-form conversations.

## D4 — State and events share the M2.1 store operation

Date: 2026-10-04

The M2.1 store swaps authoritative immutable state and appends its structured
domain events together under one lock. `InMemoryStateStore` is deliberately a
narrow, process-local implementation so the same command/event boundary can be
replaced by SQLite in a later milestone without adding execution-loop or UI
concerns here.

## D5 — Run-owned workflow budgets and operation reservations

Date: 2026-10-04

M2.2 stores counters, attempts, immutable submissions, reviews, acceptance and
pending-operation identity on the run. A deterministic reducer atomically
reserves work and commits results/events; provider IO occurs outside the lock.
Generation checks reject stale results while preserving their usage. Pause
acknowledgment waits for the outstanding call; cancellation cannot undo billing.
Existing runtime attribution is reused with Manager phase schemas and a guard
before each submitted provider request.

## D6 — Conservative scope invalidation and synthetic evidence

Date: 2026-10-04

The preserved Manager schema has no requirement-to-task mapping, so scope or
configuration changes invalidate all current acceptance and require fresh work.
All lifetime counters and evidence history remain. Replanning is permitted only
before approval; executing replacements is deferred rather than allowing task
IDs to reset review safeguards. M2.2 evidence is explicitly synthetic and
captured by a pure in-memory gateway; it does not imply filesystem or shell work.

## D7 — Relational SQLite state with shared commands and external evidence

Date: 2026-10-05

M4.1 extracts the existing memory-store command operations into a shared module;
SQLite replaces their read/commit hooks. This preserves workflow authority without
coupling orchestration to SQL. Current entities/relations are authoritative;
events are append-only history. Typed bounded JSON preserves existing immutable
value contracts within entity rows, with explicit foreign keys between entities.

Reducers and sidecar preparation run before SQL transactions because existing M3
reducers can invoke file/command gateways. Gateway audit sinks independently commit
intent before side effects and outcomes afterward. State and its events then
commit atomically in a short transaction. Captured file evidence/logs are hashed
external files, preserving exact historical bytes without embedding them in SQLite.
File/SQL reconciliation and orphan cleanup remain future work; M4.1 promises clean
shutdown persistence only, for one local application writer.

## D8 — Durable start fences, recovery epochs and operator resume

Date: 2026-10-05

M4.2 distinguishes prepared operations from operations permitted to execute.
The execution fence precedes provider submission, file replacement or command
spawn, so a lost acknowledgment becomes uncertain rather than an implicit retry.
Operation receipts and events are durable independently of workflow admission.

Startup reconciliation marks a recovery gate and inspects evidence without new
external work. A separate recovery epoch fences old results while preserving the
execution generation used by accepted submissions; incrementing that generation
on every ordinary restart would invalidate previously accepted tasks. Explicit
operator resolution and resume are required for interrupted work. Unknown billing
survives abandonment; late receipts enrich effective accounting by call ID without
rewriting the immutable interrupted record. A metadata-only store update records
integrity blockers even when external evidence cannot be loaded. Stale PIDs confer
no process-control authority; unresolved command effects require operator inspection.

## M5.1 — Same-origin browser adapter and snapshot refreshes

The Next.js App Router frontend uses a server route handler to forward allowed
HTTP/SSE requests to loopback FastAPI. Keeping browser requests on one origin
preserves the existing local Host/Origin protections without adding CORS or auth.
The adapter validates the browser Host/Origin before mapping the upstream Origin;
backend credentials remain absent from client configuration. It only forwards
transport and never implements workflow rules. Streaming route handlers use the
standard Request/Response boundary described in the [Next.js route-handler
reference](https://nextjs.org/docs/app/api-reference/file-conventions/route).

Committed DomainEvents are activity/invalidation inputs, while authoritative
snapshots provide task/run state. Existing events do not carry enough complete
entity data to reconstruct state safely in the browser. Serialized, coalesced
snapshot refreshes avoid duplicating orchestration logic. The received-event cursor
is separate from snapshot cursors so a faster snapshot cannot discard later SSE
activity. This adds read traffic under active execution; pagination and richer
read projections remain future work. No advanced state framework is needed.

## M5.2: project configuration applies to newly initialized runs

The settings API persists the existing immutable employee definitions as an
optional field of ProjectState, with existing version checks, durable command
keys and a committed configuration event. Only name, role, model and system
instructions are editable. Applying this configuration at the next run's
initialization preserves the current run's frozen definitions, context/config
fences and recovery validation. An active run is not replanned or generation-reset
by a settings save. Recovered runners reconstruct their captured definitions.

This conservative timing fills the missing configuration surface without adding
workflow semantics or allowing a UI edit to alter an outstanding invocation.
Tools/permission policy and limits remain backend-configured. The UI explicitly
says future **runs**; applying edits between steps of an existing run is unsupported.
Persistence uses the existing allowlisted dataclass codec and optional default,
so existing databases do not need a schema migration.


## M6 — Reference-led layered pixel office, shared authoritative projections

The supplied Lazy Agents mockup supersedes the earlier triangular room layout.
A broad warm office, left-side navigation and compact light dashboard frame the
existing workspace. Manager, Developer and Reviewer sit left to right. Empty
matching room shells and independent transparent character/desk/chair/equipment
atlas layers preserve reusable scene composition. Plants and documents remain
separate assets. Day/Night keeps the same object positions; mobile stacks stations.
Generated artwork and exact prompts are recorded under `features/office/sprites/`.
This change only affects presentation and leaves the approved M6 state contracts
and M5.2 inspection functions intact.

The renderer owns no workflow state. It consumes the existing snapshot status
projection and nonpersistent committed-event visual window. Motion, expiry and
receipt nods cannot issue commands or mutate workflow. Existing M5.2 panels remain
the sole detail/evidence/settings/recovery UI. No second event bus is introduced.
