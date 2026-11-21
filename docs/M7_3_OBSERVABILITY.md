# M7.3 LangGraph observability

LangGraph remains an opt-in orchestrator; legacy remains the default. `GraphObservabilityAdapter` observes each graph-routed `WorkflowRunner.step`. The runner appends `graph.node_started` with its durable invocation reservation, then appends `graph.node_completed`, `graph.node_interrupted`, or `graph.node_failed` and the matching invocation outcome **after** the existing domain reducer validates and commits its result. These records use the existing `DomainEvent` envelope, project cursor, event ID, sequence, timestamp, correlation/causation IDs, and run/task references. They contain node/phase and identity references only. Graph state does not own domain facts or usage.

The existing domain and gateway events continue to provide submission, review, acceptance, revision, handoff, permission, tool, test, retry, pause/resume, cancellation, and finalization facts. The graph adapter does not emit duplicate success events. Reviewer PASS becomes a committed review; Manager acceptance remains a separate domain commit. Reviewer FAIL becomes a committed review, followed by the existing Manager revision decision. A waiting Developer node interrupts; approval/denial and command execution use the durable M7.1 continuation, and a later graph invocation resumes the workflow. No graph call stack or checkpoint is retained during approval.

| Trace fact | Durable source | Authority |
|---|---|---|
| Node and invocation lifecycle | `graph.node_*`, `graph.invocation_*`, `operation.started` | Runtime observation |
| LLM call and retry | `execution.operation_recorded`, `usage.recorded` | Existing operation and `AgentRuntime` receipts |
| File tool request/result | `tool.audit` intent and result | WorkspaceToolGateway audit |
| Approval wait/decision, command/test result | `developer.waiting_for_approval`, `command.permission_decided`, `command.launch`, `command.completed` | Permission Gateway and command executor |
| Submission, Reviewer PASS/FAIL, revision, acceptance, completion | `submission.admitted`, `review.completed`, `revision.requested`, `task.accepted`, `run.completed` | Domain commits |
| Agent handoff | Committed assignment, submission, review, or revision event | Domain commits |

`project_agent_debug` maps the committed event stream, immutable submissions/reviews, tool audit and operation receipts, agent snapshots, and `AgentRuntime` usage into the existing Agent Inspector tabs. Its trace rows use `event_id` as identity and `sequence` for order. Correlation references include task, attempt, invocation, generation, node, operation, tool request, permission, submission, and review where recorded. Existing file tool audits provide request/result pairs; command audits and permission events provide approval and execution history. The projection reads accounting totals and never records usage. Legacy and historical runs use the same projection; they simply have no `graph.*` rows.

The embedded Pixel Office reads backend inspection for poses and agent snapshots. It refreshes on committed run status/phase/task changes; an open Inspector also refreshes on the workspace SSE cursor. The pop-out subscribes to the same cursor protocol. The existing SSE endpoint replays durable events after the requested cursor, and the Inspector projects each durable event once by event ID. The existing Office handoff animation path keeps its live-only event-ID deduplication. A replay or historical load is not a new handoff.

Prompt and context fields are selected from stored agent instructions, task/project records, model configuration, and record references. The projection never stores or displays hidden reasoning, arbitrary model requests, continuation context, or raw LangGraph objects. Secret patterns and secret environment values are redacted at the backend serialization boundary. Tool rows link to existing operation/evidence receipts; they do not copy evidence blobs.

M7.3 does not introduce node checkpoint ownership or M7.4 failure hardening. A process interruption after an atomic domain commit is recovered from SQLite and the existing explicit recovery flow. Runtime events for an in-flight provider/tool operation are limited to facts already committed before interruption. The Inspector projection is generated from persisted records on request; it is not a second event store.
