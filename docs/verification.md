# AI Office verification record

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
