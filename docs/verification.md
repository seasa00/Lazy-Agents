# AI Office verification record

**Current official status:** M1–M6 complete; M6 frozen and closed, including the
production Office Experience, approved Pixel Office, Agent Inspector,
pop-out/fullscreen, and system integration. M7 — Agent Runtime Modernization & Production Hardening is **In Progress**. M7.1–M7.2 are complete; M7.3–M7.6 have not started. See the [roadmap](IMPLEMENTATION_MILESTONES.md).

Entries after the M7.2 section are historical verification records. Statements
such as “M4.3 has not started,” earlier visual descriptions, and individual test
counts apply to those recorded checkpoints, not the current project status.


## M7.2 implementation verification — complete

LangGraph 1.2.24 is locked alongside the existing `langchain-core` 1.8.3;
Python requirement remains 3.11+. `tests/test_m72.py` compares isolated
legacy and graph fixtures for first PASS, FAIL/revision/PASS, repeated FAIL at
three rounds, approved and denied command continuation, pause/resume,
cancellation and stale snapshot, dependency scheduling, finalization, malformed
Reviewer output, and restart from approval waiting or a committed submission,
including a SQLite reopen followed by the required explicit recovery resume.
Both paths retain the same event sequence and domain outcomes, with one
`AgentRuntime` call record per provider request. The full backend suite passed
with 488 tests; `git diff --check` passed. See [the comparison report](M7_2_ORCHESTRATOR_COMPATIBILITY.md).
Legacy remains the production default. M7.3 observability is not implemented.

## M7.1 implementation verification — complete

Dependency selection: `langchain-core>=1.8.2,<2`; uv resolved 1.8.2 for
Python 3.11+. No LangGraph dependency or LangSmith integration is used; the
`langsmith` distribution is an indirect `langchain-core` dependency. No LangSmith
credentials, tracing, API calls, or project configuration are required. LangChain
Core provides the Developer tool abstractions; the provider adapter remains
responsible for model transport and `AgentRuntime` callbacks remain the sole
usage/cost accounting path.

New deterministic tests: `tests/test_m71.py` (7 passed) cover gateway-backed
Developer file list/read/edit/write, protected-path denial and failure propagation,
pre-tool execution boundary checks, bounded model→tool→model execution, validated
Developer submission output, per-request call records/token usage, and tool-call
budget exhaustion. `tests/test_m71_command_continuation.py` adds eleven deterministic
command/test approval, resume, idempotency, stale, cancellation, restart, and crash
boundary tests, including a SQLite restart after the intervention is durable but
before its workflow approval commit. Startup reconstructs the approval from the
pre-request continuation seed and exact persisted permission audit.

The first regression run exposed workspace scenarios failing because scripted
test providers do not advertise tool support. The runner now enables LangChain
tools only for Developer invocations whose provider explicitly advertises tool
support; the rerun passed. This preserves the scripted-provider behavior.

The verification command must use the project environment. Running the system
Python (`PYTHONPATH=apps/api python3 -m unittest discover -s apps/api/tests -q`)
failed test discovery because that interpreter has neither `langchain_core` nor
FastAPI installed. With the repository environment, the full suite passed:

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest discover -s apps/api/tests -q
```

The original M7.1 file-tool checkpoint passed **465 tests**. The initial durable
command/test continuation checkpoint passed 144 focused tests and 475 tests in
the full backend suite. After adding the intervention/workflow-commit crash
boundary, the focused groups passed **145 tests** (including permission, recovery,
runtime, API service and M7.1 tests) and the full backend suite passed **476 tests**:

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest tests.test_m71_command_continuation tests.test_m32 tests.test_m42 tests.test_m43 tests.test_m71 -q
PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest discover -s apps/api/tests -q
git diff --check
```

The multi-turn file-tool test verifies two model requests produce two call records and
aggregate provider-reported tokens once per request. The command continuation
fixture verifies four Developer requests across read, edit, approval and resume
retain four attributable records. Accounting remains in the existing runtime
callbacks, with no LangChain callback accounting path.

### Final M7.1 exit evidence

| Requirement | Evidence/status |
|---|---|
| Developer file tools through Permission Gateway | Automated M7.1 tests pass for list/read/write/edit and protected-path denial. |
| Command/test tools and human approval continuation | Implemented for configured command profiles through the existing gateway. Tests cover pending approval, approve/deny, test evidence, duplicate decision, stale generation, pause/cancel, restart while pending, crash between durable intervention and workflow commit, restart after approval before start, crash before the execution fence, and uncertain post-fence crash. |
| Manager/Reviewer structured output | Existing provider-neutral schemas and domain validation remain in use. LangChain wrappers are intentionally omitted because they add no functional benefit. Paired workflows preserve both roles' decisions. |
| Legacy/adapted parity scenarios A–F | Passed in `tests/test_m71_parity.py`; [the compatibility record](M7_1_COMPATIBILITY.md) lists outcomes and intentional provider-call differences. |
| Bounded end-to-end offline workflow with adapted Developer | PASS: Manager → Developer read/edit → approved test → submission → Reviewer PASS → completion. |
| Reviewer FAIL → revision → PASS using adapted Developer | PASS: two attempts, approved tests, immutable submissions, exact reviews, revision brief and acceptance. |
| Live OpenRouter verification | Not performed. |
| M6 Office/Inspector trace compatibility | Existing inspection payload and cursor replay verified with adapted Developer tool, approval, command, submission, review and revision events. No frontend production changes. |

Final closeout: **377 targeted backend tests passed**, followed by **480 full
backend tests passed**. `git diff --check` passed. The paired matrix A–F and
Inspector backend contract passed. **M7.1 is COMPLETE; M7.2 remains NOT STARTED
and ready for review.** Live-provider verification not performed; deterministic
compatibility and regression coverage completed. No frontend production code
changed, so frontend validation was not required for this closeout.

## M4.2 — Restart reconciliation and durable execution controls

**COMPLETE on 2026-10-05. M4.3 has not started.** This section supersedes the
historical M4.1 absence of restart reconciliation below.

Final full suite: **415 tests passed** in 14.726 seconds (366 existing + 49 new
recovery tests). `git diff --check` passed. All tests/fixtures use disposable
workspaces/databases. No provider network calls, user DB upgrades or production
filesystem modifications were performed.

```bash
PYTHONPATH=apps/api python3 -m unittest discover -s apps/api/tests -q
git diff --check
PYTHONPATH=apps/api python3 -m app.dev.recovery demo --directory /tmp/lazy-agents-m42-verified-20261005
```

### Deterministic automated coverage

`tests/test_m42.py` exercises:

- Safe phase restart, prepared file/provider/command boundaries, accepted-task
  completion and paused shutdown. Runner construction and restart inspection
  never execute another operation; resume is explicitly gated.
- File mutation without a receipt, before/after hash proof, mismatching hashes,
  known outcomes restored without writes, and capture reuse without recapture.
- Commands before launch, uncertain completion and confirmed completion. Recovery
  never invokes `os.kill`/`os.killpg` on a persisted PID. Explicit operator
  quiescence acknowledgment retains uncertainty and invents no result/exit code.
- Unknown in-flight provider usage, saved successful proposal admission,
  pre-submission reservations, legacy reservations, and late-result accounting
  without workflow admission after recovery, scope/requirement change or cancel.
- Interrupted first/second Reviewer invocations, immutable submission linkage,
  retained prior review and round 2, and saved Reviewer result admission without
  repeating the review.
- Late command receipts cannot acknowledge a pause owned by newer work; a stale
  file reducer cannot resurrect a canceled run. Permission request/decision audit
  receipts reconcile interrupted workflow permission updates without replay.
- Durable limits/counters/generations, pending instructions, pending permissions
  and approval/request/launch counters. Exhausted limits and generic resolve/scope
  controls cannot bypass recovery; original ordinary blocker/phase remains intact.
- Idempotent reconciliation/resolution, epoch checks, terminal cancellation,
  inspectable missing/corrupt artifacts (including completed runs and operation
  evidence), atomic recovery metadata/operation writes plus events, migration 2→3
  and preservation of immutable historical row bytes. A workspace run cannot
  recover with a synthetic gateway.
- The five real child-process crash scenarios and both in-memory/SQLite recovery
  contract paths. Existing M4.1 migration assertions now expect schema 3 and its
  next invalid/future migration; artifact tests select submission references
  rather than incidental first sidecar rows.

### Manual separate-process restart/reconciliation

The final demo directory was `/private/tmp/lazy-agents-m42-verified-20261005`.
Each fixture committed its state/fences and exited abruptly using `os._exit(73)`;
context-manager shutdown/finally handlers did not run. Inspection, a repeated
idempotence inspection, resolution and explicit resume used separate new processes.
The report is `/tmp/lazy-agents-m42-verified-report.json` (disposable, not a repository
artifact). All five scenarios returned `all_passed: true`.

| Scenario | State after restart | Proof/decision before resume | Final result |
| --- | --- | --- | --- |
| A — before mutation | Paused, interrupted/prepared file operation; original bytes unchanged | No start fence; explicit resume and separately authorized new fixture mutation | Completed; 1 attempt, 1 review, 6 calls, 90 tokens |
| B — mutation happened, outcome absent | Blocked (`waiting_for_user`), uncertain file operation; edited bytes present | Retained before/intended-after hash evidence establishes current target content | Completed; 1 attempt, 1 review, 6 calls, 90 tokens |
| C — provider in flight | Blocked, uncertain submitted request; no automatic resend | Explicit abandonment accepts unknown charge and discards uncommitted application proposal | Completed; same attempt, 1 review, 7 submitted calls, token/cost totals unknown |
| D — second review in flight | Blocked; 2 immutable submissions and first FAIL review retained | Explicitly abandon interrupted response and authorize same-submission review retry | Completed; 2 attempts, 2 reviews, 11 submitted calls; unknown interrupted usage preserved |
| E — paused backend | Still paused, queued instruction and counters retained | Explicit resume | Completed; 1 attempt, 1 review, 6 calls, 90 tokens |

Repeated inspection reports were equal in every scenario. Before explicit resume,
no additional provider submission, file mutation or command occurred. Scenario A's
new mutation is explicitly authorized by `--execute-fixture`, not performed by
startup/inspection/reconciliation/plain resume. Scenario B restored its confirmed
change for immutable capture without repeating the write. Scenario D preserved the
first review identity/submission/round and added round 2, without resetting the
3-round limit. Calls in C/D remain counted once, with unknown usage/cost retained;
these fixtures configure no pricing, so no monetary amount is fabricated.

Known versus uncertain is deliberately conservative: a durable prepared fence
proves no permitted execution; a committed receipt proves the recorded outcome;
an executing fence without a receipt proves neither success nor failure. File
hash resolution establishes present bytes under the recorded narrow mutation,
not historical absence of other effects. Operator process/effect attestations
retain uncertainty. A saved PID alone never authorizes signaling.

### Files and contracts changed for M4.2

Added:

- `apps/api/app/domain/recovery.py`
- `apps/api/app/orchestration/recovery.py`
- `apps/api/app/dev/recovery.py`
- `apps/api/app/persistence/migrations/003_execution_recovery.sql`
- `apps/api/tests/test_m42.py`

Updated:

- `apps/api/app/agents/runtime.py` — durable call reservation/receipt callbacks
- `apps/api/app/domain/workflow.py`, `artifacts.py`, `commands.py` — checkpoints,
  recovery epoch/state, gateway mode and backward-compatible protocol markers
- `apps/api/app/orchestration/runner.py`, `controls.py` — startup gate, restored
  gateways, explicit resume, original controls, generation/epoch/requirement fencing
- `apps/api/app/persistence/store.py`, `operations.py`, `sqlite.py`, `models.py` —
  store-neutral metadata/operation/permission queries and atomic recovery writes,
  typed recovery values, immutable-byte preservation on upgrades
- `apps/api/app/tools/gateway.py` — durable stages, retained changes/captures and
  command results/permissions/counters; no process restoration
- `apps/api/app/usage/aggregation.py` — effective late receipts deduplicated by call ID
- `apps/api/app/dev/workflow.py` — injectable store for controlled recovery fixtures
- `apps/api/tests/test_m41.py` — schema version/future migration and artifact selection
- `README.md`, `docs/CURRENT_MILESTONE.md`, `docs/contracts.md`,
  `docs/verification.md`, `docs/decisions.md`

Recovery never automatically resumes execution, replays workspace mutations or
commands, resends unknown provider requests or resets lifetime limits. An explicit
resume restores the same valid attempt/submission phase, or the next phase of a
saved proposal explicitly admitted under all existing authority checks. Terminal
runs do not resume. Unknown billing remains unknown; late reported usage enriches
stored effective accounting without rewriting original interrupted call rows.

Single-local-user/single-writer, file/SQLite atomicity limits, external writer
races, trusted-code privileges and detached descendants remain limitations. No
exactly-once execution, rollback, distributed lease/worker, provider-side recovery,
FastAPI/SSE/frontend or M4.3 work was introduced.

## M4.1 — SQLite state, event history, and durable accounting

**COMPLETE on 2026-10-05. M4.2 has not started.** Historical milestone records
below describe their status at verification time; their earlier in-memory-only
limitations are superseded by the M4.1 contracts.

Final full suite: **366 tests passed** in 8.573 seconds. `git diff --check` passed.
No API calls or production/user database modifications were performed. All database
tests use `TemporaryDirectory`; the manual fixture used a new directory under `/tmp`.

```bash
PYTHONPATH=apps/api python3 -m unittest discover -s apps/api/tests -q
git diff --check
```

The original 187 tests remain passing. `tests/test_m41.py` adds 179 executions:

| Coverage | Tests |
| --- | ---: |
| Existing StateStore contracts against SQLite | 8 |
| Existing workflow contracts against SQLite | 49 |
| Existing workspace contracts against SQLite | 41 |
| Existing command contracts against SQLite | 48 |
| Existing finalization contracts against SQLite | 7 |
| New persistence, transactions, migrations, integrity and boundary checks | 24 |
| Decimal/per-agent/retry/unknown aggregation checks | 2 |

New cases cover project/run/task/dependency/decision reopen; attempts, submissions,
reviews, agents, invocations, calls and event history; command/tool/intervention and
artifact metadata reopen; successful transitions; rollback on event insertion,
state validation and audit event failure; rejection of event-only/state-only
reducers; foreign keys, duplicate active runs, duplicate IDs and attempt numbers;
ordered sequences after reopen and append-only triggers; duplicate/conflicting
calls and idempotent audit records; unknown, incomplete and retry usage; fresh,
current, upgrade, invalid/checksum/newer and failed migration states; missing and
corrupt artifacts; credential-named configuration rejection; and no SQL transaction
during reducers, sidecar IO or command launch.

Separate-reader checks prove file and command intent is committed before write or
spawn. An injected intent-write failure prevents the filesystem operation entirely.
Tests compare complete immutable domain records and event envelopes after reopen,
including exact Decimal values, enums, hashes and captured bytes loaded from disk.

### Manual complete workflow and separate-process reopen

Executed these as separate processes, with the first exiting before the second:

```bash
PYTHONPATH=apps/api python3 -m app.dev.persistence create /tmp/lazy-agents-m41-final-20261005
PYTHONPATH=apps/api python3 -m app.dev.persistence inspect /tmp/lazy-agents-m41-final-20261005
```

The fixture created a disposable greeting project, generated/approved its plan,
read/edited a real file, explicitly approved its exact harmless Python test profile,
executed it, captured the submission/test evidence, reviewed/accepted it and
completed finalization. A fake API credential was placed in process environment;
a protected `.env` held a separate sentinel. No live provider was used.

The new process loaded the same SQLite database and sidecar directory without
constructing a runner or resuming work. The complete inspection report matched
the report saved by the exited process: project/task/attempt/review identities,
all event IDs/sequences, individual LLM and tool records, artifact metadata,
submission digest, call attribution and all usage aggregates.

Observed counts: 1 project, 3 agent snapshots, 1 run, 1 task, 1 attempt, 1 submission,
1 review, 6 invocations, 6 LLM calls, 1 command result, 11 tool audit records,
1 command permission intervention, 1 captured file metadata row, 4 top-level
artifact references, and **47 events** (last sequence 47). This single-task fixture
has no dependency edges or plan decisions; separate reopen tests cover both.

Command outcome: succeeded, exit 0, captured output `1 test passed`. Captured tests
remained fresh and successful. Submission digest and file content hash remained
identical after reopening. SQLite `integrity_check` returned `ok` and
`foreign_key_check` returned no violations.

| Agent | Calls | Tokens | Estimated USD (fixture prices) |
| --- | ---: | ---: | ---: |
| Manager | 4 | 60 | 0.00008000 |
| Developer | 1 | 15 | 0.00002000 |
| Reviewer | 1 | 15 | 0.00002000 |
| Total | 6 | 90 | 0.00012000 |

Each call recorded 10 input, 0 cached input, 10 uncached input and 5 output tokens,
with cost USD 0.00002000. Totals were independently summed from individual records
and compared overall and per agent. There were 0 retries and 1 review. Pricing was
a deterministic fixture (USD 1/M input, 0.5/M cached input, 2/M output), not a claim
about current provider pricing. Unknown/partial pricing/usage and failed retry
calls are additionally verified by automated tests and remain unknown in totals.

SQLite dump checks found neither the fake API credential nor protected `.env`
content nor captured greeting bytes. The protected file stayed in the workspace;
file evidence and command logs remained in hashed sidecars. Provider clients and
process environment are never passed to the persistence serializer.

### Changes and limits

Added:

- `apps/api/app/persistence/operations.py`, `sqlite.py`, `models.py`, `migrate.py`
- `apps/api/app/persistence/migrations/001_initial.sql`, `002_query_indexes.sql`
- `apps/api/app/usage/aggregation.py`
- `apps/api/app/dev/persistence.py`
- `apps/api/tests/test_m41.py`

Updated:

- `apps/api/app/persistence/memory.py`, `store.py`
- `apps/api/app/domain/workflow.py`, `orchestration/runner.py`, `tools/gateway.py`
- `apps/api/app/dev/workspace.py`, `apps/api/pyproject.toml`, `.gitignore`
- `README.md`, `docs/CURRENT_MILESTONE.md`, `docs/contracts.md`,
  `docs/verification.md`, `docs/decisions.md`

Schema version 2 and the complete table map are documented in `contracts.md`.
Clean shutdown persistence is supported for one local user and one application
writer. Preserve the database and sidecar directory together. Filesystem changes
and SQLite commits cannot roll back together; failed commits may leave orphan
sidecars. **Crash/restart reconciliation, automatic resume and exactly-once side
effects remain unsupported until M4.2.** Existing trusted-local-command limitations
still apply. No M4.2 work, HTTP/SSE, frontend or distributed infrastructure was added.

## M3.2 — Approved commands, test evidence, and tool limits

### Required live OpenRouter verification — 2026-10-05

**M3.2 COMPLETE; M3 — Tools & Permissions COMPLETE. M4.1 has not started.**

The required bounded live small-project workflow completed successfully through
OpenRouter with `openai/gpt-4o-mini`. Workflow status was `completed`,
`blocked_reason` was null, and all six provider calls succeeded on attempt 1.
There were no retries or repairs and one review round. Usage was 2,618 input +
601 output = 3,219 total tokens; estimated cost was USD 0.00075330. The final
result passed validation and referenced the accepted tasks and evidence. The
previous finalization validation failure did not recur.

The earlier attempt on 2026-10-05 also made six first-attempt calls with this
model, using 2,435 input and 628 output tokens (3,063 total; estimated cost USD
0.00074205), but exited with `waiting_for_user` because final output validation
reported `final result must reference all accepted tasks and evidence`. The
successful run above supersedes that failed result for the required live gate.

The prior defect investigation found that final context lacked an explicit
task-to-accepted-submission mapping and exact finalization policy. A shared
manifest now resolves each task's latest accepted submission, checks
generation/requirements and rejects noncurrent acceptance entries. Both context
and final validation use that manifest. Schema descriptions explicitly require
every supplied task ID and accepted submission ID; exact-set validation rejects
missing and stale references. This live run confirms the previous validation
failure did not recur.

Full automated suite: **187 tests passed** on 2026-10-05 using the command below.
The finalization regression tests cover one/multiple tasks, missing task/evidence
IDs, stale attempts, raw evidence substitutions, authoritative provider context,
schema semantics, and the six-successful-calls/final-validation-failure shape.
`PYTHONPATH=. python3 -m app.dev.commands` exited **0**: workflow completed,
test succeeded (exit 0, `1 test passed`), Reviewer received captured files/tests,
denial/cancellation/process cleanup and stale-evidence checks all passed.

The earlier `app.dev.workflow live` finalization run used synthetic in-memory
evidence; it did not execute M3.2 workspace commands. Its original validation
failure and the successful required M3.2 live verification recorded above are
separate runs. The real-process command lifecycle check remains the disposable
`app.dev.commands` demonstration below.

Verification date: 2026-10-05. Implementation, required live verification, and
automated verification passed. **M3.2 and M3 are complete. M4.1 not started.**

Full standard-library suite, from `apps/api`:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -q
```

Observed: **180 tests passed** (132 existing + **48 M3.2 tests**). The suite
executes only harmless fixture programs inside automatically removed disposable
workspaces. No package installation or provider network request was performed.

Required coverage in `tests/test_m32.py`:

| Required test | Observed |
| --- | --- |
| Unapproved command | Denied, no marker file created; audit outcome retained. |
| Approval mismatch | Changed argv, profile, cwd, environment, timeout, output cap, attempt or generation denied. |
| No shell expansion/injection | `$()`, backticks, semicolons, globs, variables, pipes and spaces arrived as literal argv; no injected marker. |
| Cwd escape | Absolute/traversing/noncanonical paths and directory symlinks denied; valid nested cwd scoped correctly. |
| Restricted environment | Fake inherited API/AWS secrets, PYTHONPATH, startup/loader variables and HOME absent; forbidden overrides denied. |
| Timeout | Sleeping/flooding fixture timed out, non-success result, exit code retained, direct process reaped. |
| Output truncation | Both streams drained under heavy output, each retained within cap with truncation flags. Invalid UTF-8 also bounded. |
| Cancellation | Active command canceled, result retained on canceled run, pending slot cleared after cleanup. |
| Process cleanup | Direct process and original-group descendant disappeared; leader exit with unfinished child reported terminated, not success. |
| Pause before launch | Denied before Popen with no execution; final launch guard separately tested. |
| Failed test command | Exit 7 and assertion stderr preserved; fresh evidence marked failed. |
| Stale test evidence | Gateway/external/protected-file changes and restored bytes invalidate live evidence; self-mutating tests stale too. |
| Reviewer denied | Cannot request or execute even with a valid Developer approval. |
| Manager denied | Cannot request or execute even with a valid Developer approval. |

Additional coverage: pending interventions stop workflow progression; explicit
denial audit; single-use approvals; shell-profile rejection; one active command
and no overlapping file mutation/provider step; pause-during-command/resume;
launch/request/workspace/output limits; no budget reset on resume; mutable or
unbounded request rejection; executable/profile changes invalidate approval;
scope invalidation and cancellation during execution; launch failure consumes
approval and records error; JSON serialization of full real-file/command history;
version-bound Reviewer context after live edits; stale/failed evidence cannot
establish PASS; a fresh retest supersedes older stale results; ordinary commands
cannot become test evidence; incomplete cleanup conservatively retains the
reservation and blocks further commands/resolution; repeatable demo assertions.

### Disposable real-process verification

Command, from `apps/api`:

```bash
PYTHONPATH=. python3 -m app.dev.commands
```

Observed output:

```json
{
  "workflow_status": "completed",
  "test_outcome": "succeeded",
  "exit_code": 0,
  "stdout": "1 test passed\n",
  "reviewer_received_submission_and_tests": true,
  "denied_without_execution": true,
  "slow_command_outcome": "canceled",
  "process_reaped": true,
  "live_test_evidence_stale_after_edit": true,
  "captured_submission_unchanged": true,
  "disposable_workspaces": true
}
```

1. Developer used the existing gateway to edit a disposable `greeting.txt` from
   `hello` to `hello world`.
2. Developer requested the exact configured test profile. The harness recorded an
   explicit human-control approval scoped to that request and workspace version.
3. The actual local Python executable ran `-I -B test_greeting.py` with bounded
   output/timeout and restricted environment. Exit 0 and `1 test passed` were
   recorded against matching before/after workspace versions.
4. Reviewer received the immutable changed file, diff and application-captured
   command/test result in the submission. The workflow completed.
5. A second disposable project requested a marker-writing command; the harness
   explicitly denied it. Launch failed and the marker file did not exist.
6. A slow harmless fixture received a separate exact approval, launched, then
   was canceled through workflow controls. Result was canceled; the direct PID
   no longer existed after cleanup.
7. A later external edit made live test evidence stale/nonpassing. The previously
   captured/reviewed submission and its historical evidence stayed unchanged.

Both temporary projects were removed. Approvals in this fixture authorize only
these built-in disposable programs; there is no blanket approval for arbitrary
workspace commands. Role proposals are deterministic; subprocess execution is real.

### Remaining roadmap verification and safety limits

The required real-provider small-project smoke check passed as recorded above.
`OPENROUTER_API_KEY available: False` was an earlier observation and does not
describe the completed live verification. The smoke run and the disposable
real-process demonstration are separate checks: the former verifies bounded
provider-backed workflow completion, and the latter verifies command lifecycle
behavior in a disposable workspace.

Approved commands are trusted local code, **not OS sandboxing**. They retain the
service user's filesystem/network privileges; cwd and environment restrictions
cannot stop code from accessing outside paths, modifying protected files, starting
shells or detaching descendants. POSIX/macOS original-group cleanup is tested;
whole-process-tree containment is not guaranteed. Sequential fingerprints have
external-writer/path-replacement races and do not snapshot outside libraries.
OS spawn/filesystem IO are synchronous. Logs/approvals/evidence remain process-local;
no persistence, crash recovery, installation, deployment, deletion tool, FastAPI,
frontend or M4.1 was added. Full details are in `contracts.md`.

### Files changed

Added:

- `apps/api/app/domain/commands.py`
- `apps/api/app/tools/commands.py`
- `apps/api/app/dev/commands.py`
- `apps/api/tests/test_m32.py`

Updated:

- `apps/api/app/permissions/policy.py`
- `apps/api/app/tools/gateway.py`, `__init__.py`
- `apps/api/app/domain/artifacts.py`, `workflow.py`
- `apps/api/app/orchestration/runner.py`, `controls.py`
- `apps/api/app/dev/workspace.py`
- `docs/CURRENT_MILESTONE.md`, `docs/contracts.md`, `docs/verification.md`
- `README.md`

## M3.1 — Workspace file tools and immutable submissions

Verification date: 2026-10-04. **M3.1 complete; M3.2 not started.**

Full standard-library suite, from `apps/api`:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -q
```

Observed: **132 tests passed** (91 existing + 41 M3.1), including all prior
workflow/provider regressions. Tests perform file operations exclusively inside
`TemporaryDirectory` fixtures. No provider network calls or installation.

Real-file verification command, from `apps/api`:

```bash
PYTHONPATH=. python3 -m app.dev.workspace
```

Observed: **completed**, 11 recorded file operations, disposable workspace
removed after verification. Submission:
`workspace-run:t0-0:attempt:1:submission`; evidence digest:
`ea2975319fa57e196e5d309cd852ff15818714e217a9d7ce6c6b1ce899da7018`.

| Required verification | Observed evidence |
| --- | --- |
| Developer edits real workspace | Role-bound runner edit changed `greeting.txt` from `hello\n` to `hello world\n`. |
| Submission captures exact version | Frozen file bytes, SHA-256 hashes and diff capture `hello world\n`. |
| Reviewer reads capture | Reviewer gateway read and subsequent role context both contain captured bytes. |
| Later changes cannot alter capture | Live file changed to `later external version\n`; Reviewer still read `hello world\n`, manifest digest unchanged. |
| Outside-root write denied | Absolute path to a sibling fixture rejected; outside file stayed `untouched`. |
| Reviewer mutation denied | Write rejected; source stayed unchanged. |
| Manager mutation denied | Write rejected; source stayed unchanged. |
| External conflicts detected | External writer changed the source after read; stale-hash write rejected and external bytes preserved. Explicit fresh read/hash used to restore intended output before capture. |

Captured diff:

```diff
--- a/greeting.txt
+++ b/greeting.txt
@@ -1 +1 @@
-hello
+hello world
```

Additional automated coverage: nested paths, traversal/noncanonical paths,
file/directory/dangling/internal symlinks, hardlinks, protected defaults and
configured subtrees, live-read role denial, unsupported operations, omitted
hashes, create conflicts, unique edits, added/reverted files, exact manifest
paths, immutable/repeated captures, scope mismatches, later-attempt isolation,
missing-final-newline diffs, preservation of file mode, bounded reads/writes/
lists/results/capture, binary/FIFO rejection, root replacement, immutable audit
records, unbound guard denial, final pre-replacement guard cleanup, paused/
canceled/stale-scope mutation denial, pause/resume during Developer call,
cancel/late-result usage retention, and external edits before capture blocking
admission. Reviewer reads remain valid even after the live workspace is removed.

The demonstration uses deterministic role proposals and trusted runner file
calls, not a live model's native tool dispatch. Test execution inside the agent
workflow remains unavailable; submitted test reports are labeled UNVERIFIED.
Artifacts/audit remain in application memory. Optimistic hashes are not hostile-
process isolation; final-check races, directory moves, sequential multi-file
capture and lack of crash-atomic filesystem/state commits remain documented in
`contracts.md`. No commands, deletion tool, SQLite, FastAPI, frontend or M3.2
were implemented.

Files added:

- `apps/api/app/permissions/__init__.py`, `policy.py`
- `apps/api/app/tools/files.py`, `gateway.py`, `submissions.py`
- `apps/api/app/domain/artifacts.py`
- `apps/api/app/dev/workspace.py`
- `apps/api/tests/test_m31.py`

Files updated:

- `apps/api/app/domain/submissions.py`
- `apps/api/app/orchestration/runner.py`
- `apps/api/app/tools/__init__.py`
- `docs/CURRENT_MILESTONE.md`, `docs/contracts.md`, `docs/verification.md`
- `README.md`

## M1.1 — Agent contracts and isolated runtime

Verification date: 2026-09-21

The original M1.1 gate recorded 15 passing tests, independent deterministic
CLI checks for all three roles, and the intentional malformed-output check.
Those tests remain in `tests/test_m11.py` and pass in the M1.2 regression run.

## M1.2 — One provider, bounded calls, and usage attribution

Implementation verification date: 2026-10-04

### Automated tests

Command, from `apps/api`:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Result: **28 tests passed**.

M1.2 coverage includes:

- OpenRouter OpenResponses-shaped structured JSON and usage normalization.
- Cached-input token normalization and overlap-safe Decimal pricing.
- Missing credentials and invalid model-slug rejection before transport.
- Secret exclusion from ordinary provider configuration representation.
- Bounded transient retries with injectable backoff and every attempt
  recorded, including retry exhaustion with unknown usage.
- Bounded structured-output repair and repair exhaustion.
- Unknown pricing represented without fabricated zero cost.
- All 15 M1.1 regression tests.

The suite uses only the Python standard library and does not require network
credentials or make provider calls.

### Deterministic manual verification

From `apps/api`:

```bash
PYTHONPATH=. python3 -m app.dev.cli manager
PYTHONPATH=. python3 -m app.dev.cli developer
PYTHONPATH=. python3 -m app.dev.cli reviewer
PYTHONPATH=. python3 -m app.dev.cli manager --invalid
```

Observed: all three valid calls returned validated role outputs with one
deterministic provider call record each. The malformed call exited `2` and
reported the `manager_plan.v1` validation error. No network or local mutation
occurred.

### Live-provider verification status

The required bounded live checks were completed with a backend-only
`OPENROUTER_API_KEY`:

```bash
PYTHONPATH=. python3 -m app.dev.cli manager --provider openrouter --model openai/gpt-4o-mini --max-attempts 3 --max-repairs 1
PYTHONPATH=. python3 -m app.dev.cli developer --provider openrouter --model openai/gpt-4o-mini --max-attempts 3 --max-repairs 1
PYTHONPATH=. python3 -m app.dev.cli reviewer --provider openrouter --model openai/gpt-4o-mini --max-attempts 3 --max-repairs 1
```

Observed live results:

| Check | Provider/model | Result | Attempts | Repairs | Structured output | Usage and cost |
|---|---|---|---:|---:|---|---|
| Manager | OpenRouter / `openai/gpt-4o-mini` | succeeded | 1 | 0 | validated `manager_plan.v1` | provider-reported token usage recorded; estimated Decimal USD cost produced |
| Developer | OpenRouter / `openai/gpt-4o-mini` | succeeded | 1 | 0 | validated `developer_submission.v1` | provider-reported token usage recorded; estimated Decimal USD cost produced |
| Reviewer | OpenRouter / `openai/gpt-4o-mini` | succeeded | 1 | 0 | validated `review_result.v1` | provider-reported token usage recorded; estimated Decimal USD cost produced |

All three calls reported usage, created a successful `LLMCallRecord`, and
required no repair or retry. The live output summary supplied for this record
contains the usage/cost presence and provenance above but not the numeric token
counts or Decimal amounts; no numeric values are inferred here. No credential,
prompt payload, or other sensitive data was printed, committed, or persisted.

This completes the required M1.2 live-provider gate.

## M2.1 — Shared state, planning, and legal transitions

Implementation and verification date: 2026-10-04

### Automated verification

Command, from `apps/api`:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Result: **42 tests passed**.

The 14 new M2.1 tests cover:

- Valid Manager plans and invalid structured plan shape.
- Plan approval and execution-before-approval rejection.
- Missing, self, and cyclic dependencies.
- Dependency readiness before and after prerequisite completion.
- Invalid state transitions and exactly one active run.
- Canceled tasks excluded from completed-task counts.
- Atomic state/event consistency and rejection without partial commits.
- The repeatable state demonstration CLI.

### Manual verification

Command, from `apps/api`:

```bash
PYTHONPATH=. python3 -m app.dev.cli state-demo
```

Observed:

```text
Validated plan: Build the bounded M2.1 demonstration
Ready task: task-foundation
Cyclic plan rejected: task dependency cycle detected: cycle-a -> cycle-b -> cycle-a
Second active run rejected: project project-demo already has active run run-demo
```

The demonstration displayed proposed tasks and dependencies, validated and
approved the plan, selected only the root task as ready, rejected a cyclic
proposal before committing it, and rejected creation of a second active run.
No Developer/Reviewer execution loop, filesystem change, command execution,
SQLite write, HTTP request, or UI state was involved.

This completes the M2.1 gate. M2.2 was not started.

## M2.2 — Complete workflow and bounded human controls

Verification date: 2026-10-04. **M2.2 COMPLETE: implementation, deterministic
checks and required live workflow passed.** M3.1 was not started.

### Automated verification

From `apps/api`:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Result: **91 tests passed** (42 prior regressions + 49 M2.2 tests in
`tests/test_m22.py`). Coverage includes:

- Initial PASS, multiple dependent tasks, exact accepted evidence and final result.
- FAIL→PASS, FAIL→FAIL→PASS, and blocking exactly at three review rounds.
- Manager bypass attempts, missing evidence, incorrect submission versions,
  malformed/empty/stale reviews, premature assignment and incomplete final evidence.
- Invocation, provider-call, per-invocation, iteration, task creation and replan caps.
- Technical failures and repairs remain separate from quality rounds; usage is
  retained for retries, non-retryable failures, cancellations and stale results.
- Pause before/during a call, no retry after pause, resume, block/resolve,
  cancellation with a late result/error, and queued instruction application.
- Scope/configuration changes, conservative acceptance invalidation, current
  requirement criteria, and waiting for outstanding calls before resume.
- Concurrent dispatch exclusion, application-wide run uniqueness, protected
  legacy mutation paths, version conflicts, immutable/defensive snapshots,
  event evidence links and run/task/call usage attribution.
- Reviewer cannot write evidence; controlled gateway has no filesystem/shell
  operations. Run snapshots serialize workflow history.

### Deterministic manual scenarios

```bash
PYTHONPATH=. python3 -m app.dev.workflow all
```

Exit code: **0**. Every scenario asserts its terminal result.

| Scenario | Actual result | Admitted review rounds | Provider calls |
|---|---|---:|---:|
| A: initial PASS | COMPLETED | 1 | 6 |
| B: FAIL → revision → PASS | COMPLETED | 2 | 10 |
| C: repeated FAIL | Task BLOCKED, run WAITING_FOR_USER at review limit | 3 | 13 |
| D: pause during controlled held call | PAUSED; next operation rejected; resume → COMPLETED | 1 | 6 |
| E: cancel during controlled held call | CANCELED; late result ignored; usage retained | 0 | 3 |

D/E use thread events to hold and release an actual in-flight fixture provider
call, rather than timing-sensitive sleeps. All evidence and tools are synthetic
and in memory. No real agent filesystem or command capability was invoked.

### Live OpenRouter workflow

Command:

```bash
PYTHONPATH=. python3 -m app.dev.workflow live --model openai/gpt-4o-mini
```

Initial assistant-launched attempt: exit code **2** before network submission:

```text
{"status": "not_verified", "reason": "technical failure: provider call failed: OPENROUTER_API_KEY is required for the openrouter provider"}
```

The workspace process did not inherit the key exported in the user's shell.
The user then ran the same command in that configured shell and supplied the
complete JSON result. **That live workflow completed successfully**, with
`status: completed`, `blocked_reason: null`, and one review round.
The table below records that user-run evidence; it is not a claim that the
assistant-launched process made these calls. No credential was inspected or printed.

Provider: `openrouter-responses`; model: `openai/gpt-4o-mini`.
All six calls: `succeeded`, `attempt: 1`, `purpose: initial`,
`usage_provenance: provider_reported`, `usage_completeness: complete`, no errors.
There were no technical retries or structured repairs. With six calls and one
round, the phases follow the fixed successful runner sequence shown below.

| Phase | Provider request ID | Input | Output | Total | Estimated USD |
|---|---|---:|---:|---:|---:|
| Manager plan | `gen-1791119571-ZX34TbtiOFmIEZFCCuFI` | 342 | 175 | 517 | 0.00015630 |
| Manager assignment | `gen-1791119574-OS6kDHYdQt3IrrbmSrRx` | 244 | 39 | 283 | 0.00006000 |
| Developer submission | `gen-1791119578-skh3RP5M3eWoyzWZLnJk` | 397 | 135 | 532 | 0.00014055 |
| Reviewer | `gen-1791119582-uEu24gnNLUk9hYi0zm0C` | 570 | 176 | 746 | 0.00019110 |
| Manager acceptance | `gen-1791119586-pYR3k5xTxoQdciG7QmTg` | 489 | 36 | 525 | 0.00009495 |
| Manager final result | `gen-1791119588-YXF7cpWIlTjN0GyoSjDb` | 258 | 75 | 333 | 0.00008370 |
| **Total** | | **2,300** | **636** | **2,936** | **0.00072660** |

Cached input: 0 for every call; uncached input equals input. Decimal totals were
reconciled against the supplied pricing snapshot (`2026-10-04`): USD 0.15/million
input, 0.075/million cached input, 0.60/million output. These are estimates from
the configured rate snapshot, not a provider billing reconciliation.

Live caps: one task, 16 invocations, 24 LLM calls, 24 iterations, three review
rounds, three transient attempts, one structured repair, four calls per
invocation, 30-second provider timeout. Unknown aggregate cost is reported as
unavailable rather than zero.

### Changed files

New files:

- `apps/api/app/domain/submissions.py`, `reviews.py`, `workflow.py`
- `apps/api/app/orchestration/runner.py`, `controls.py`, `limits.py`
- `apps/api/app/tools/__init__.py`, `contracts.py`, `memory.py`
- `apps/api/app/dev/workflow.py`
- `apps/api/tests/test_m22.py`

Updated files:

- `apps/api/app/domain/projects.py`
- `apps/api/app/orchestration/planning.py`
- `apps/api/app/persistence/store.py`, `memory.py`
- `apps/api/app/agents/runtime.py`, `apps/api/app/providers/schemas.py`
- `docs/CURRENT_MILESTONE.md`, `docs/contracts.md`, `docs/verification.md`,
  `docs/decisions.md`, `README.md`

## Known limitations

- Usage/cost records and project state are process-local and not durable until
  later persistence milestones.
- M2.2 executes the full workflow only with synthetic evidence. Real tools,
  SQLite, crash recovery, FastAPI, SSE, frontend and office UI remain out of scope.
- Scope/configuration changes conservatively invalidate every task's acceptance;
  replacement/reopening after execution starts is rejected. No counters reset.
- Pausing waits for an outstanding provider call; it cannot undo submitted work
  or billing. The live check verifies orchestration and structured synthetic
  evidence, not real software implementation or filesystem/command tools.
- The adapter accepts OpenRouter model slugs without an OpenAI-only allowlist;
  the selected slug and routed endpoint must support the requested structured
  output parameters.

## M4.3 verification — 2026-10-05

Full suite: **445 passing tests**, including **30 new M4.3 tests**. Existing
migration tests now target schema 4 while preserving schema-2 upgrade/history
checks and atomic failed-migration checks. `git diff --check` passed.

`tests/test_m43.py` verifies HTTP workflow end-to-end; create/plan/cancel duplicates;
concurrent duplicate admission; journal receipts and uncertain fences after reopen;
conflicting keys; stale versions with no emitted mutation; one active run;
snapshot/cursor consistency; strict inputs; host/origin/mutation restrictions;
missing entities; backend credentials absent from public JSON; responsiveness
during provider IO; pending pause and explicit resume; permission rejection and
idempotent approval; immutable artifact reads after live edits; protected/custom
protected/traversal paths; recovery inspection, epoch rejection, uncertain-provider
resolution and resume. SSE tests verify ordered replay/reconnect, events arriving
during replay, snapshot-to-stream race, slow/disconnected clients, keepalives,
SQLite sequence IDs and exclusion of uncommitted events.

Manual real HTTP + SSE check: `PYTHONPATH=. python3 -m app.dev.http` passed over a
real loopback Uvicorn socket using disposable SQLite and a controlled provider.
Created/planned/approved/started/paused/resumed/completed the fixture; duplicate
creation returned the same acknowledgment. HTTP remained responsive during a
held Developer call. Disconnecting the stream did not stop execution. Reconnected
with Last-Event-ID 13 and a deliberately invalid query cursor; the header won and
all 38 committed events replayed in order through final cursor 51. Six synthetic
provider calls; complete final snapshot. Server shutdown settled before DB close.

Dependencies were installed in a disposable virtualenv at
`/private/tmp/lazy-m43-venv`. Loopback binding required sandbox escalation; the
verification did not access external providers, production data or credentials.
The current Starlette TestClient emits a dependency deprecation warning for
HTTPX; all checks pass. No frontend or M5.1 implementation was started.

## M5.1 verification — 2026-10-05

- **445 backend tests passed** (`python -m unittest discover -s tests -q`).
- **59 frontend tests passed** (`npm test`, five Vitest files).
- **4 Chromium E2E tests passed** (`npm run test:e2e`, 32.7 seconds).
- **1 separate headed-browser full-workflow check passed**
  (`npm run verify:browser`, 25.9 seconds).
- TypeScript (`npm run typecheck`), production Next.js build (`npm run build`),
  OpenAPI type generation and `git diff --check` passed.

Frontend tests cover authoritative snapshot load, event-driven refresh, duplicate
and older-event suppression, sequence gaps, resets including lower restored DB
cursors, stale snapshots/acks, pending/uncertain commands and exact-key/body retry;
stream framing (split UTF-8, CRLF, multiline JSON, keepalives), replay order,
Last-Event-ID reconnect, 409 reset, malformed/cross-project envelopes and teardown;
controller snapshot-before-stream ordering, pause confirmation and stale-version
refresh; project creation/list/open, planning/approval/start, task/review changes,
resume/cancel/final result, disconnect/stale-version/blocked/recovery visibility,
permission details/reason/approve/deny/rejected decision; and proxy local
Host/Origin/Fetch-Site restrictions, upstream URL restriction, credential header
exclusion, error messages, replay headers and initial keepalive comment.

The full real-browser scenario uses `app.dev.browser:app` and actual SQLite,
WorkflowRunner, WorkspaceToolGateway, committed events and FastAPI endpoints.
All normal workflow actions use rendered controls, not test-client API commands:
create → name/goal/criteria → plan → review/approve → start → permission details/
reason/approve → continue → Developer → Pause requested → backend PAUSED → Resume
→ FAIL/revision → refresh during the second attempt → authoritative state restored
→ PASS → DONE (two reviews) → completed summary/limitations/evidence references.
Unique activity IDs were checked; no page JavaScript errors occurred.

Other browser scenarios persist a denied permission across refresh then cancel,
exercise browser offline/online connection state and Last-Event-ID reconnect, and
inject one read-only unavailable-cursor response to prove automatic snapshot
reset/reconnect. The cursor-error response is the only mocked browser transport
response; workflow facts and mutations are actual backend commits.

For visual/manual verification, headed Chromium opened the full workflow against
real loopback servers. Screenshots of permission scope, Pause requested, Paused,
refreshed execution and final completion were recorded under ignored
`apps/web/test-results/` and visually inspected. The final screenshot showed event
cursor 144, completed run, DONE task, two reviews, explicit fixture limitations
and the backend evidence JSON link. This verification was browser automation plus
visual inspection, not a claim of human mouse-driven testing.

The explicit fixture uses a disposable greeting workspace and harmless approved
Python print command; that command is not promoted to test evidence. Each revision
records a genuine distinct per-attempt file change, preserving existing capture
rules. Four-second Developer calls make the pending pause observable. No live
provider, production database, credentials, frontend-created workflow transition
or self-authorized permission was used. Default M4.3 backend behavior is unchanged.

Node 26.4.0/npm 11.17.0, Next.js 16.3.8, Python 3.14, Chromium via Playwright were
used. API dependencies came from `/private/tmp/lazy-m43-venv`; browser binaries
from `/private/tmp/lazy-m51-browsers`. Installation and loopback/headed-browser
checks required sandbox escalation. Existing Starlette HTTPX and Node color
warnings are non-failing. Frontend uses the checked-in npm lockfile for repeatability.
M5.2 and M6 were not started; unsupported HTTP features and activity-window limits
are explicitly documented in the UI, README and contracts.

## M5.2 verification (2026-10-05)

Additional backend coverage in `tests/test_m52.py` verifies exact attempt/review
references, durable input/output/cache accounting and repeated reads, immutable
artifact/diff associations, missing/protected paths, settings idempotency and
persistence, stale versions, future-run model configuration and historical runner
reconstruction, forbidden settings fields and safe validation errors, credential/
environment/authorization redaction, missing inspection records and explicit
recovery acknowledgment without changing uncertain outcomes or auto-resuming.

Frontend inspection tests verify captured employee state/model/role/capabilities,
invocations and structured handoffs, no rendering of injected private/secret fields,
exact submission versions, multiple FAIL/PASS attempts, findings/fixes/unperformed
checks, technical errors without invented verdicts, protected artifact loading,
404/policy/permission/integrity failures, diff markers and stale historical evidence,
total/per-agent token/cost rendering, retries separate from review rounds, unknown
cost, replacement totals on repeated reads, manual provider slugs, future-only
settings, stale/policy rejection, same-key uncertain retries, effective role-policy
denial and recovery inspection/reason/quiescence/explicit resume. A controller
regression keeps a command visibly sending until its owned refresh finishes.
Existing permission approval/denial and SSE reconnect/replay/reset tests remain.

`e2e/00-inspection.spec.ts` drives the real local FastAPI/SQLite and Next.js servers
using disposable backend fixtures. It opens a completed project; inspects all
three employees, two exact submission/review attempts, findings, skipped checks,
file diff and command logs; inspects agent usage; saves a new manual model slug;
checks the historical configuration remains unchanged; reconciles an interrupted
Reviewer fence with unknown billing; explicitly resumes/completes and refreshes;
starts a subsequent run, approves its exact runtime permission, completes it and
checks the new model on a successful Developer call receipt. It checks narrow
viewport overflow and scans all observed JSON responses for the configured secret
sentinel, credential name, authorization headers and environment fields.

The recovery fixture in `app/dev/inspection.py` executes existing backend workflow/
file/approval boundaries, interrupts immediately after a committed provider fence,
and closes/reopens SQLite before application startup reconciliation. It has no
production crash/fixture-mutation endpoint. `AI_OFFICE_M52_FIXTURE=1` opts into two
seeded projects under `app.dev.browser`; normal `app.main` is unchanged.

Run from `apps/api` with its virtualenv activated:

```bash
PYTHONPATH=. python -m unittest discover -s tests -q
```

Run from `apps/web` with that virtualenv in PATH:

```bash
npm run contracts
npm test
npm run typecheck
npm run test:e2e
npm run verify:browser
npm run build
```

`verify:browser` now runs the entire suite in headed Chromium; `verify:m52` runs
only the M5.2 headed inspection scenario. Tests use ports 8011/3011. The inspection
scenario runs first because the controlled recovery project is initially active;
it completes that gate before other workflows. Browser actions need no direct API
mutations. For pause verification, wait for the snapshot's pending invocation,
not merely its earlier SSE activity entry, before capturing a command version.

Screenshots under ignored `apps/web/test-results/`: `m52-evidence.png`,
`m52-usage.png`, `m52-recovery.png`, `m52-narrow-agent.png`, plus the existing
permission/pause/refresh/completed workflow screenshots. Browser verification uses
controlled providers and real disposable files/commands, not a billed live
provider. Unknown pricing is intentionally exercised. This does not validate live
provider credentials, model availability or pricing accuracy for a user's provider.

Final verification totals: **458 backend tests**, **85 frontend tests** (6 files)
and **5 Chromium E2E scenarios**. M5.2 adds 13 backend tests, 25 inspection UI tests,
one command-refresh controller regression and one complete browser scenario.
Retained-run selection is checked after the new-model run completes: selecting
its prior run restores the old captured model while primary run state remains
completed; selecting Current / latest restores the new model.

Agent details also query the latest 50 committed events scoped to the inspected
run. SQLite selects this bounded window directly; the memory adapter has matching
semantics. Opening a completed/historical project therefore shows durable recent
activity without a second SSE stream. A backend test checks ordering, uniqueness,
run isolation and bounds; browser verification checks retained Developer activity.

M5.2 final result: **COMPLETE**. The full headless suite and full headed suite each
passed all 5 scenarios after the final changes. TypeScript checks, regenerated
OpenAPI client types, production Next.js build and `git diff --check` passed.
Headed screenshots for evidence/diff, usage, uncertain recovery and narrow agent
layout were inspected. Normal workflow and recovery actions used only browser UI.
No browser response or rendered UI exposed the configured secret sentinel, backend
credential fields, authorization headers, hidden environments or private reasoning.
Manual/headed verification used the real local backend with deterministic providers;
live-provider billing/model/pricing verification remains outside this fixture check.
M6 was not started.

## Historical M6 illustration trial — superseded by the tile/sprite redesign

Status: **Rejected visual direction; historical checks only.** The user subsequently
required a composed tile/sprite room. The final implementation and verification
are recorded in the next section; the generated images described here are no
longer served or used by the application.

The initial flat vector room was rejected and replaced with matching Day/Night
raster pixel-art scenes. Manager, Developer and Reviewer are distinct idle sprites
in one coherent room. Compact desk-mounted HTML plates remain crisp. Mobile crops
the same art into three stacked interactive workspaces. Day/Night is persistent
presentation state; all work/handoff semantics remain snapshot/event driven.
The generated assets and exact prompts are in `apps/web/public/office/ASSETS.md`.

### Checks completed after redesign

- **120 frontend tests passed** across seven files: 85 prior tests, 34 office tests
  and one reconnect-boundary controller regression.
- **7 Chromium E2E scenarios passed headless**, including all five M5/M5.2 cases
  and two M6 cases.
- **7 Chromium E2E scenarios passed headed** against real local FastAPI/SQLite,
  the explicit deterministic provider/file/command fixture and Next.js.
- TypeScript, production webpack build, focused Prettier checks and
  `git diff --check` passed.
- Production backend-facing interfaces were unchanged; the prior **458 backend
  test** baseline was not rerun for this visual work. Only the explicitly opted-in
  browser fixture timing was extended for marked M6 projects.

Commands from the repository root:

```bash
npm test --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
npm run test:e2e --prefix apps/web
npm run verify:browser --prefix apps/web
git diff --check
```

This environment used the existing Python virtualenv and installed browsers:

```bash
PATH=/private/tmp/lazy-m43-venv/bin:$PATH PLAYWRIGHT_BROWSERS_PATH=/private/tmp/lazy-m51-browsers npm run test:e2e --prefix apps/web
PATH=/private/tmp/lazy-m43-venv/bin:$PATH PLAYWRIGHT_BROWSERS_PATH=/private/tmp/lazy-m51-browsers npm run verify:browser --prefix apps/web
```

The suite launches and stops its own local servers on ports 8011 and 3011. The
visual fixture uses real committed operations, not fabricated client events or
frontend timers. `AI_OFFICE_M6_VISUAL=1` only extends non-Developer fixture calls
whose context contains `M6 visual verification`; ordinary M5 fixture timing is
preserved. Developer calls retain the existing four-second delay. There are no
live paid-provider calls.

### Coverage and rendered inspection

Unit tests cover role/status projection, current task, all active roles, Idle,
Waiting, Blocked, Error, Done, pause-requested versus paused, permission/recovery,
disconnection semantics, each handoff route, exact review identity/verdict joins,
missing event identity, duplicate events, initial/refresh history suppression,
reset, new live events after reconnect, navigation, unknown cost and theme
persistence. The controller regression closes a real in-memory SSE reader, advances
the snapshot cursor, verifies retained Last-Event-ID, replays older events into the
feed without motion, then accepts a new event into the visual window.

Browser cases operate create/plan/approve/start, exact command permission,
Developer work, pause-requested/paused/resume, submission, Reviewer FAIL, Manager
revision, Reviewer PASS and completion. They open each existing Agent Detail,
TaskHistory/review, Activity and Usage view; toggle/persist lighting; inspect narrow
and mobile layouts; check keyboard focus/activation and reduced-motion CSS; and
refresh during execution. The reconnect case keeps execution running while the
browser is offline, verifies replayed submission has no handoff, then observes a
new revision/assignment acknowledgement. Existing inspection tests still check
retained evidence, settings, recovery and secret-free browser responses.

Headed captures were generated for Day/Night idle, Thinking, assignment/receipt,
permission block, Working, pause-requested, paused, resumed, submission handoff,
Reviewing, FAIL, revision, PASS, completion, all three agent details, task details,
Activity, Usage, night completion, tablet, mobile, reduced motion, disconnection
and reconnection. Rendered Day/Night, Manager Thinking, assignment/receipt,
submission handoff, pause-requested, FAIL/PASS, tablet and mobile screenshots were
visually inspected. The corrected result has textured pixel furniture and sprites,
warm lamps, an enclosed room, consistent role placement, compact desk plates and
readable dashboard UI. It is no longer the rejected flat corporate/vector scene.

Retained headed evidence:

- `docs/screenshots/m6/day-office.png`
- `docs/screenshots/m6/night-office.png`
- `docs/screenshots/m6/mobile-office.png`

Additional scenario captures are in ignored `apps/web/test-results/m6-*.png`.
The missing supplied-reference comparison is explicitly **not verified**.

### Known limits

Two local 1536×1024 PNG assets total approximately 3.6 MB. Characters are fixed idle
sprites; actual work is acknowledged by small state-driven pixel indicators, not
full sprite-sheet acting or locomotion. At most four short live packets are shown;
Activity retains the existing bounded 250-event view. Fast backend work may finish
before a visual acknowledgement is noticed. Mobile uses desk crops rather than
shrinking the whole room. Theme storage can be unavailable; the toggle then lasts
for the current mount only. Initial hydration may briefly show Day before restoring
Night. No new orchestration, model routing, auth, game engine or M7 work was added.


## M6 final tile/sprite scene verification — 2026-10-05

The final scene is hand-authored and composed from tiles, independent furniture
and character sprites, and attached HTML desk cards. It uses a 320×224 logical
room grid, 16×16 reusable floor tiles, 80×64 desk zones, shared indexed pixel art,
integer coordinates and solid palette shading. Desktop is 3×, tablet 2×, mobile
stacks the original 3× desk sprites. Manager is top/center, Developer lower-left,
Reviewer lower-right. No generated illustration, background PNG, scene crop,
blurred/painted shading or game engine is used. Rejected PNG assets were removed
from the application's public assets and retained only in local temporary backup.

### Final verification

- **126 frontend tests passed** in 8 files. Six new sprite-system tests verify
  palette cells, tile/object composition, independent desk/character layers,
  Developer dual monitors, distinct silhouettes and Manager/Reviewer props.
- **7 headed Chromium scenarios passed** against the real local backend/Next.js.
- **7 headless Chromium scenarios passed** after the final sprite-layer changes.
- TypeScript, production webpack build, focused Prettier checks and
  `git diff --check` passed.
- No backend interfaces or execution behavior changed in this redesign. The
  previously verified 458-test backend baseline was not rerun.

Commands used from the repository root:

```bash
npm test --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
PATH=/private/tmp/lazy-m43-venv/bin:$PATH PLAYWRIGHT_BROWSERS_PATH=/private/tmp/lazy-m51-browsers npm run verify:browser --prefix apps/web
PATH=/private/tmp/lazy-m43-venv/bin:$PATH PLAYWRIGHT_BROWSERS_PATH=/private/tmp/lazy-m51-browsers npm run test:e2e --prefix apps/web
git diff --check
```

Existing scenarios verify planning/approval, real permission decisions,
pause-requested versus paused, resume, review FAIL/revision/PASS/completion,
refresh during execution, event replay/reconnect/reset and duplicate suppression.
They retain M5.2 evidence/settings/recovery and secret-safety assertions. Keyboard
focus/activation, reduced-motion animation suppression, persistent themes and
narrow/mobile overflow checks pass. The explicit deterministic backend fixture
performs real durable operations; no client fake-work sequence is used.

### Headed visual inspection

The following final rendered captures were opened and visually inspected, not
merely produced by a test. Each is retained under `docs/screenshots/m6/`:

| Required view | Capture |
| --- | --- |
| Day idle office | `day-office.png` |
| Night idle office | `night-office.png` |
| Manager Thinking | `manager-thinking.png` |
| Developer Working | `developer-working.png` |
| Reviewer Reviewing | `reviewer-reviewing.png` |
| Reviewer FAIL / Manager revision | `review-fail.png`, `revision-handoff.png` |
| Reviewer PASS / completed run | `review-pass.png`, `completed.png` |
| Permission / Blocked | `blocked.png` |
| Paused | `paused.png` |
| Narrow / mobile | `narrow-office.png`, `mobile-office.png` |

Visual review confirmed a repeated tile floor, bounded rectangular room, separate
pixel silhouettes and role-specific desk construction, consistent pixel outline
scale, compact attached role/status/task cards, readable night palette, and mobile
reuse of the same sprites. Manager has a formal outfit/notebook/planning setup;
Developer has a headset/two code displays; Reviewer has glasses/checklist/paper
stack. Active work uses one-pixel hand/document motion and code cursors. Actual
receipts add a brief one-pixel character nod and desk highlight. Paused/blocked
work is static. Existing committed-event identities and replay suppression remain
unchanged; sprite components have no commands or event subscriptions.

### Limits

The scene is deliberately small and fixed; there is no locomotion, physics or
sprite-sheet acting. Extremely narrow screens can constrain the nominal 3× mobile
sprite width to prevent overflow. Fast backend operations can finish before a
brief acknowledgement is noticed; Activity remains the persistent source. Live
provider billing/model availability is outside the deterministic fixture check.
Day/Night local storage may be unavailable, in which case the current mount still
supports the toggle. Startup commands are unchanged. No M7 work was started.

Final result: **M6 COMPLETE**. The authored tile/sprite room and requested headed
visual states were verified. Stop after M6; do not begin M7 automatically.


## M6 supplied-reference implementation — 2026-10-06

This pass supersedes the earlier tile-grid and triangular visual layout. The user
provided the primary reference: broad cozy room, horizontal desk placement,
Lazy Agents branding, left navigation, light dashboard and compact status cards.
The implementation composes empty matching room shells with a transparent atlas
of separate characters, desks, chairs and role equipment. Plants and packet art
remain independent. The built-in imagegen prompts and source paths are recorded
in `apps/web/features/office/sprites/M6_PROMPTS.md` and `README.md`.

Verification:

- 125 frontend tests pass; production webpack build including TypeScript passes.
- All 7 existing headed Chromium workflow/regression scenarios pass against the
  real local FastAPI/SQLite backend and Next.js, using deterministic providers.
- A separate responsive layout scenario passes at 1660, 1280, 820 and 390 CSS
  pixels, in both Day/Night. It checks all three independent station layers,
  attached card bounds, absence of horizontal overflow, and plan inspection.
- The M6 workflow captures also assert attached task/review cards fit inside the
  room through planning, handoffs, permissions, pause/resume and completion.
- Day, Night, tablet and stacked mobile captures were visually inspected. Final
  reference captures are retained in `docs/screenshots/m6/reference/`.
- `git diff --check` passes. Existing uncommitted work is preserved; no production
  backend files were edited by this reference pass. No M7 work was started.

The isolated M6 run initially hit the seeded interrupted recovery fixture's
application-wide active-run gate. Running the suite in its existing order resolves
that fixture through normal UI actions. An initial full run then hit live
stale-version pause rejections. Browser checks now explicitly retry through the
existing UI after the stale-version error and refreshed state are visible. This
preserves backend fencing and does not introduce production command auto-retry.
The final headed suite passes with that realistic interaction.

Commands (from `apps/web`): `npm test`, `npm run typecheck`, `npm run build`,
`PATH=/private/tmp/ai-office-m6-venv/bin:$PATH PLAYWRIGHT_BROWSERS_PATH=/private/tmp/lazy-m51-browsers npm run verify:browser`,
and the same environment with `npm run test:e2e -- --grep 'M6 reference layout'`.
Localhost binding required sandbox approval. Backend tests were not rerun because
backend behavior was outside this change's scope.

Limits: the three new generated PNGs total about 4 MB; original assets remain.
Characters use still-frame fallback with state-driven hands, equipment, cursor and
receipt cues, rather than full character animation sheets. Theme storage and
initial hydration retain their existing behavior. Unknown usage/cost stays
Unavailable/Incomplete. No mockup placeholder values appear in runtime UI.
