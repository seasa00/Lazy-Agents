# AI Office contracts

Current contract baseline: completed M1–M6. M6's production Office Experience,
Pixel Office, Agent Inspector, pop-out/fullscreen, and integration are frozen.
M7 — Agent Runtime Modernization & Production Hardening is In Progress; M7.1–M7.2 are complete and M7.3 has not started.
The [roadmap](IMPLEMENTATION_MILESTONES.md) defines migration constraints.
M7.1 adds `DeveloperToolAdapter` (`app/agents/langchain_layer.py`), which
binds LangChain tools to a single Developer attempt/generation and delegates file
operations and configured command/test profile requests to `WorkspaceToolGateway`.
`AgentRuntime` executes declared tool calls with a bounded count and records each
provider request through its existing call record callbacks. OpenRouter advertises
native tool support. The command adapter accepts only a configured profile name;
argv, executable, cwd, environment, timeout, and output bounds remain application
owned. Manager and
Reviewer retain their existing provider structured-output and domain validation
boundaries; wrapping these calls in LangChain would add no behavior or safety
benefit in M7.1. These additions do not change domain contracts. LangChain/LangGraph must preserve domain and
SQLite ownership, mandatory Permission Gateway enforcement, immutable evidence,
exact-submission reviews, accounting, idempotency, and explicit recovery.
Graph checkpoints, if introduced, hold execution/resume state only. Runtime
traces must be real and redacted and must not expose hidden chain-of-thought.

### M7.2 orchestration boundary

`Orchestrator` exposes the runner's initialize, approve, step, and
run-until-stopped operations. `LegacyOrchestrator` is the default;
`LangGraphOrchestrator` is selected explicitly with `make_orchestrator('langgraph',
...)` for isolated comparisons. Both use the same `WorkflowRunner` operation
boundary, `WorkflowControls`, domain validators, gateway, store, and
`AgentRuntime`. Graph nodes route the persisted phases: Manager plan and task
assignment, Developer, Reviewer, Manager acceptance or revision, and Manager
finalization. Reviewer PASS only selects the Manager acceptance node; domain
validation still commits acceptance. Reviewer FAIL selects the Manager revision
node; the existing three-round limit remains authoritative. Ready tasks are
selected by the existing scheduler and Manager assignment validation.

`WorkflowGraphState` holds only run/task/attempt/submission/review identities,
phase, generation, status, and a per-step progress flag. Nodes reload the run
from the store and fence execution against current phase, task, attempt, and
generation. There is no graph checkpointer or graph-owned domain state.
Approval waiting ends the graph invocation; the existing durable M7.1
continuation is resumed by a later invocation. Recovery, cancellation, pause,
events, permissions, usage/cost, and evidence remain domain-owned.

### M7.1 command/test continuation

`WorkflowState.tool_continuations` stores application-owned `ToolContinuation`
records in the durable run row. A `REQUESTING_APPROVAL` seed is committed before
the existing gateway creates its durable intervention. Recovery matches that seed
to the exact persisted permission request and audit receipt, then reconstructs
`WAITING_FOR_APPROVAL` (or the already-decided state) if a crash happened before
the workflow approval commit. A record binds run/task/attempt/invocation/agent,
execution generation, configured profile request, existing permission ID, stable
command operation ID, provider request reference, explicit tool-loop context,
tool/provider/retry counters, and state. It contains normalized JSON strings only;
it never stores a Python coroutine or LangChain object. Run snapshots expose the
continuation metadata but omit retained context, arguments, and tool output.

The command tool only creates the existing `CommandApproval`. The runtime marks
the provider response as a successful, accounted model request, raises a distinct
`WAITING_FOR_APPROVAL` control transfer, and returns from the synchronous runner.
The runner commits the continuation and enters `waiting_for_user`; it does not
run another model request or command while approval is pending. Approval or denial
updates the existing intervention and continuation. An approval is executed on a
fresh worker step; denial becomes a structured tool result and can resume the
bounded Developer loop. The same invocation ID and monotonically increasing call
numbers are retained across the boundary.

Before execution, the runner verifies the exact approval/profile/request,
generation, current task, active attempt, invocation snapshot, workflow approval,
and recovery gate. A stable `op_` operation ID binds the command to its prepared
and executing receipts. A prepared command fence proves the start boundary was
not crossed, so the same approved operation may resume. Once the executing fence
is durable, a restart treats an absent result as uncertain and recovery never
replays it. An operator may reconcile the command, but the Developer continuation
cannot invent stdout, exit status, or test evidence for an uncertain result.
Successful test results use the existing version-bound `TestEvidence`; captured
submissions remain authoritative.

Cancellation and scope/generation changes invalidate pending continuations and
approvals. Duplicate decisions are idempotent; operation identity and the durable
start fence prevent a second launch. If a crash occurs after a later file tool
starts but before its result is checkpointed, recovery blocks that continuation
for intervention rather than replaying the tool. Provider usage continues to be
recorded once by `AgentRuntime`; waiting does not create an additional model call.

Milestone-specific sections below retain their historical scope. In particular,
earlier visual asset descriptions are records of those passes, not instructions
to replace the accepted Pixel Office or reopen M6.

The implementation uses standard-library frozen dataclasses with strict
`from_dict` parsers. Missing and unknown fields are rejected. `to_dict()` is
the JSON-compatible representation used by the provider boundary and CLI.

## Agent definitions

Owner: `apps/api/app/domain/agents.py`

- `AgentKind` has exactly `MANAGER`, `DEVELOPER`, and `REVIEWER`.
- `DEVELOPER` is the canonical name for the blueprint's initial Worker
  workflow position. The configurable `role` remains separate.
- Default agent definitions have no static tools or permissions. The runner
  supplies a bounded Developer tool set only for providers declaring tool support;
  every tool delegates through the trusted application-owned gateway.
- `AgentDefinition.snapshot()` returns immutable configuration with a
  SHA-256 digest.

## Role contexts and structured outputs

Owners: `apps/api/app/context/builder.py` and
`apps/api/app/agents/contracts.py`

- Context is structured project state, not conversation history.
- Role allowlists, required sections, source versions, configuration digests,
  and context size bounds remain enforced.
- Preserve `manager_plan.v1`, `developer_submission.v1`, and
  `review_result.v1`; the provider adapter's JSON Schemas mirror these names.
- `parse_agent_output()` remains the final application-level validation gate,
  even when a provider advertises Structured Outputs.

## Provider and invocation boundary

Owners: `apps/api/app/providers/base.py` and
`apps/api/app/agents/runtime.py`

- `Provider.complete(ProviderRequest) -> ProviderResponse` remains the
  provider-neutral interface.
- `ProviderCapabilities` declares structured-output, tool, usage, and model
  support. A configured provider/model that cannot satisfy structured output is
  rejected before submission.
- Typed provider failures distinguish configuration, capability, transient,
  rate-limit, timeout, and response failures.
- `UsageSnapshot` records total input, cached input, uncached input, output,
and total token counts. Cached input is a subset of total input.
- `AgentRuntime` defaults to one call for M1.1 compatibility. M1.2 callers
  may set bounded transient attempts and bounded repair calls. Every submitted
  call receives a local request ID and an `LLMCallRecord`, including failures
  and retries.
- Failed calls may have unknown usage; zero is never fabricated for unknown
  usage. `AgentInvocation` exposes final validated output, per-call records,
  and aggregate estimated cost when pricing is known.
- Provider tool calls are rejected unless a Developer invocation explicitly
  supplies its bounded LangChain tool set. Each currently supported file tool
  delegates to `WorkspaceToolGateway`; its execution boundary is checked before
  dispatch. The configured-profile command/test tool uses the durable approval
  continuation described above.
- M2.2 adds optional `output_schema`, bounded structured `workflow_context`, and
  `before_call` to `AgentRuntime.invoke`. Manager can request
  `manager_decision.v1` or `final_result.v1`; other roles retain their schemas.
  Context manifests include the workflow fields and their digest/size.
  The guard runs before every initial/retry/repair call. Guard interruptions and
  non-transient failures preserve all already-attributed call records.

## OpenRouter OpenResponses adapter

Owner: `apps/api/app/providers/openrouter.py`

- Uses `POST https://openrouter.ai/api/v1/responses` with `store: false`,
  instructions, a serialized role context, and strict JSON Schema Structured
  Outputs.
- Credentials come from an explicit config value or backend-only
  `OPENROUTER_API_KEY`; the CLI does not print or persist it.
- Model identifiers are OpenRouter slugs such as `openai/gpt-4o-mini`. The
  adapter does not hard-code a provider/model allowlist, so Anthropic, Google,
  and other OpenRouter slugs remain selectable. The adapter normalizes response
  IDs, structured JSON output, tool calls, and usage including cached tokens.
- Structured-output requests send `provider.require_parameters: true` so
  OpenRouter routes only to endpoints that accept the required parameters.
- During M7.1, OpenRouter serializes only the Developer tool schemas supplied by
  the runner. The shared runtime rejects undeclared calls and enforces the tool
  call bound; it does not add unrestricted shell access.

## Usage and pricing

Owners: `apps/api/app/usage/records.py` and
`apps/api/app/usage/pricing.py`

- `LLMCallRecord` contains local request/invocation IDs, attempt/purpose,
  provider/model, outcome, provider request ID, usage provenance/completeness,
  optional price snapshot, optional Decimal cost, and safe error details.
- `PricingTable` loads explicit per-million-token rates. Cost is calculated as
  uncached input × input rate + cached input × cached rate + output × output
  rate. Unknown model pricing returns no cost estimate and is reported as
  unknown rather than zero.
- `config/model-pricing/openrouter.json` is a checked-in rate snapshot and must be
  refreshed deliberately when rates change.

## Deterministic development provider

Owner: `apps/api/app/providers/mock.py`

`DeterministicMockProvider` is offline, visible, and stable. It remains the
default CLI/test double, returns optional normalized usage, and performs no
network, file, command, database, or tool operation.

## Shared project and run state

Owners: `apps/api/app/domain/projects.py` and
`apps/api/app/domain/tasks.py`

- `ProjectState` owns the structured goal, requirements, decisions, tasks,
  runs, requirement version, active-run ID, and project version.
- `RunState` owns the run lifecycle, approved Manager plan, task IDs, current
  task, configuration snapshot, execution generation, and run version.
- `Task` owns its immutable brief, dependency IDs, lifecycle status, separate
  canceled disposition, revision, and entity version. A canceled task is never
  completed, and ordinary dependency waiting remains `BACKLOG`.
- Run statuses and task statuses are separate explicit enums. No UI flag or
  free-form agent message is authoritative workflow state.

## Planning, transitions, and events

Owners: `apps/api/app/orchestration/planning.py`,
`apps/api/app/orchestration/transitions.py`, and
`apps/api/app/domain/events.py`

- `validate_manager_plan()` is the deterministic gate after structured Manager
  parsing. It rejects duplicate IDs, missing dependencies, self-dependencies,
  and dependency cycles before any state mutation.
- The Manager proposes a `ManagerPlan`; `StateStore.propose_plan()` validates
  and materializes it, commits its requirements/decisions and requirement
  version, while `approve_plan()` is the only plan-approval commit.
- `ready_tasks()` returns only active unfinished tasks whose prerequisites are
  active `DONE` tasks. Approval moves only root tasks to `TODO`; completing a
  prerequisite deterministically promotes dependent tasks.
- `assert_run_transition()` and `assert_task_transition()` define the legal
  lifecycle edges. Invalid transitions fail before state or events change.
- `DomainEvent` is a versioned envelope with project/run/task references,
  actor, sequence, correlation fields, and structured payload.

## State-store boundary

Owners: `apps/api/app/persistence/store.py` and
`apps/api/app/persistence/memory.py`

- `StateStore` is the narrow command/query interface for projects, runs,
  plans, approvals, task selection, transitions, cancellation, and events.
- `InMemoryStateStore` is thread-safe and commits a state update and all its
  associated events in one operation. Events have monotonic per-project
  sequences; entity versions increment on mutation.
- At most one non-terminal run may exist across the application. Outstanding
  canceled operations must settle before another run can start. The implementation is
  intentionally process-local; SQLite durability, recovery, and HTTP/SSE are
  later milestones.

## M2.2 workflow authority

Owners: `orchestration/runner.py`, `controls.py`, `limits.py`,
`domain/workflow.py`, `domain/submissions.py`, `domain/reviews.py` (under `apps/api/app`).

- `WorkflowRunner.initialize()` installs `WorkflowState` exactly once. It may
  adopt an unexecuted M2.1 plan, or generate a Manager plan from a draft run.
  `approve()` records explicit `plan_approved`; lifecycle status alone is not approval.
- `step()` reserves one operation in an atomic reducer and releases the store
  lock for provider IO. `run_until_stopped()` stops at approval, pause, block,
  cancellation or completion. Another runner cannot reserve the pending operation.
- Manager assignments must identify approved dependency-ready tasks. The current
  task remains owned through review and decision. Generic legacy store mutations
  reject managed runs; they cannot synthesize DONE or COMPLETED for a workflow.
- `TaskAttempt` identifies run/task, cumulative attempt number, generation and
  requirement version. `SubmissionManifest` validates the expected immutable ID,
  version, task, evidence and digest. No revision overwrites a previous manifest.
- A review round is charged when a distinct submission is admitted. Technical
  retries/repairs stay within that round. `ReviewRound` requires the exact current
  submission and a unique assessment for every criterion (`c1`, `c2`, …).
  Criteria include task criteria and current project requirements. PASS cannot
  contain failed assessments or blocking findings.
- Manager acceptance requires current PASS evidence. Revision requires a
  `RevisionBrief` linking task, submission, review, fixes, criteria and remaining
  rounds. Final output must reference every required task and accepted submission.
  Cancellation never satisfies a dependency or completion requirement.

## Lifetime limits and controls

- `ExecutionLimits`: 3 review rounds/task, 60 invocations/run, 100 provider
  calls/run, 4 calls/invocation, 3 transient attempts, 1 structured repair,
  20 tasks created/run, 2 replans/run, 200 workflow iterations.
- All technical attempts count against provider-call caps. Counters remain on
  the run across pauses, revisions, scope changes and replanning. Exhausted
  budgets block; `resolve()` cannot replenish them. Replanning is restricted to
  unapproved plans; executed tasks cannot be replaced to escape safeguards.
- `pause()` acknowledges immediately only when no operation is outstanding;
  otherwise it requests a pause. After the call settles, acknowledgment prevents
  every new operation and technical retry until `resume()`.
- `cancel()` increments generation and prevents later results from advancing
  state. `block()`/`resolve()` preserve the phase. `instruct()` queues bounded
  instructions that enter structured context at the next operation boundary.
- `change_scope()` increments generation, pauses, clears current acceptance and
  invalidates all tasks conservatively. Immutable historical evidence/counters
  remain. Resume waits for old operations to settle; current configuration
  digests must match the configured agent definitions.
- `StateStore.atomic_update()` accepts a trusted deterministic reducer returning
  state plus events, with optional expected project version. It commits both
  under one lock. No provider invocation occurs in the reducer.
- `usage.recorded` events link each retained `LLMCallRecord` to run, task and
  invocation, including stale/canceled responses. Workflow state and events
  remain process-local and are exposed through defensive snapshots.

## Preserved synthetic tool boundary

Owners: `apps/api/app/tools/contracts.py`, `memory.py`.

`ToolRequest`, `ToolResult`, and `ToolGateway` define a narrow future gateway
boundary. `InMemoryToolGateway` is a pure, immediate synthetic-evidence capture
operation for Developer submissions. Reviewer sees immutable captured evidence
and cannot write it. Paths are labels only: there is no filesystem or shell
implementation. The runner captures structured summaries/test reports, explicitly
marked SIMULATED, without treating them as real execution evidence.

## M3.1 workspace policy and gateway

Owners: `permissions/policy.py`, `tools/gateway.py`, `tools/files.py` (under
`apps/api/app`).

- `WorkspacePolicy` binds one existing, non-symlink root directory, resolving
  OS ancestor aliases once, and rejects the filesystem root. The gateway pins
  the root device/inode identity and denies subsequent root replacement.
- Paths must be canonical slash-separated relative strings. Absolute paths,
  empty segments, dot/dot-dot, backslashes, colons and NUL are rejected. `.` is
  accepted only for a root listing. Each directory component opens with
  `O_DIRECTORY | O_NOFOLLOW`; file opens use `O_NOFOLLOW | O_NONBLOCK`.
- Default protected components: `.git`, `.agents`, `.codex`, `.aws`, `.ssh`,
  `.gnupg`, `.runtime`, `.artifacts`, `__pycache__`, `.env*`, `*.pem`, `*.key`,
  `credentials`, `credentials.json`, `secrets.json`. Checks are case-insensitive;
  configured `protected` relative subtrees extend them. Listing hides protected
  entries, symlinks, hardlinks and special files. Direct access denies them.
- Only singly linked regular UTF-8 files are supported. Existing parent
  directories are required. Listing is nonrecursive. Limits default to 65,536
  file bytes, 262,144 serialized result/snapshot bytes, and 1,000 scanned entries.
  Oversize results are rejected, never silently truncated.
- `PermissionDecision` permits Developer live list/read/write/edit/capture.
  Reviewer and Manager may list/read only with an exact captured submission ID,
  attempt ID and generation. All other operations/role combinations are denied.
- `FileToolRequest` carries operation, trusted actor, attempt ID, generation,
  relative path, content, expected hash, exact edit strings, optional submission
  ID and capture paths. Actor/attempt identity belongs to the application caller,
  never model-generated tool arguments. `FileToolResult` returns content/hash,
  entries or a frozen `CapturedSubmission`.
- Existing-file write/edit requires the exact lower-case SHA-256 hash from a
  prior read. `expected_hash=None` explicitly means the target must not exist;
  omitted or malformed hashes are denied. Edit replaces exactly one nonempty
  match. Repeated matches are rejected. External edits yield `FileConflict`.
- Writes check the hash, stage a bounded temporary sibling, flush/fsync, recheck
  current bytes and execution control, then atomically replace the target.
  Existing permission bits are preserved; new files use mode 0600. Temporary
  files are removed on success or failure. No deletion tool is exposed.
- `WorkspaceToolGateway` fails closed without a bound mutation guard.
  `WorkflowRunner.file_tool()` is the trusted production entrypoint and runs
  under the state-store lock, serializing against pause/cancel/scope controls.
  It emits `file.operation` with the tool-call ID/outcome. The guard checks an
  approved RUNNING run, Developer phase, latest attempt and matching generation
  before each mutation, including capture, and immediately before replacement.
- A pause during a Developer provider call retains its usage and prior file
  edits but does not capture the result. Resume repeats that phase. Cancellation
  retains usage and ignores late results. Neither operation undoes prior writes.
- Frozen `ToolCallRecord` includes unique ID, actor, operation, attempt,
  generation, path, submission, outcome and successful mutation hashes.
  Success, denial, conflict and filesystem error outcomes are recorded without
  file contents or raw OS errors. Gateway history is exposed as an immutable tuple.
  Automatic capture also has a record; `submission.admitted` links its call ID.

## M3.1 captured submission evidence

Owners: `tools/submissions.py`, `domain/artifacts.py`, `domain/submissions.py`,
`orchestration/runner.py` (under `apps/api/app`).

- Changes are tracked per attempt/generation, retaining each file's original
  bytes (or absence) and latest successful gateway write. A reverted file is
  removed from the manifest. Unknown external-only files are never claimed as
  gateway changes. Failed operations do not enter change tracking.
- Capture requires a nonempty exact, duplicate-free set of changed paths and
  `attempt_id + ':submission'`. It re-reads changed paths and rejects mismatches.
  This captures gateway-produced versions, not model-provided file summaries.
- Frozen `FileChange` retains path, before/current bytes, SHA-256 hashes and
  unified diff (including missing-final-newline markers). `CapturedSubmission`
  retains identity, attempt, generation and a sorted tuple of file changes.
  Its canonical JSON contains actual content, hashes, type and diffs; the digest
  hashes that JSON. Artifacts live solely in application memory, outside the
  writable workspace. Existing captures cannot be overwritten; attempts seal.
- `SubmissionManifest.files` is optional for backward compatibility. Real-file
  admission validates the model submission identity/version first, normalizes
  change types from actual before/after state, and binds serialized file evidence
  to the manifest digest. Model test claims are explicitly UNVERIFIED.
- Reviewer role context and snapshot reads use the captured values. There is no
  fallback to live files. Later modification/removal of the source cannot affect
  evidence or its digest. A later attempt gets independent evidence and identity.
- Existing role-context size limits remain enforced in addition to tool limits;
  too-large evidence blocks the invocation. No truncation or fabricated test
  execution is used to fit the context.
- These are POSIX, cooperative-process safeguards, not an OS sandbox or durable
  audit system. A concurrent external process can race the final hash check or
  move an opened directory. Multi-file capture is sequential rather than a global
  filesystem snapshot. State/event commits and filesystem writes are not a crash-
  atomic transaction. Only disposable workspaces were used for verification.
- M3.2 extends this capture with version-bound command evidence below.
  Provider-native tool execution, installation, deletion, SQLite, FastAPI,
  frontend and M4.1 remain unimplemented.

## M3.2 exact command requests and permission interventions

Owners: `domain/commands.py`, `permissions/policy.py`, `tools/gateway.py`,
`orchestration/controls.py`, `orchestration/runner.py` (under `apps/api/app`).

- `CommandProfile(name, executable, args, is_test)` is trusted application
  configuration: one canonical absolute executable and an exact immutable argv
  tuple. No profiles exist by default. Recognizable shell executables are rejected;
  there is no free-form shell string or `shell=True` interface. Profiles themselves
  do not confer approval. Interpreters and their input code remain trusted code.
- Frozen `CommandRequest` includes application-owned actor, attempt, generation,
  profile name, executable, argv tuple, workspace fingerprint, relative cwd,
  environment tuple, timeout and per-stream retained-byte limit. It rejects mutable
  argument/environment containers, NUL arguments, invalid identities, non-finite
  timeouts, invalid bounds and more than 16,384 argument/environment characters.
- `WorkspacePolicy.decide_command()` allows only Developer to request execution.
  Reviewer and Manager cannot request or execute, including with a Developer's
  otherwise-valid approval. Provider-generated arguments never supply actor identity.
- `WorkflowRunner.request_command()` calls the gateway and records a pending
  `CommandApproval` on a successful scope check. `workflow.pending_permissions`
  stops ordinary workflow progression until each intervention is resolved.
- `WorkflowControls.resolve_command(id, approved=bool, reason=...)` is a trusted
  human-control API, not an agent tool. It explicitly approves/denies one pending
  intervention, preserves a bounded decision reason, and emits
  `command.permission_decided`. The gateway records each request and valid decision,
  including denials, and rejects attempted approval of a changed scope.
- Approval scope digest includes the full request, canonical root, executable
  content hash, effective child environment and full configured profile (including
  its test designation). Exact request equality and digest equality are required
  again at launch. Changing args, cwd, env, limits, role, attempt, generation,
  workspace, executable or profile invalidates reuse. No prefix/wildcard approvals.
- Approvals progress pending → approved/denied → consumed (approved only).
  Cancellation/scope changes invalidate pending and approved permissions and clear
  pending interventions. A rejected launch does not consume a still-valid approval;
  an attempted actual spawn does, even if OS launch fails. Approvals are single-use.

## M3.2 launch and process lifecycle

Owner: `tools/commands.py`, with gateway/runner ownership.

- `WorkflowRunner.command_tool(request, approval_id)` is the trusted execution
  entrypoint. It verifies no pending provider/command/permission operation, checks
  run-level command budget, validates scope/approval, rechecks pause/cancel and
  launches while holding the state-store lock. The run reserves its existing
  pending-operation slot. Poll/drain occurs outside the lock; controls remain live.
- The gateway independently enforces one active command and disallows file
  write/edit/capture while it owns a running command. New commands are rejected,
  never queued concurrently. Workflow provider calls cannot start during commands.
- Cwd must be an existing, canonical workspace-relative directory. Root identity,
  protected-path and component no-follow checks reuse M3.1 safeguards. Commands
  launch with the configured root/cwd; no arbitrary outside cwd is accepted.
- `Popen` receives `[executable, *args]`, `shell=False`, `stdin=DEVNULL`, separate
  stdout/stderr pipes, `close_fds=True`, `start_new_session=True`. Argument text such
  as dollar expansion, semicolons, spaces, globs and pipes is passed literally.
- Child environment starts from a fixed map: PATH `/usr/bin:/bin`, LANG/LC_ALL `C`,
  TZ `UTC`, PYTHONDONTWRITEBYTECODE `1`. Only LANG, LC_ALL, TZ and PYTHONHASHSEED
  may be overridden with unique, bounded values. No inherited API keys, PYTHONPATH,
  startup hooks, loader variables, proxies or HOME. Approved code can still read
  credentials from disk or obtain outside resources; this is not secret isolation.
- `CommandLimits` defaults: 20 launches, 60 permission requests, 30 s maximum
  timeout, 65,536 retained bytes per stream, 2,097,152 workspace bytes and 2,000
  fingerprint entries. Requests default to 10 s and 8,192 bytes per stream. Directory
  fingerprint depth is capped at 64; executable hashing is capped at 128 MiB.
  Count/byte limits are positive integers; time limits are finite positive values.
- The collector uses nonblocking pipes and selectors to drain both streams fairly.
  Excess bytes are discarded while setting stream-specific truncation flags;
  output floods cannot bypass monotonic timeout or stop checks. Invalid UTF-8 is
  replaced, then bounded again so retained encoded text respects the byte limit.
- Pause, cancel, blocked state, stale generation or lost operation ownership stop
  execution. The POSIX process group receives SIGKILL, and the direct child is
  waited/reaped. Normal leader exit also triggers cleanup of any remaining group
  members; a leader that exits while children remain is `terminated`, not success.
  Draining and waiting have bounded cleanup waits. Pipe holders outside the group
  cannot make the collector wait indefinitely; incomplete cleanup is not success.
- Incomplete cleanup retains the command/operation reservation and blocks the run
  for manual intervention. Further commands, mutation, resume/resolution and new
  runs cannot proceed while that reservation remains. There is no automatic
  recovery path in M3.2; a failed cleanup must not allow overlapping execution.
- A pause during execution settles as PAUSED after the command result is retained;
  resume does not replay it or reuse its approval. Cancellation keeps the run
  canceled, retains the outcome, clears the settled operation and never admits late
  success. Scope changes likewise cancel a running old-generation command.
- Frozen `CommandResult` retains request/approval ID, test designation, outcome,
  real exit code (or None for launch error), bounded stdout/stderr, truncation flags,
  UTC start time, monotonic duration, before/after workspace versions, PID and
  cleanup status. `log_ref` is `<command_id>:logs`; logs remain embedded immutable
  application-owned values. Success requires outcome `succeeded`, exit 0 and
  complete cleanup. Failed, timed-out, canceled, paused, terminated and error
  results are never represented as successful.
- `CommandAuditRecord` covers request/decision/launch/result/invalidation with
  unique ID, actor, attempt, generation, approval ID, outcome and reason. The gateway
  exposes immutable history tuples; runner events link the corresponding IDs.
  `WorkflowState.command_results` retains every attempted launch result, including
  cancellation and launch errors. JSON snapshots include command history and
  captured UTF-8 files. No database is involved.
- Launch/result caps persist on the run; gateway lifetime counters additionally
  bound launches and permission requests. Pause, resume, cancellation, scope changes
  and retries do not reset counters. Replacing application-owned gateway configuration
  is not an agent capability. Existing provider/tool/context limits remain active.

## M3.2 version-bound test evidence

Owners: `tools/commands.py`, `tools/gateway.py`, `domain/artifacts.py`,
`domain/commands.py`, `orchestration/runner.py`.

- `workspace_version()` traverses the entire configured workspace using no-follow
  descriptors, bounded entries/bytes/depth. It hashes regular-file contents, paths,
  mode/change timestamps and directories. Protected files contribute hashes only;
  their contents are never returned to agents. Binary files can be fingerprinted.
  Symlinks, hardlinks, special files, replaced roots and observed concurrent changes
  fail closed. A fingerprint failure after execution makes evidence stale.
- Requests and approvals bind the pre-run version; results capture before/after
  versions. `TestEvidence` associates a result with the current or captured workspace
  version and marks it stale if either run version differs. `passed` requires a
  successful command plus fresh evidence. `CommandResult.succeeded` describes the
  historical process outcome, not whether its tests remain valid for live content.
- Edits to implementation, tests, previously unchanged files or protected files,
  additions/removals and tracked metadata changes invalidate live evidence. Rewriting
  previous bytes does not ordinarily restore the previous version because change
  timestamps differ. Tests that create/change files are conservatively stale too.
- Only configured `is_test=True` profiles produce test evidence. A general command
  or model-provided test report cannot be promoted into a verified test result.
- Submission capture rechecks the workspace version around file capture and adds
  frozen `workspace_version` and `tests` values to `CapturedSubmission`. Canonical
  serialization (and therefore the submission digest) includes the command results,
  logs, scope, versions and freshness flags. Oversized evidence fails before sealing.
- Reviewer receives these captured values in structured context. For each test
  profile, the latest captured result must be fresh and successful before Reviewer
  PASS is admissible. Retesting after an edit supersedes old evidence for that
  profile while retaining its history. Failed/stale tests cannot silently establish
  acceptance of new content. With no captured tests, model claims remain UNVERIFIED.
- Later live changes make live evidence stale but cannot alter the historical
  captured submission, its reviewed bytes, recorded test outcome or manifest digest.
  A new version needs a new attempt/test/approval; no live-file fallback is used.

## M3.2 safety and verification limits

Approved commands are **trusted local code execution**, not OS sandboxing. Cwd,
argv, profiles and environment are enforced launch scopes; approved programs keep
the service user's OS privileges and can access paths outside the root, modify
protected files, use the network, start shells, or detach children. There is no
network isolation, memory/CPU/cgroup sandbox or guaranteed whole-process-tree
containment. Only the original POSIX process group is controlled. Detached processes
that close inherited pipes may be undetectable; those retaining pipes lead to a
bounded cleanup failure rather than an indefinite wait.

Verification uses macOS/POSIX disposable workspaces only. Fingerprints are sequential,
not atomic filesystem snapshots; external writers, path/executable replacement and
privileged metadata manipulation can race checks. Outside-workspace libraries and
runtime dependencies are not captured. Cwd/path checks do not prevent approved code
from subsequently changing directories. OS spawn and filesystem calls themselves
are synchronous, although command execution and cleanup have bounded waits.

Approvals, logs and evidence are process-local. There is no durable intent log,
restart recovery or crash-atomic transaction across process spawn, files and state.
Provider-native tool dispatch stays disabled; no package installation, deployment,
deletion tool, SQLite, FastAPI, frontend or M4.1 work was added. The requested offline
suite and real-process demonstration passed; the roadmap's additional live-provider
smoke remains unverified because no OpenRouter key is available in this process.

## M4.1 durable StateStore (supersedes earlier process-local persistence limits)

`persistence/operations.py` shares existing command behavior between
`InMemoryStateStore` and `SQLiteStateStore`. Existing methods and returned domain
values are preserved. `WorkflowState` adds agent snapshots and invocation records
at the end of its fields, preserving positional arguments. Each invocation binds
an agent identity and configuration digest, phase and execution generation.

The protocol adds `record_tool(project_id, run_id, record, approval=None)` and
`usage(project_id, run_id=None)`. The former atomically commits an immutable audit
record, its `tool.audit` event and, where applicable, current permission state.
Repeated identical audit IDs are idempotent; conflicting reuse fails. Usage is
computed from call records, never event-delivery counts. SQLite supports explicit
`close()` and context-manager ownership; construction migrates but never resumes.

Schema version **2** uses these authoritative tables:

| Tables | Purpose |
| --- | --- |
| `projects`, `runs`, `tasks` | Current domain state, versions, active-run constraint |
| `dependencies`, `run_tasks` | Foreign-key checked task/dependency/run membership |
| `decisions` | Existing project decision records |
| `agents`, `invocations` | Immutable configuration snapshots and invocation attribution |
| `attempts`, `submissions`, `reviews` | Immutable evidence identities and parent relations |
| `llm_calls` | Unique call IDs, provider/model/request, attempt/purpose/status, token breakdown, provenance/completeness, prices, Decimal cost text and errors |
| `command_results`, `tool_records`, `interventions` | Outcomes, intent/audit history and current command permissions |
| `artifact_metadata`, `artifacts` | Submission file paths/hashes and sidecar hash/path/size references |
| `events` | Append-only committed event envelopes |
| `schema_migrations` | Contiguous applied versions and migration checksums |

Bounded domain documents use allowlisted typed JSON within entity tables; there
is no pickle or event-replay reconstruction. Run-owned collections load from their
own tables. Requirements and revision briefs retain their existing project/run
ownership. Dependency validation and workflow authority remain application owned.
SQL additionally enforces parent relations, one application-wide active run,
unique identities, and attempt/review numbers within a task/run.

`migrations/001_initial.sql` creates the schema/constraints and event immutability
triggers; `002_query_indexes.sql` adds event replay and agent accounting indexes.
Migrations run in numeric order in one transaction and verify applied checksums.
Gaps, changed checksums, newer schemas and failed SQL prevent opening/upgrading;
failed upgrades roll back. Migration SQL is packaged with `app.persistence`.

Transactions: acquire the application lock, run the reducer, validate and prepare
all JSON/sidecars, then begin a short `BEGIN IMMEDIATE` transaction. Recheck the
project version, write state/history rows and events, and commit together. On any
failure, all SQL changes roll back. Event-only/no-op reducers and state-only
reducers are rejected. The application lock may encompass existing M3 file or
launch work, but **no SQL transaction is held during external IO**. Provider and
command waits keep their existing outside-lock behavior.

Gateway audit callbacks commit file intent before dispatch and command intent
before spawn. They contain paths, identities and hashes, not file-write content.
Command scope remains on its permission record. Each audit write has its own
short transaction and event. Consequently an attempted/finished side effect can
remain recorded even if a later workflow commit fails; there is no false claim
of filesystem rollback. These callbacks use only the store abstraction.

Events retain all envelope fields and indexed project/run/task references. SQLite
sequence numbers are database-wide, positive and monotonically increasing;
project-filtered queries can have gaps. `after_sequence` remains an exclusive
cursor. Updates/deletions are rejected by database triggers. Memory sequences
remain project-local as before; consumers must depend on ordering, not adjacency.

Costs are stored as decimal text and summed using Python `Decimal`, never SQLite
floating-point `SUM`. Overall/per-agent aggregates include calls, retries
(`attempt > 1`), tokens, estimated cost and completeness flags; review count is
also returned. Unknown or partial usage makes `total_tokens` unknown; missing
pricing/cost or incomplete usage makes `estimated_cost` unknown. Separately named
`known_tokens` and `known_estimated_cost` are partial subtotals, not complete totals.
Duplicate call IDs in a new state are rejected; rewriting an unchanged snapshot
never bills/counts the same persisted row again. Immutable history cannot change.

Captured contents, before images, diffs, serialized submission evidence and command
stdout/stderr live in content-addressed sidecars (`<database>.artifacts` by default).
Files are prepared before the SQL transaction using temporary files, fsync and
rename; SQL stores references and metadata only. Reads validate hashes and sizes
and raise `ArtifactIntegrityError` for missing/corrupt evidence. Backup/copy the
sidecar directory with the database; keep both outside the agent workspace.
Provider objects, API credentials and process environment are never serialized.
Credential-named run configuration entries are rejected; protected workspace files
remain subject to existing capture policy. Explicit allowed command environment
settings are scope metadata, not a copy of the process environment or `.env`.

Local defaults: foreign keys ON, WAL, synchronous FULL, busy timeout 5000 ms.
One local user and one application writer/store instance are supported. Clean
shutdown preserves committed state. **Crash/restart reconciliation, automatic
resume and exactly-once side effects remain unsupported until M4.2.** Unreferenced
sidecar cleanup, process restoration and approval reactivation are not implemented.

## M4.2 restart reconciliation and durable controls

This section supersedes M4.1's absence of restart reconciliation. SQLite schema
version **3** adds `execution_operations` and a run/stage index through
`003_execution_recovery.sql`. Migrations 1 and 2 remain unchanged. Immutable
entity rows keep their original serialized bytes when new optional contract
fields decode to the same domain value; upgrade/reconciliation never rewrites
committed event history or immutable evidence.

### Checkpoints and operation certainty

`domain/recovery.py` defines `ExecutionCheckpoint`, `ExecutionOperation`,
`OperationStage`, `OutcomeCertainty`, `RecoveryIssue` and `RecoveryState`.
Checkpoints identify project/run/task/attempt, phase, invocation/operation,
execution generation, requirement version, recovery epoch, UTC times and the
last committed safe phase/boundary. Run-owned checkpoints change atomically with
run state/events. Tool/provider operations carry their own complete checkpoints.

Operation stages are durable fences:

- `prepared`: intent/metadata is durable; external execution has not been permitted.
- `executing`: permission to execute is durable; execution may or may not actually
  have occurred. A missing outcome here is **uncertain**, not failed/succeeded.
- `settled`: a receipt or an explicit operator decision is durable.

Provider reservation/receipt callbacks preserve local call identity, model,
provider, attempt, purpose, price snapshot and reported usage before workflow
admission. Each request starts only after its execution fence commits. File writes
retain the intended hashes and external before/after bytes before their fence;
commands retain exact request/approval and a diagnostic PID when available.
Every operation write commits its structured event in the same short transaction.
Serialization/artifact IO remains outside SQL transactions.

Certainty is one of `confirmed_success`, `confirmed_failure`, `interrupted`, or
`uncertain`. Confirmed command success requires the existing successful result,
exit 0 and completed cleanup; confirmed command failure describes the observed
process outcome and **does not imply that no files changed**. Provider errors
likewise do not establish zero billing. A prepared operation is interrupted but
provably unstarted under the new protocol. Legacy M4.1 intent/reservation records
without these fences are conservatively uncertain. Protocol-version defaults
preserve that distinction across migration.

### Startup and inspection

Opening SQLite for read-only history inspection does not mutate a run. A reopened
store marks existing run references as needing startup inspection. Backend startup
calls `RecoveryCoordinator.startup()`; `WorkflowRunner` construction ensures this
inspection for its run before exposing execution. The operator CLI also performs
startup inspection on every invocation. There are no SQL statements in recovery
or orchestration code.

Startup reads checkpoints, operation/permission/audit records and artifact
integrity. It retains durable call receipts and command results whose workflow
commit was interrupted. Running work at a safe phase becomes paused; unresolved
work becomes `WAITING_FOR_USER` with a visible restart blocker. Existing canceled,
failed and completed runs remain terminal. Missing/corrupt evidence can be reported
through a metadata-only store path without loading or rewriting the damaged rows;
terminal evidence damage is visible too. Restore exact artifact bytes before it
can be cleared. Inspection/reconciliation never invokes a provider, mutates a
workspace, spawns a command, signals a PID or applies a saved model proposal.

Reconciliation is idempotent while the recovery gate remains active. Original
pause/cancel state, counters, limits, instructions, blocked reason/resume phase,
configuration generations, accepted submissions and review links persist.
Execution generation remains valid for previously accepted evidence; a separate
durable **recovery epoch** advances when entering a new recovery gate and fences
old in-flight work. Provider/tool results must also satisfy execution generation,
requirement version and operation identity checks. Late results are retained for
audit/usage and cannot advance workflow automatically.

### Operator resolution and exact resume behavior

The coordinator and CLI support these controlled actions, with a bounded evidence
reason and optional expected epoch:

| Action | Proof/decision and effect |
| --- | --- |
| `verify-file` | Safely read the target; compare to retained intended-after or before hash. Matching after confirms the intended current content; matching before confirms no surviving target mutation. A different hash blocks. This proves present content, not historical absence of transient/external writes or rollback. |
| `verify-capture` | Validate hashed captured evidence and its generation/requirements; reuse the immutable submission capture. |
| `verify-artifacts` | Re-read all referenced evidence after restoring exact missing/corrupt sidecars. |
| `accept-result` | Explicitly admit a saved, validated successful provider proposal with a bound runner; revalidate phase, invocation, configuration, generation, requirements and ordinary workflow rules. No provider call is repeated. |
| `abandon-provider` | Explicitly abandon the unknown/unadmitted application proposal. Preserve unknown billing and spent limits. A later new invocation in the same phase is operator-authorized, not a claim the earlier request was unprocessed. Provider-native tools remain disabled. |
| `acknowledge-command` | Require explicit operator attestation that processes are quiescent and effects have been inspected. Retain uncertain certainty; do not invent an exit code, test success or cleanup result. Never auto-relaunch. |
| `acknowledge-file` | Equivalent explicit attestation for legacy/file operations lacking hash evidence. Retain uncertainty; never auto-replay the old mutation. |
| `abandon-read` | Abandon interrupted read/list work; no workspace mutation is replayed. |

Unresolved dangerous effects/artifacts prevent proposal admission and resume.
Resolving an issue leaves the run behind the recovery gate. **Only explicit resume**
clears it. Resume validates the epoch, generation/requirements, current attempt or
submission/review link, and non-resettable limits. It clears the abandoned pending
operation, preserves history/counters and restores the saved phase. A developer
retry uses the same valid attempt; a Reviewer retry uses the same immutable
submission and round. Already accepted tasks remain accepted and are not rerun.
A saved successful proposal can instead move to its validated next phase before
resume. Terminal runs cannot resume. Original ordinary blockers remain blocked
until their existing control resolution, and exhausted limits cannot be replenished.

Workspace runs require the workspace gateway on reconstruction. Gateway restoration
loads known changes, captured submissions, sealed attempts, results, approvals and
request/launch counters without executing anything. Permission decisions remain
human controlled; scope and single-use status are rechecked. A consumed command
approval is never revived, including when its prepared operation never launched.
Interrupted/consumed command attempts require a new explicit approval for any later execution. Recovery
never reconstructs a live process from a PID; PIDs are diagnostics only.

### Usage and remaining limits

Unknown in-flight provider calls become immutable interrupted call records.
Current operation receipts can later enrich their effective usage without changing
that original history. Aggregation merges these durable receipts by local call ID,
counting each request once. Unknown charge/usage remains `None`; a reported late
receipt can supply known usage even after abandonment/cancel/scope change. Prepared
or provably unsubmitted requests are excluded from submitted-call totals, while
their conservative limit reservations remain spent.

Recovery supports the existing single-local-user, single-application-writer model.
It does not provide distributed leases, exactly-once execution, automatic resume,
automatic rollback, provider-side request lookup/recovery, or safe attachment to
or termination of processes from a previous backend. Operator attestations can
accept uncertainty but cannot turn it into proof. External filesystem writers,
sequential fingerprints and escaped command descendants retain M3 limitations.
Back up SQLite and its artifact directory together; orphan artifact cleanup is
still deferred. No M4.3 API/SSE/UI or worker infrastructure is introduced.

## M4.3 HTTP control surface and baseline SSE

Owners: `app/main.py`, `app/api/{schemas,service,events}.py` and the StateStore
query/admission boundary. This supersedes earlier statements that HTTP/SSE is
unimplemented. The M5.1 browser contract is documented below. SQLite schema **4** adds `api_commands`;
prior migrations and immutable history remain unchanged.

One FastAPI lifespan owns startup recovery reconciliation and one supervised
execution thread. Handlers validate/route HTTP only. The service calls existing
WorkflowRunner, WorkflowControls and RecoveryCoordinator methods; those remain
workflow authority. Provider IO runs outside the store lock. Requests and SSE
connections do not own execution. Approval records approval; explicit start
schedules execution. Resume explicitly opens the existing gate and schedules the
saved phase. Shutdown requests a safe pause and waits for owned work to settle
before closing SQLite; abrupt exit uses M4.2 recovery on next startup.

### Endpoints and command admission

- `POST /projects`: name, goal and nonempty structured requirements. Returns the
  created project ID in a typed command acknowledgment.
- `GET /projects`: project list. `GET /projects/{id}` and
  `GET /projects/{id}/snapshot`: authoritative ProjectSnapshot.
- `POST /projects/{id}/plan`: create/initialize a run and schedule planning.
- `POST /projects/{id}/runs/{run}/approve|start|pause|resume|cancel`.
- `POST /projects/{id}/runs/{run}/permission`: exact `approval_id`, `approved`
  boolean and evidence `reason`; invokes the existing permission control.
- `POST /projects/{id}/runs/{run}/recovery`: `operation_id`, existing recovery
  `action`, `reason`, optional `expected_epoch` and `quiescent` attestation.
- `GET /projects/{id}/runs/{run}/tasks|reviews|evidence|usage|permissions|recovery`.
- `GET /projects/{id}/runs/{run}/artifacts/{submission}?path=relative/path`:
  immutable captured UTF-8 bytes and content hash. No arbitrary filesystem,
  sidecar, live-file, or artifact-root access. Existing workspace/custom protected
  policy is checked; unknown artifacts return 404, denied paths 400, corrupt
  evidence 409. Recovery remains inspectable through metadata if evidence fails.
- `GET /projects/{id}/events`: committed event SSE.

All POSTs require `Idempotency-Key` (1..200 printable non-space ASCII characters).
Run/project commands require positive `expected_version`, the **project** version
from the snapshot, including permission and recovery commands. `expected_epoch`
additionally checks the recovery epoch when supplied. Unknown input fields fail
validation. `/openapi.json` and `/docs` expose the typed request/acknowledgment
and snapshot envelope contracts for future clients; no frontend is included.

CommandAcknowledgement has `command_id`, `status` (`pending`, `applied`,
`rejected`), `project_id`, optional `run_id`, `project_version`, `event_cursor`
and safe `error`. Pending means admitted/scheduled or pause requested; it does
not claim eventual completion. Inspect the snapshot/events for eventual state.
Backend workflow/policy rejection returns a rejected acknowledgment; optimistic
conflicts and conflicting key reuse return HTTP 409 with a rejected acknowledgment.
Validation is 422; missing entities are 404; invalid read policy/state is 400.

Admission serializes with store mutations. Keys are scoped to project, or the
application create-project scope. The fingerprint includes target, action and
complete parsed body. Identical retries return the original receipt even if the
original expected version is now stale. Different payloads under the same key
fail. Rejections after admission are journaled too. A durable intent fence commits
before effects, followed by the acknowledgment. A crash between those commits
leaves an **uncertain receipt**: retry returns 409 and never re-executes. Inspect
snapshot/recovery before explicitly issuing a new command/key. This deliberately
prevents duplicate effects without claiming crash-atomic external execution or
automatic job resumption. Journal retention/cleanup is deferred.

### Snapshot and SSE contract

ProjectSnapshot is `{schema_version: 1, project: <authoritative domain state>,
event_cursor: <integer>}`. State and cursor are read under one store lock. The
cursor is the last committed event for that project; SQLite sequences are global
and may have project-local gaps. Snapshot, then connect with `?after=cursor`:
commits between those requests remain in history and replay without a race.

SSE frames are UTF-8 `id: <sequence>`, `event: domain`, and `data: <DomainEvent
JSON>`, followed by a blank line. The domain envelope retains `schema_version`,
`sequence`, `type`, entity references, actor, timestamps and payload. Only stored,
committed events are read; rejected/rolled-back mutations never generate a frame.
Replay uses an exclusive cursor, ascending sequence, bounded 100-event pages.
Events committed during replay are picked up by subsequent pages; there is no
replay-to-live subscription gap. Empty history is polled every 100 ms. Idle
connections receive `: keepalive` comments every 15 seconds. Responses disable
cache and proxy buffering. No WebSocket, Redis or client-owned worker exists.

A supplied `Last-Event-ID` overrides `after`, including when the query cursor is
unavailable. Default cursor 0 replays all project history. Malformed, negative,
future or other-project cursors return 409 before streaming; fetch a fresh
snapshot and reconnect from its cursor. Missing projects return 404. Delivery is
at least once across reconnects: clients must ignore IDs <= their last applied
sequence and never infer state from event counts or contiguous numbering.
Disconnect discards only stream state. Slow readers hold neither a store lock nor
an event queue; execution continues and history supplies catch-up on reconnect.
SQLite event pages and cursor checks use indexed queries. There is no compaction,
retention limit, distributed subscriber infrastructure or exactly-once delivery.

### Local configuration and security

Default launch binds `127.0.0.1`, one process/worker. Hosts are restricted to
localhost/loopback; Origin must match the HTTP host, and cross-site/same-site
browser mutations are rejected. No CORS access, accounts or authentication is
added. Do not expose this trusted local service through a public bind/proxy.
Backend provider credentials/environment are never included in public objects;
credential-named fields and configured environment secret values are redacted
at the snapshot/query/event serialization boundary. Existing persistence and
workspace credential protections remain active. Arbitrary application text is
not a general-purpose secret classifier.

Default runner is explicitly the offline synthetic development fixture. Production
provider/definitions/workspace gateway configuration is supplied through
`create_app(runner_factory=...)` in backend code, never HTTP credential fields.
HTTP adds no provider-native tools or automatic file/command work. Existing M3/M4
execution, filesystem races, trusted-command and recovery limitations remain.
Large snapshots/evidence are currently complete documents; pagination and richer
query schemas are deferred. Provider calls must eventually settle for graceful
shutdown; forced shutdown relies on the durable recovery fences.

## M5.1 browser-operated workflow

Owners: `apps/web/app`, `features/{projects,workspace}`, `lib/{api,events,state}`.
This section records the M5.1 release baseline before M5.2 below. At that release,
no production backend workflow or HTTP contract changed. `app/dev/browser.py` is an explicitly selected disposable
verification fixture, using the existing runner, approvals, commands, file tools,
immutable captures, review rounds and durable store.

### Browser structure and authority

App Router routes `/`, `/projects/new`, and `/projects/{id}` provide project
list/open, creation, and workspace. The workspace renders goal/requirements,
structured Manager plan/tasks/dependencies/criteria, six task statuses with
assignee and persisted review counts, basic Manager/Developer/Reviewer cards,
run controls, committed activity, permission decisions, blocked/recovery state
and final summary/completed task IDs/limitations/evidence references. Final
references link to the existing backend evidence JSON; no artifact/diff UI exists.

Request and response envelope types in `lib/api/openapi.d.ts` are generated from
FastAPI's OpenAPI without starting its lifespan. `npm run contracts` uses Python
with the backend dependencies (`API_PYTHON` can select it). The domain document
remains a dict in OpenAPI, so `lib/api/types.ts` provides read projections matching
existing Python domain serialization. No frontend lifecycle reducer, task readiness
calculation, acceptance gate or permission authorization is introduced.

The small React reducer/context owns the authoritative snapshot, received event
cursor, bounded committed activity, selected task, UI pending commands,
connection/stream errors and command errors. Permissions come from the existing
read API. Agent status is a coarse presentation of backend run status/phase and
pending operation/task, not an independent employee state machine.

Commands include a captured expected **project** version and new UUID idempotency
key. Failed/unknown transport outcomes offer an explicit same-body/same-key retry.
Stale-version rejection refetches state and requires the user to review/retry;
mutations never auto-repeat under a new version/key. Acknowledgments do not overwrite
a newer snapshot or imply task/run completion. Pause requested is UI command state
until the backend snapshot confirms PAUSED; PAUSE_REQUESTED remains distinct.
Approved plans and decided permissions still require the existing explicit Start
command. Resume uses the current recovery epoch when a resolved gate is present.
Cancel/Stop calls cancellation and does not promise rollback of files or billing.

### Snapshot/event controller

The project view first fetches ProjectSnapshot, then opens exactly one streaming
fetch from its exclusive cursor. A small incremental SSE parser accepts domain
frames, validates schema/project/sequence against the frame ID, and ignores
keepalive comments. IDs <= the last received cursor are duplicate-safe; sequence
gaps are allowed. Unique committed events populate the activity feed and trigger
serialized, coalesced snapshot/permission refreshes. Events are not complete state
documents, so task/run state always comes from refreshed snapshots rather than
frontend reconstruction. Stale snapshots cannot roll versions/cursors backward.

The snapshot cursor and received-event cursor have separate roles: an ordinary
refresh may see commits that SSE has not delivered yet and does not advance the
received cursor or discard their future activity. Reconnect sends Last-Event-ID
from the last accepted event (initial connection uses `after`). HTTP 409 or invalid
schema/envelope triggers a visible reset, a new authoritative snapshot and cursor,
then reconnection; explicit reset also supports a restored database with a lower
cursor/version. Teardown aborts the stream and reconnect timer only. Browser
online/offline transitions abort only that connection and show disconnection;
backend execution remains independently supervised.

Activity is limited to the last 250 delivered committed events since the view
opened; an explicit reset clears that window. A full page refresh reloads the
current authoritative snapshot and starts a new activity window. There is no
localStorage-authoritative state or replay animation. No polling timer advances
tasks: reconnect delays are transport-only, and refreshes are event/command/user
triggered.

### Same-origin local transport

`app/api/backend/[...path]/route.ts` forwards allowed existing GET/POST routes to
a server-configured loopback HTTP backend. No mutation/recovery/authorization rule
lives in the proxy. It validates local URL/Host and same-origin Origin/Fetch-Site
before mapping the upstream Origin to FastAPI's local host. It does not trust
forwarded-host headers or forward browser cookies/Authorization/provider credentials.
`AI_OFFICE_API_URL` is server-only; no `NEXT_PUBLIC` credential/configuration field
is introduced. FastAPI's M4.3 Host/Origin policy stays intact.

SSE passes through with no domain-event rewriting or buffering. An initial
`: keepalive` comment flushes idle proxy headers so the browser can report a live
connection before FastAPI's next event/15-second keepalive. Backpressure and request
abort apply to the stream only, not execution. HTTP errors preserve status and safe
backend messages. Backend unavailability, rejected commands, stale versions,
permission denial, blocked runs, recovery gates, disconnects and resets are visible.

### Current API limitations and scope boundary

CreateProject accepts name, goal and nonempty requirements only. Workspace is
backend-configured and displayed read-only. The API does not expose plan mutation,
instruction submission or arbitrary blocker-input commands, so the UI communicates
these limits instead of storing substitutes in the browser. Recovery issues are
visible; unresolved issue resolution uses existing backend tooling until M5.2.
No new backend endpoint or workflow semantic is added to fill these gaps.

M5.1 excludes usage/settings polish, detailed evidence/diff/artifact inspection,
code editing, office visuals/animations, authentication, new agent roles, budgets,
WebSocket/Redis and M6 work. Default startup remains offline synthetic execution;
production provider/workspace setup still belongs to backend configuration. Single
trusted local user/process/writer and all M3/M4 limitations remain applicable.

## M5.2 inspection, usage, settings and recovery

The workspace adds connected Agents, Task history, Tool activity, Usage, Settings,
and Recovery views. Selection is UI state; run/task/attempt/submission/review data
comes from the authoritative snapshot. Existing SSE delivery and reset semantics
remain unchanged. Events trigger fresh queries; accounting is never incremented
from events. Supplementary inspection results are replaced, ignore superseded
requests, and are associated with their run so a previous run cannot supply the
new run's usage/recovery controls. Commands remain visibly sending through their
owned snapshot refresh, avoiding an enabled-button race with the controller's
in-flight command lock.

### Additional HTTP read/configuration contracts

- `GET /projects/{project_id}/settings`: next-run definitions for exactly Manager,
  Developer and Reviewer, project version, editable field names, application
  timing (`next_run`), explanatory note and backend credential **configured boolean**.
- `POST /projects/{project_id}/settings`: `AgentSettings` with `expected_version`,
  `kind`, `name`, `role`, `model`, and `system_instructions`; required
  `Idempotency-Key`; existing typed `CommandAcknowledgement`. Extra fields are
  forbidden. The durable project definition changes atomically with
  `agent.configuration_updated`. Identical keys/bodies return the original receipt;
  conflicting keys/versions reject. No provider or tool executes in this command.
- `GET /projects/{project_id}/runs/{run_id}/inspection`: durable run and whole-project
  usage, the latest 50 committed run events, tool audit records, metadata-only execution operations, recovery inspection,
  next-run settings, retained execution limits, and effective workspace role-policy
  decisions if a configured gateway is bound in this backend session. Missing gateway
  information is unavailable, never interpreted as a grant.

The proxy allowlist includes these routes; loopback/same-origin restrictions,
secret-free forwarded headers and SSE headers remain in force. Request validation
returns a safe 422 message without echoing rejected inputs. Public projections drop
credential/authorization/environment/private-reasoning fields, redact configured
secret values, and redact authorization header text. No provider configuration or
hidden command environment is sent to the browser.

### Configuration timing and supported fields

`ProjectState.agent_definitions` is an optional persisted tuple of the existing
immutable `AgentDefinition` values (empty means existing defaults). Older stored
projects decode with that default; no SQL migration is needed. A settings save
replaces one employee definition and increments its configuration version. Names,
roles, model slugs and instructions are editable. Arbitrary nonempty model slugs,
including `anthropic/...`, `google/...` and `openai/...`, are accepted as manual
configuration. Provider support is still checked when invoking; configuration is
not proof of model/provider availability.

Changes apply **only to runs initialized afterward**, not to an active run's next
step. The run captures all three definitions at initialization. Reconstructing a
historical/recovered runner uses those captured definitions, even if project
settings have since changed. Existing invocations, call receipts and price/config
snapshots are unchanged. Tools, permissions, context policy and execution limits
are backend-owned and read-only; there is no provider-secret editor or model routing.
Unknown save outcomes offer an explicit same-body/same-key retry; stale versions
refresh state and require another reviewed command, without automatic resubmission.

### Evidence and tools

Task history joins attempts to submissions by `attempt_id` and reviews/revision
briefs by exact `submission_id` and `submission_version`. PASS/FAIL are actual
Reviewer verdicts. BLOCKED and technical provider failures have separate labels;
no technical error synthesizes a FAIL review. Criteria, evidence, findings,
requested fixes and `checks_not_performed` remain visible.

File buttons call the existing protected immutable artifact API:
`GET /projects/{project_id}/runs/{run_id}/artifacts/{submission_id}?path=RELATIVE`.
It now includes artifact/submission/task/attempt IDs, version, captured diff,
before/content hashes and text. `created_at` is null because the capture contract
has no timestamp; the UI says Unavailable. Reads still require a captured file in
that exact submission and configured workspace policy. No arbitrary live path,
sidecar path, `.env`, credential file or external/system path is supported. Missing,
protected and integrity failures are explicit; there is no local-file fallback.
Text is escaped React content, not HTML. Diff additions/removals retain `+`/`-`
markers and readable colors. Historical attempts are labeled as historical/stale
relative to newer attempts; actual test evidence retains its backend stale flag.
Redaction can change displayed bytes; hashes identify the original capture.

Command/test receipts come from retained workflow records, not a new shell API.
Tool activity shows audit outcomes, exact permission request/grant/consumption,
scopes, attempt/task links, execution certainty/stage, timestamps, exit codes,
bounded stdout/stderr, truncation, timeout/cancellation and cleanup state. A duration
is shown where no separate end timestamp was retained. Backend-enforced configured
capabilities, per-operation requests and per-operation grants are distinct. Trusted
commands remain outside an OS sandbox; the UI states that limitation. No editor,
IDE, arbitrary filesystem reader or permission-policy override exists.

### Usage and recovery

Accounting adds input/output/cached-input token breakdowns to existing durable
aggregation. Cached input is a subset of input. Current/latest run, per-agent run
usage and all-run project totals show calls, tokens, estimated USD cost, quality
review rounds and technical retries separately. Decimal estimates serialize as
strings. Incomplete usage/cost remains null; UI shows `Unavailable / Incomplete`,
never a false zero. Repeated queries or event replay cannot double totals. Per-task
accounting is unavailable in the current contract and is labeled accordingly.

Recovery inspection now advertises `available_actions` per unresolved issue using
M4.2's existing actions and retained evidence. Each has an action identifier, label
and `requires_quiescent` flag. This is discoverability, not authorization: `resolve`
continues to validate phase/generation/epoch, retained evidence and dangerous effects.
The browser displays interrupted phase/task/operation, certainty, reasons and
receipts. It sends existing `recovery` commands with bounded reasons/current epoch,
and requires explicit quiescence attestation where advertised. Resolution retains
uncertainty/unknown billing, leaves execution paused, and requires a separate
explicit Resume. Unadvertised/unsupported actions stay unavailable. Missing or
corrupt artifact sidecars may still require operator repair outside the browser
before protected reads or reconciliation can succeed.

M5.2 does not add M6 office scenes/animations, an IDE, new workflow semantics,
automatic recovery/routing, auth, cloud deployment or M7 reliability work.

The inspection run selector can read any retained project run. It changes only
inspection queries/task/evidence navigation; primary workflow commands continue
to use the authoritative active/latest run. Recovery actions for a historical
selection are disabled. Earlier configuration, attempts and usage remain inspectable
when a newer run is active or completed. Agent activity is filtered to the selected run.

Recent committed run events in the inspection read are a bounded historical
window, not a second stream or an event-based accounting projection. The browser
replaces this query result and associates events with retained invocation IDs/agents.
The primary activity feed retains M5.1's live-view window and duplicate suppression.


## M6 office presentation and event acknowledgements

Owners: `apps/web/features/office/`, existing `lib/state/` controller/reducer and
workspace/inspection components. No HTTP, domain-event, workflow or durable-state
schema changes. `DomainEvent.event_id` is now represented in the frontend type;
missing identities remain readable in the feed but never create handoff motion.

The broad layered room arranges Manager, Developer and Reviewer left to right.
Transparent character and furniture layers have static fallback poses; motion
never implies activity without backend evidence. Desk controls reuse AgentDetail and TaskHistory;
review labels navigate to the matching task, and document packets focus their
same committed Activity Feed entry. The resource strip consumes `project_usage`
from the existing inspection query, never event-derived counters or prices.
Unknown totals/cost remain Unavailable/Incomplete.

### Read-only status and animation projection

- No run/no pending operation: Idle. Pending Manager phases plan/assign/decide/final:
  Thinking. Pending develop: Developer Working. Pending review: Reviewer Reviewing.
- Approval, paused or canceled runs: Waiting. Pending command approval blocks the
  Developer; other employees wait. User-input blockers identify the active employee;
  recovery gates block the office. Completed: Done. Failed: Error.
- Current task belongs to the authoritative active phase; task links never assign
  or transition a task. Last review is explicitly historical and uses the matching
  retained review, not a synthetic activity or inferred verdict.
- Pause requested preserves a genuinely pending work indicator until the backend
  reaches Paused. Paused/blocked/recovery/failed states suppress work motion.
- Disconnected views retain clearly labeled last-known status, suppress motion,
  and state that browser disconnection does not stop backend execution.

### Handoff and replay contract

`task.assigned`: Manager → Developer; `submission.admitted`: Developer → Reviewer;
`review.completed`: Reviewer → Manager; `revision.requested`: Manager → Developer.
Review PASS/FAIL labels join `payload.review_id` to the authoritative review; until
available the neutral label is Review returned. Completion is projected from the
snapshot, never caused by receipt animation.

Before every SSE connection attempt, the existing controller fetches a fresh
snapshot and records its committed cursor as a visual boundary. It retains the
last delivered cursor for Last-Event-ID/feed replay. Only events above the fresh
boundary can enter a bounded, nonpersistent `liveEvents` UI window. The existing
reducer rejects wrong-project, duplicate identity and non-increasing sequence
entries. Ordinary event delivery still refreshes authoritative snapshots. Snapshot
reset clears both feed/visual windows; reconnect clears visual acknowledgements.
Events committed during the snapshot→stream gap are eligible; older reconnect
backlog updates the feed/state without animating. No second stream or event bus.

Office mounts treat already-present events as historical. A bounded local seen-ID
set prevents rerenders from repeating acknowledgements. Up to four short packets
may appear; a presentation-only expiry removes them after 1.6 seconds. Packets do
not queue workflow, invoke commands, modify tasks or delay execution. Pause,
terminal states, recovery and disconnect clear motion. A just-committed assignment
may be acknowledged even if its following permission request has already blocked
work; the desk is explicitly Blocked and no working animation runs.

### Visual assets, themes and accessibility

The scene is assembled by `features/office/OfficeRoom.tsx`, `DeskSprite.tsx` and
`PixelCharacter.tsx`. Empty day/night structural PNG shells contain walls, windows,
floor and threshold only. A transparent three-column/four-row atlas supplies
independent employee, desk, chair and equipment layers. Plants and documents are
separate reusable sprites. CSS selects complete atlas cells and explicit depth
order; the office is never one flattened illustration. Assets use nearest-neighbor
rendering; generation prompts are recorded in `sprites/M6_PROMPTS.md`.

Desktop/tablet share a broad panorama. Mobile removes the backdrop and stacks the
same stations. Day/Night swaps only room/workspace presentation; employee identity,
positions and projected state remain stable. Functional cards and dashboard text
remain normal HTML/CSS. Art components have no domain state, provider access or
separate event subscription. The existing projection gates hands/documents/cursor
motion and committed-event receipt acknowledgements. State-specific character
frames currently fall back to each employee's still sprite. No engine, Canvas or
WebGL is introduced.

`ai-office-theme` stores only Day/Night in localStorage; unavailable storage falls
back to session state. No Auto mode. Desktop/tablet use one fixed rectangular room;
mobile stacks three readable desk cards and their original sprite components. Semantic buttons, described status text,
keyboard navigation and focus outlines remain. Reduced-motion CSS disables all
ongoing work/travel animation and leaves static receipt/status cues. Artwork is
presentation-only and hidden from assistive technology; desk controls provide the
names, roles, states and task actions.
