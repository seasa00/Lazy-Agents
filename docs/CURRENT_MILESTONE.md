# Current milestone

## Status

Completed milestone: **M3 — Tools & Permissions**, including **M3.2 — Approved
commands, test evidence, and tool limits**. M1, M2 and M3.1 are also complete.
**M4.1 has not started.**

Final full automated suite (2026-10-05): **187 tests passed**. The real-process
disposable demonstration passed all seven requested steps.

Required live OpenRouter verification passed on 2026-10-05: workflow completed,
no blocked reason, six successful first-attempt calls using
`openai/gpt-4o-mini`, no retries or repairs, one review round, 2,618 input and
601 output tokens (3,219 total), estimated cost USD 0.00075330. Finalization
validation passed; the previous failure did not recur. The detailed record is in
[verification.md](verification.md).

## Implemented

- Frozen structured `CommandRequest`: executable plus argument tuple, explicit
  profile, workspace-relative cwd, restricted environment, timeout/output bounds,
  trusted actor, attempt/generation and workspace version. No shell-string API.
- Configured exact command profiles, including `is_test` profiles. Developer
  requests create pending permission interventions; trusted human controls
  explicitly approve or deny them. Reviewer and Manager commands are denied.
- Single-use approvals bind the entire request, canonical workspace root,
  executable hash, effective environment and configured profile. Stale/mismatched,
  denied, missing, consumed or invalidated approvals cannot launch.
- One command at a time. Pending permissions prevent workflow advancement;
  running commands own the existing pending-operation slot. File mutations and
  submission capture are denied while a command is running.
- Scoped cwd validation and restricted child environment; no inherited API keys,
  startup/loader hooks, Python path, proxy configuration or HOME. `shell=False`,
  stdin closed, file descriptors closed, new POSIX process session/group.
- Concurrent bounded stdout/stderr draining, monotonic timeout, exit-code capture,
  timestamps, duration, truncation flags and immutable log references/results.
- Pause/cancel checks immediately before launch and during execution. Timeout,
  pause, cancel and scope invalidation kill the original process group and reap
  the direct child. Unfinished descendants after leader exit prevent success.
  Incomplete cleanup keeps the operation reserved and blocks further work.
- Bounded workspace fingerprint covers every regular file (protected files only
  as hashes), directories and change metadata. Symlinks/hardlinks/special files
  fail closed. Before/after/current versions identify stale test evidence.
- Frozen test evidence is attached to the exact captured submission and Reviewer
  context. Latest stale/failed/terminated tests cannot be overridden by PASS.
  Retesting the same profile on current content supersedes its older result.
- Request, decision, launch and result audit records/events; command results are
  retained on the run across pause, cancellation and scope changes.

## Contracts and files

- `domain/commands.py`: limits, profiles, requests, permission interventions,
  audit records, command results, test evidence and approval scope digest.
- `tools/commands.py`: fingerprinting, restricted environment, bounded POSIX
  process launch/drain/timeout/cleanup implementation.
- `tools/gateway.py`, `permissions/policy.py`: existing role gateway plus exact
  approval, command lifetime, audit and evidence ownership.
- `orchestration/runner.py`, `controls.py`: trusted command entrypoints, human
  permission decisions, pending operations, pause/cancel/scope handling.
- `domain/artifacts.py`, `workflow.py`: frozen submission tests and run-owned
  command history; real-file snapshots serialize to JSON.
- `dev/commands.py`: harmless disposable command demonstration.
- `tests/test_m32.py`: 48 command/evidence/limit/workflow tests.

Paths above are under `apps/api/app`, except tests under `apps/api/tests`.

## Verification

From `apps/api`:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -q
PYTHONPATH=. python3 -m app.dev.commands
```

Observed: **180 tests passed**. Demo: workflow **completed**, test command
**succeeded**, exit **0**, stdout `1 test passed`. Reviewer received captured
files and tests. Explicit denial caused no execution. Slow command was
**canceled**, its process was reaped. A later edit made live test evidence stale
while the historical submission and its reviewed test evidence stayed unchanged.

Final suite rerun on 2026-10-05: **187 tests passed**. Required live OpenRouter
verification also passed; see [verification.md](verification.md) for usage and
cost details.

The demo explicitly approves only its built-in harmless commands in disposable
workspaces; it does not approve arbitrary user project commands.

## Limits and limitations

- Default per-request timeout: 10 s; hard configured maximum: 30 s. Default
  retained output: 8 KiB per stream, maximum 64 KiB per stream. Excess is drained
  and discarded with truncation flags. Cleanup adds at most bounded waits beyond
  the execution timeout; OS spawn and filesystem IO themselves are synchronous.
- 20 command launches/results per run (also enforced per gateway lifetime),
  60 permission requests per gateway lifetime; pause/resume never reset them.
  Launch errors consume their approval and launch budget. Gateway replacement is
  trusted configuration, not an agent capability.
- Fingerprints: 2 MiB total file content, 2,000 entries, depth limit 64; executable
  hash bound 128 MiB. Existing M3.1 file/result and role-context bounds still apply.
- **Approved commands are trusted local code execution, not OS sandboxing.**
  They inherit the service user's filesystem/network privileges and can access
  outside paths, alter protected files, spawn shells or escape the process group.
  Cwd/environment restrictions are launch controls, not containment.
- POSIX process groups and descriptor APIs, verified on macOS. Descendants that
  detach from the original group are not guaranteed to be killed. No Windows
  implementation, resource/cgroup sandbox, network isolation or process-tree
  containment guarantee is provided.
- Fingerprints are sequential, not atomic against external writers. Interpreter
  libraries and other dependencies outside the workspace are not snapshotted.
  A privileged writer or concurrent process can race checks or defeat metadata
  assumptions. Command-created workspace files make read-only test evidence stale.
- All approvals, logs, evidence and state remain in memory; no restart recovery,
  crash-atomic filesystem/state transaction, SQLite or M4.1 work.
- Provider-native tool dispatch remains disabled; trusted runner entrypoints own
  actor identity and permissions. No package-installation/deployment tools,
  deletion tool, FastAPI or frontend were added.

See [contracts.md](contracts.md) and [verification.md](verification.md).
