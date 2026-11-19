# M7.1 compatibility record

Deterministic paired fixtures in `apps/api/tests/test_m71_parity.py` run the
trusted legacy Developer entrypoints and the LangChain adapted Developer with
the same workspace, configured command profile, Manager, Reviewer, and domain
orchestrator. Random record IDs and model prose are excluded from comparisons.

| Scenario | Legacy outcome | Adapted outcome | Domain result | Intentional difference | Unexplained difference |
|---|---|---|---|---|---|
| A: read/edit/PASS | Completed; one immutable submission and PASS | Same | Pass: captured bytes, versions, task acceptance and review link match | Adapted model selects read/edit, adding two accounted provider calls | None |
| B: approved test | Completed; one approval, command receipt and test evidence | Same | Pass: approval scope, command outcome, workspace version and submission link match | Adapted model requests the command and resumes after approval; three additional accounted calls | None |
| C: denied command | Durable denial; no command result | Same | Pass: no command side effect or approval bypass | Adapted model receives a structured denial result; legacy trusted caller receives the decision directly | None |
| D: malformed Developer result | Bounded validation failure; no submission | Same | Pass: technical block and retained call records | Adapted tool turns occur before the malformed final result | None |
| E: canceled pending command | Canceled; no command or submission | Same | Pass: late work cannot advance the task | Adapted path has already made tool selection calls | None |
| F: FAIL → revision → PASS | Completed; two attempts, submissions, reviews and tests | Same | Pass: immutable first submission, exact review links, revision count and final acceptance match | Adapted path makes six additional accounted calls across two tool loops | None |

The legacy fixture invokes file/command entrypoints as a trusted application
caller. The adapted fixture lets the Developer model select tools. Provider call
counts are therefore intentionally different: A 6/8, B 6/9, C 6/9, D 4/6,
E 2/5, F 10/16 (legacy/adapted). Each fixture's persisted call count equals
actual provider requests. Provider-reported tokens total A 90/120, B 90/135,
C 90/135, D 60/90, E 30/75, F 150/240. These differences are attributable
to real tool-loop turns, with one authoritative call record per request.

The adapted PASS workflow and revision workflow both complete offline. In the
revision workflow, the first submission and review remain in history; the
second attempt edits the workspace, runs an approved test, creates a new
submission, receives PASS, and is accepted by the existing Manager/domain path.

The M6 Inspector backend contract remains usable: inspection returns committed
events, tool audits, operations, usage, settings and recovery. The deterministic
trace includes assignment, file read/edit receipts, permission waiting and
decision, command launch/result, submission, review and acceptance. The revision
trace includes two submissions and reviews separated by `revision.requested`.
Event sequence IDs are unique and cursor replay returns only later events.
Public run snapshots omit private continuation context/arguments/results;
the existing API redaction removes credential fields and environment secrets.

Recovery comparison uses the M7.1 continuation fixtures: approval survives
restart, duplicates do not relaunch, stale/canceled generations cannot resume,
prepared commands reuse their operation ID, and uncertain executing commands
are never blindly replayed. An uncertain result still requires operator
reconciliation; no exactly-once guarantee is claimed past that fence.

No live provider call was made. No frontend production code changed. LangChain
Core remains the Developer tool abstraction; Manager/Reviewer retain validated
provider-neutral structured outputs. The existing orchestrator, Permission
Gateway, SQLite domain records and `AgentRuntime` accounting retain ownership.
LangGraph is not present in M7.1.
