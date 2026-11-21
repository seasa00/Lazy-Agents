# M7.2 orchestrator compatibility

Status: **complete**. Legacy remains the production default. LangGraph is an
explicit opt-in through `make_orchestrator('langgraph', ...)`. Paired scenarios
use separate stores and workspaces; no live run is executed by both paths.

## Boundary and graph

`Orchestrator` matches the existing synchronous runner API. The graph has
`manager_plan`, `manager_assignment`, `developer`, `reviewer`,
`accept_submission`, `manager_revision`, and `finalize` nodes. START and each
node use conditional routing from the latest persisted run. Each node executes
one existing `WorkflowRunner.step` operation. The phase, task, attempt, and
generation fence rejects a stale graph snapshot. Graph nodes introduce no new
agent identity: Manager, Developer, and Reviewer remain the only agents.

```text
START → Manager plan → approval stop
approved → Manager assignment → Developer → Reviewer
Reviewer PASS → Manager acceptance → Manager assignment or finalization
Reviewer FAIL → Manager revision → Manager assignment → Developer → Reviewer
```

The PASS edge is an acceptance candidate. Existing `ReviewRound`, submission,
Manager decision, and final manifest validation commit or reject it. The FAIL
edge still invokes the Manager decision and existing `RevisionBrief` validation.
At three submitted review rounds the domain blocks further revision. Dependency
readiness and next task selection use the existing scheduler.

`WorkflowGraphState` stores only IDs, phase, generation, status, and progress.
SQLite/domain records retain tasks, submissions, reviews, evidence, events,
permissions, limits, and usage. There is no LangGraph checkpointer in M7.2.
The Developer node reuses M7.1 LangChain tools, gateway, and durable command
continuation. Approval waiting ends graph execution; a later invocation loads
the continuation and executes the approved command once. Denial resumes with
a denied tool result and never launches the command. `AgentRuntime` remains the
only LLM accounting writer; gateway and operation records own tool receipts.

## Isolated comparison

| Scenario | Legacy and LangGraph result |
|---|---|
| A — first PASS | Same completed task, immutable submission, exact PASS review, evidence, acceptance, final result, event sequence, and call/token counters. |
| B — FAIL → revision → PASS | Same two immutable submissions and exact reviews, one revision brief, final acceptance, events, and accounting. |
| C — repeated FAIL | Three reviews and submissions, then the same blocked task/run and exhausted limit; no graph loop reset. |
| D — approval | Same durable approval and one settled command, one command receipt, captured test evidence, completion, events, and accounting. Reinvocation creates no second command. |
| E — denial | Same denied approval and zero command results or settled commands; completion uses the denied tool result. |
| F — pause/resume | No provider call while paused; execution resumes at the persisted phase. |
| G — cancellation/stale result | Late Developer result and a stale graph snapshot cannot create a submission or acceptance. |
| H — dependencies | Three dependent tasks are assigned in the same order, after prior acceptance; final evidence references all accepted submissions. |

Malformed Reviewer output blocks without a review or duplicate transition.
For every fixture, retained call records equal actual provider requests; the
graph adds no usage/cost records. Existing event order remains unchanged, so
M6's domain-event consumers continue to receive the same workflow facts.

## Recovery boundary

New graph instances resume from a committed submission and from a pending
approval using the durable domain and M7.1 continuation records. A SQLite
reopen at a committed submission enters the existing recovery pause and
requires explicit operator resume before the graph continues. The graph
never holds an in-memory call stack across approval. The existing operation
fences and recovery coordinator govern uncertain provider, file, and command
outcomes. M7.2 does not add graph checkpoint recovery or claim automatic replay
of uncertain side effects; broader failure hardening remains M7.4.

Verification: `tests/test_m72.py` passed (8 tests); the complete backend suite
passed (488 tests); `git diff --check` passed. No frontend or shared API
contract changed. M7.3 node-level observability has not started.
