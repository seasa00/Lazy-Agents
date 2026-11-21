# Current milestone

**Official status: M1–M6 COMPLETE. M6 is frozen and closed.**

M6 delivered the production Office Experience and observability UI, including
the approved Pixel Office, Agent Inspector, pop-out/fullscreen behavior, and
integration with the existing Lazy Agents system. No new implementation work is
assigned to M6. Earlier visual/reference-pass notes are historical records.

**Active milestone: M7 — Agent Runtime Modernization & Production Hardening.**
**M7.1 and M7.2 are COMPLETE. M7.3 is NOT STARTED.** M6 remains frozen
and closed.

| Planned phase | Goal | Status |
|---|---|---|
| M7.1 — LangChain Agent Layer | Developer file and approved command/test adapters, durable continuation, paired A–F parity and Inspector backend verification | Complete |
| M7.2 — LangGraph Orchestration | Compare legacy and graph orchestrators before switching | Complete; legacy remains default |
| M7.3 — LangGraph Observability Integration | Feed real runtime traces into existing M6 surfaces | Not Started |
| M7.4 — Reliability & Recovery Hardening | Preserve domain guarantees under failures/restarts | Not Started |
| M7.5 — Evaluation & Regression Suite | Produce repeatable comparative evidence and metrics | Not Started |
| M7.6 — Production & Portfolio Finish | Verify setup/deployment and prepare demonstration materials | Not Started |

The [roadmap](IMPLEMENTATION_MILESTONES.md) defines scope and review gates.
LangChain Core 1.8.3 is used for Developer tool abstractions and calls. The
provider-neutral provider remains the model boundary and is the sole accounting
path. LangGraph 1.2.24 is available through an explicit opt-in orchestrator.
Developer file tools pass through the existing
Permission Gateway. Command/test requests now suspend into durable continuations;
recovery reconstructs an approval from its persisted pre-request seed and exact
permission audit if a process stops before the workflow commit. Paired A–F
compatibility and both offline end-to-end workflows passed; see
[the compatibility record](M7_1_COMPATIBILITY.md).
Manager and Reviewer retain their
existing provider-neutral structured-output paths; adding LangChain wrappers is
not required where it adds no functional value. SQLite/domain records own projects,
tasks/runs, immutable submissions, reviews, evidence, events, usage/cost,
permissions, recovery, and idempotency. Optional graph checkpoints hold only
execution/resume state. Preserve exactly three agents, one active run, revision
limits, exact-submission review, and backend-authoritative M6 observability.
Do not expose hidden chain-of-thought; prompt/context traces must redact secrets.

Keep the existing orchestrator and provider/runtime contracts. The M7.2 comparison
passed; see [the compatibility record](M7_2_ORCHESTRATOR_COMPATIBILITY.md). Current LangChain execution is enabled only for providers
that declare tool support; unsupported deterministic providers retain the existing
path. M7.1 has passed its deterministic comparison and bounded end-to-end gates.
Manager/Reviewer schemas remain guarded by existing provider and domain validation.

Verification evidence and the remaining exit gates are recorded in
[verification.md](verification.md).

## Verified M5.2 baseline

**M5.2 — Evidence, Usage, Settings, and Recovery UI COMPLETE.**

The Next.js workspace has connected inspection views for all three employees,
retained runs, task attempts, exact submissions/reviews/revisions, immutable file
text/diffs, command/test receipts, durable usage, future-run configuration and
explicit recovery intervention. The backend remains authoritative; one project
SSE stream invalidates projections, and usage is queried rather than incremented.
Historical inspection selection does not change current-run command targeting.

Backend additions fill HTTP/read/configuration gaps: settings GET/POST with existing
versioned/idempotent acknowledgments; inspection GET; artifact metadata/diff fields;
input/output/cache token accounting; existing recovery-action descriptors; stricter
secret/environment/private-reasoning redaction and non-echoing validation errors.
No workflow transition, permission bypass or automatic recovery is introduced.

Settings support employee name, role, arbitrary manual model slug and system
instructions. Changes apply **only to newly initialized runs**. Current and
completed invocations keep captured definitions; restarted runners reconstruct
those definitions. Tools/permission policy/context policy and execution limits
remain backend-configured/read-only. Credentials show configured status only.

Protected artifact reads are scoped to an immutable captured submission/file.
Missing/protected/integrity failures are explicit. Diff markers and original hashes
are shown; historical evidence/test staleness stays visible. Capture timestamps
are Unavailable where no timestamp was retained. Reviewer PASS/FAIL, BLOCKED and
technical errors are distinct. Trusted local command limits remain unchanged.

Recovery displays phase/task/operation, certainty/reason and retained receipts.
Only backend-advertised actions are offered, with explicit reason/quiescence where
required. Resolution leaves execution paused and preserves uncertainty/unknown
billing. Resume is a separate human action. No automatic resume occurs.

## Verification on 2026-10-05

- **458 backend tests passed** (445 existing + 13 M5.2 tests).
- **85 frontend tests passed** (59 existing + 25 inspection tests + 1 controller regression).
- **5 Chromium E2E scenarios passed** (4 existing + 1 complete M5.2 scenario).
- **5 headed Chromium scenarios passed** against real local FastAPI/SQLite and Next.js.
- OpenAPI generation, TypeScript checks, production build and `git diff --check` passed.
- Evidence, usage, uncertain recovery and narrow agent screenshots were inspected.

The headed workflow inspected Manager/Developer/Reviewer, two FAIL/PASS attempts,
exact submissions, criteria/findings/fixes/unperformed checks, protected file diff,
command stdout and per-agent accounting. It saved a new model slug, verified the old
captured configuration, resolved an interrupted Reviewer fence without inventing
billing certainty, explicitly resumed/completed/refreshed, started another run,
approved its runtime command permission and verified the new model on a successful
Developer receipt. It then selected the prior run and restored the old model in
inspection while current workflow state remained completed. Completed/historical
agent activity came from bounded durable events. JSON responses contained no secret
sentinel, credential names, authorization headers or environment fields. The
preserved browser suite also verified pause-requested/paused/resume, denial/cancel,
refresh during execution and SSE disconnect/reconnect/reset. No direct API mutations
were needed for normal browser actions. No billed live-provider call was made.

## Startup

Install backend dependencies in a virtualenv; frontend dependencies with `npm ci`.
From `apps/api`, with its virtualenv activated:

```bash
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

From `apps/web` in a second terminal:

```bash
npm run dev -- --port 3000
```

Open `http://127.0.0.1:3000`. For reproducible completed evidence and an interrupted
Reviewer gate, replace the backend command with:

```bash
AI_OFFICE_M52_FIXTURE=1 PYTHONPATH=. python -m uvicorn app.dev.browser:app --host 127.0.0.1 --port 8000 --workers 1
```

This uses disposable SQLite/workspaces and deterministic providers. Inspect
Completed evidence fixture, then explicitly resolve/resume Interrupted recovery
fixture before starting another run. Normal startup remains offline synthetic
execution; provider/workspace wiring is backend-owned. Settings alone do not enable
a live provider. No billed live-provider browser check was performed.

## Verification commands

From `apps/api`, virtualenv activated:

```bash
PYTHONPATH=. python -m unittest discover -s tests -q
```

From `apps/web`, with that virtualenv in PATH:

```bash
npm run contracts
npm test
npm run typecheck
npm run test:e2e
npm run verify:browser
npm run build
```

`verify:browser` drives the entire suite in headed Chromium; `verify:m52` drives
only the M5.2 scenario. Tests own ports 8011/3011. Screenshots/traces are under
ignored `apps/web/test-results/`. Do not run dev and build concurrently because
both use Next.js output files. Run `git diff --check` from the repository root.

## Limits

Usage supports retained run/per-agent and whole-project totals; per-task attribution
is unavailable. Unknown usage/pricing is Incomplete, not zero. Current activity
retains the latest 250 delivered project events since opening the view. Workspace
selection, plan edits, instructions/arbitrary blocker inputs and capability/limit
changes remain backend-only. Corrupt/missing sidecars may need operator repair.
No IDE, auth/cloud, routing, new agent kinds or M7 work.
See [contracts.md](contracts.md), [verification.md](verification.md) and README.

## Files introduced or extended for M5.2

- Frontend detail components: `features/agents/AgentDetail.tsx`,
  `features/artifacts/ArtifactViewer.tsx`, `features/usage/UsagePanel.tsx`,
  `features/settings/SettingsPanel.tsx`, and workspace `Inspection.tsx`,
  `TaskHistory.tsx`, `ToolActivity.tsx`, `RecoveryPanel.tsx`.
- Frontend integration/contracts: `features/workspace/Workspace.tsx`,
  `lib/api/{types.ts,client.ts,proxy.ts,openapi.d.ts}`, `lib/state/context.tsx`,
  `app/globals.css`, `package.json`, `playwright.config.ts`.
- Frontend verification: `tests/inspection.test.tsx`,
  `tests/controller.test.tsx`, `e2e/00-inspection.spec.ts`, `e2e/workflow.spec.ts`.
- Backend: `app/main.py`, `app/api/{schemas.py,service.py}`,
  `app/domain/projects.py`, `app/orchestration/recovery.py`,
  `app/usage/aggregation.py`, `app/persistence/{store.py,operations.py,sqlite.py}`,
  `app/dev/{browser.py,inspection.py}`,
  `tests/test_m52.py`.
- Documentation: README, current milestone, contracts, verification and decisions.

Existing uncommitted M4/M5.1 work is preserved; this inventory describes M5.2's
changes, not the entire workspace diff from its older Git baseline.
