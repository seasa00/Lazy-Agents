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
