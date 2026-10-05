# AI Office contracts

Current contract owner: M3.2 approved commands and version-bound test evidence, preserving M1/M2/M3.1 contracts.

The implementation uses standard-library frozen dataclasses with strict
`from_dict` parsers. Missing and unknown fields are rejected. `to_dict()` is
the JSON-compatible representation used by the provider boundary and CLI.

## Agent definitions

Owner: `apps/api/app/domain/agents.py`

- `AgentKind` has exactly `MANAGER`, `DEVELOPER`, and `REVIEWER`.
- `DEVELOPER` is the canonical name for the blueprint's initial Worker
  workflow position. The configurable `role` remains separate.
- Default agent definitions have no tools or permissions. The runtime still
  rejects non-empty provider tool configuration. File/command tools use a trusted
  application-owned runner entrypoint; provider-native dispatch is not enabled.
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
- Tool calls remain rejected before execution.
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
- The adapter has no tool definitions in M1.2. Any returned tool call is
  normalized and rejected by the shared runtime.

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
