# AI Office

AI Office is a local three-agent workspace: Manager, Developer, and Reviewer.

## Current status

**M1–M6 are complete.** M6 uses a composed pixel-game room: reusable tiles,
hand-authored character/prop sprites, three structured desk zones, persistent
Day/Night palettes and committed-event handoffs. Existing workflow, evidence,
usage, settings and recovery remain available. **Do not start M7.**

See [verification](docs/verification.md) and retained headed captures:
[Day](docs/screenshots/m6/day-office.png), [Night](docs/screenshots/m6/night-office.png),
[narrow](docs/screenshots/m6/narrow-office.png) and
[mobile](docs/screenshots/m6/mobile-office.png).

Restart inspection never starts new provider/file/command work. Unresolved effects
block resume; unknown provider billing remains unknown. Recovery targets one local
user and one application writer, with no exactly-once or automatic-resume guarantee.

Run all five disposable interruption/restart scenarios from `apps/api`:

```bash
PYTHONPATH=. python3 -m app.dev.recovery demo
```

Inspect and explicitly control a persisted run:

```bash
PYTHONPATH=. python3 -m app.dev.recovery list /path/to/state.db
PYTHONPATH=. python3 -m app.dev.recovery inspect /path/to/state.db --project PROJECT --run RUN
PYTHONPATH=. python3 -m app.dev.recovery resolve /path/to/state.db --project PROJECT --run RUN --operation OPERATION --action verify-file --reason 'Verified retained file hashes' --epoch EPOCH
PYTHONPATH=. python3 -m app.dev.recovery resume /path/to/state.db --project PROJECT --run RUN --epoch EPOCH
```

Resume only clears the gate and restores the valid phase. It does not itself run
a provider or command. Use `python3 -m app.dev.recovery resolve --help` for supported
proof/attestation actions. Saved-model-result admission and `--execute-fixture` in
this CLI are restricted to its disposable fixtures; application callers supply
their bound configured runner. The demo uses controlled providers and harmless
fixtures exclusively. It never attaches to or kills processes using saved PIDs.

Backend startup calls `RecoveryCoordinator(store).startup()` before execution;
`WorkflowRunner` also ensures inspection for its reopened run. Opening a store to
read history does not mutate workflows. Reconstruct workspace runs with their
workspace gateway; permissions are scope-checked and consumed approvals stay spent.

From `apps/api`, verify persistence using a new disposable directory:

```bash
PYTHONPATH=. python3 -m app.dev.persistence create /tmp/m41-new-disposable-project
PYTHONPATH=. python3 -m app.dev.persistence inspect /tmp/m41-new-disposable-project
```

These are separate processes. The fixture uses a controlled provider and explicitly
approves its built-in harmless test command. Inspection compares all committed
history and usage without resuming execution. No API key is needed. SQLite uses
Python's standard library; no additional dependency or service is required.

For application wiring, pass `SQLiteStateStore(database_path)` instead of
`InMemoryStateStore()` to `WorkflowRunner`. Close the store on shutdown. Keep the
database and `<database>.artifacts` sidecar directory outside the workspace and
back them up together. Existing demos still default to the memory adapter.

Run the disposable real-file and command demonstrations from `apps/api`:

```bash
PYTHONPATH=. python3 -m app.dev.workspace
PYTHONPATH=. python3 -m app.dev.commands
```

The command demo explicitly approves its built-in harmless test/slow fixtures,
denies another command, verifies cancellation and marks evidence stale after a
later edit. Every project it changes is an automatically removed temporary folder.
It does not approve arbitrary commands in user projects.

File and command tools use trusted runner entrypoints; provider-native tool calls
remain disabled. Reviewer and Manager have no command execution permission.
**Approved commands are trusted local code, not an OS sandbox.** Scoped cwd and
a restricted environment do not prevent approved code from accessing other paths,
networking, or creating detached descendants. No package installation, deletion
tool, HTTP API or frontend was added.

The previous synthetic workflows remain available below.

## Run the offline harness

From `apps/api`:

```bash
PYTHONPATH=. python3 -m app.dev.cli manager
PYTHONPATH=. python3 -m app.dev.cli developer
PYTHONPATH=. python3 -m app.dev.cli reviewer
```

To demonstrate output validation:

```bash
PYTHONPATH=. python3 -m app.dev.cli manager --invalid
```

The harness uses the development-only `deterministic-mock` provider by
default. It makes no network requests or local project changes.

## Demonstrate M2.1 planning and state

From `apps/api`:

```bash
PYTHONPATH=. python3 -m app.dev.cli state-demo
```

This validates and approves a structured Manager plan, displays dependencies,
shows the first ready task, rejects a cyclic plan, and rejects a second active
run. It does not execute agent work or mutate project files.

## Run the explicit live provider

M2.2 workflow demonstrations (from `apps/api`):

```bash
PYTHONPATH=. python3 -m app.dev.workflow all
PYTHONPATH=. python3 -m app.dev.workflow live --model openai/gpt-4o-mini
```

`all` runs A: PASS, B: revision/PASS, C: review-limit block, D: pause/resume,
and E: cancel/late-result rejection. Individual letters also work. The `live`
command generates a one-task plan and explicitly approves that disposable
controlled fixture before executing it. It needs `OPENROUTER_API_KEY` in the
launched process environment and may incur charges. It reports call metadata,
usage and Decimal cost without printing the credential. Live caps are one task,
16 invocations, 24 calls, 24 iterations and three review rounds.

Copy `.env.example` to a secure environment location and set
`OPENROUTER_API_KEY` without committing it. Then run one bounded role invocation:

```bash
PYTHONPATH=. python3 -m app.dev.cli manager --provider openrouter --model openai/gpt-4o-mini --max-attempts 3 --max-repairs 1
```

Repeat for `developer` and `reviewer`. The CLI prints validated output,
per-attempt usage provenance, and estimated cost. Live calls may incur provider
charges.

## Run tests

From `apps/api`:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

See [docs/CURRENT_MILESTONE.md](docs/CURRENT_MILESTONE.md) for the current
handoff, [docs/verification.md](docs/verification.md) for actual results, and
[docs/IMPLEMENTATION_MILESTONES.md](docs/IMPLEMENTATION_MILESTONES.md) for the
gated roadmap.

## M4.3 local HTTP and SSE

From `apps/api`, in a Python virtual environment:

```bash
python3 -m pip install -e '.[test]'
PYTHONPATH=. python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000/docs` for typed requests. Default execution uses the
explicitly offline synthetic workflow provider. SQLite defaults to `data/state.db`;
set backend-only `AI_OFFICE_DB` to choose another path. Configure real providers,
agent definitions and trusted workspace gateways through `create_app`'s backend
runner factory; credentials are never HTTP inputs or public configuration.

Create a project with name, goal and structured requirements:

```json
{"name":"Greeting","goal":"Describe a synthetic greeting","requirements":[{"id":"r1","description":"Greeting","acceptance_criteria":["Synthetic output is documented"],"priority":"normal"}]}
```

All POSTs require `Idempotency-Key`. Commands require `expected_version` from
`GET /projects/{id}/snapshot`. Plan via `POST /projects/{id}/plan`; use the
acknowledged run ID for `POST /projects/{id}/runs/{run}/approve`, then `/start`.
`/pause`, `/resume`, `/cancel`, `/permission` and `/recovery` use existing backend
controls. Read tasks, reviews, evidence, usage, permissions and recovery under
that run URL. Approval and start are separate; pending acknowledgments are not
completion evidence.

Load the authoritative snapshot, then stream `GET /projects/{id}/events?after=`
with its `event_cursor`. SSE emits `event: domain`, sequence IDs and committed
DomainEvent JSON. Reconnect with `Last-Event-ID`; ignore previously applied IDs.
Idle keepalive comments arrive every 15 seconds. Invalid cursors return 409 and
require a fresh snapshot. Disconnecting the browser or stream never stops work.

Run the disposable real HTTP/SSE verification:

```bash
PYTHONPATH=. python3 -m app.dev.http
PYTHONPATH=. python3 -m unittest discover -s tests -q
```

One local user/process/writer only; keep the loopback bind. No auth, frontend,
WebSocket or Redis. Preserve SQLite and its artifact sidecars together. Restart
inspection never auto-resumes work. An interrupted command-journal receipt fails
closed: inspect snapshot/recovery before explicitly sending a new key. Full
endpoint and SSE contracts are in [docs/contracts.md](docs/contracts.md).

## M5.1 browser workflow

The Next.js App Router frontend lives in `apps/web`. It uses FastAPI snapshots,
HTTP commands, and one committed-event SSE stream per project view. No browser
state can grant a permission or complete a task. M5.2 adds the inspection views below.

First-time backend setup, from the repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

Start the normal backend in that terminal:

```bash
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Start the frontend in a second terminal, from the repository root:

```bash
cd apps/web
npm ci
npm run dev -- --port 3000
```

Open **http://127.0.0.1:3000**. Create a project with its name, goal and acceptance
criteria. Request Manager planning, review the plan, approve it, then Start.
Pause, Resume, Cancel/Stop and permission decisions use the existing API. After
a permission decision, use Start / Continue execution. Refresh restores the
saved project state; disconnecting the browser leaves backend execution running.

The Next.js server forwards same-origin requests to loopback FastAPI. Its
server-only `AI_OFFICE_API_URL` defaults to `http://127.0.0.1:8000`; copy
`apps/web/.env.example` to `apps/web/.env.local` only if changing that URL.
Keep provider credentials exclusively in the backend environment. The proxy
checks local Host/Origin, preserves command keys and SSE replay headers, and
adds an initial SSE keepalive comment to flush an idle connection promptly.

For the complete permission/revision/pause demonstration, **replace** the normal
backend startup command with this explicit offline fixture:

```bash
PYTHONPATH=. python -m uvicorn app.dev.browser:app --host 127.0.0.1 --port 8000 --workers 1
```

The fixture creates a disposable SQLite database and greeting workspace. It
requests approval for a harmless Python print command, deliberately returns a
first FAIL review, records a genuine per-attempt file revision, then returns PASS.
Developer calls take four seconds, allowing Pause requested to be observed before
Paused. It performs no live provider calls. The default backend remains the M4.3
synthetic fixture; its fast run does not generate a command permission request.

Frontend verification, from `apps/web` with the backend virtualenv activated:

```bash
npm run contracts
npm run typecheck
npm test
npx playwright install chromium
npm run test:e2e
npm run verify:browser
npm run build
```

`test:e2e` starts isolated loopback servers on ports 8011/3011 and drives Chromium;
`verify:browser` opens headed Chromium for the full workflow and records screenshots
under `test-results/`. These commands need `python3` with the API dependencies in
PATH. `API_PYTHON=/absolute/path/to/python` can select the interpreter for contract
generation. Production frontend: `npm run build` then `npm start -- --port 3000`.

Current limits: workspace selection, plan editing, instructions and arbitrary
blocker input remain unavailable through HTTP. Activity retains the latest 250
committed events since opening the view; refresh starts a fresh activity window.
At the M5.1 release, no office scene/animation or IDE was included; the M6 layer is described below.

## M5.2 evidence, usage, settings and recovery

In a project workspace, use **Inspect project** views. The run selector exposes
retained historical runs without changing current-run command targeting:

- **Agents**: captured name/kind/role/model, current status/task, structured handoffs,
  recent invocations/call receipts, durable usage and configured/effective permissions.
- **Task history**: select a board card or a task; inspect attempts, exact submission
  versions, PASS/FAIL review criteria/findings/fixes and checks not performed.
  Technical failures and blockers have separate labels.
- **Tool activity**: request/grant/consumption audit, scope, execution certainty,
  timestamps, bounded command/test stdout/stderr, exit/timeout/cancellation/cleanup.
  A selected task filters these records. Trusted local commands are not OS-sandboxed.
- **Usage**: current run and per-agent calls/input/output/cache/total tokens, estimated
  cost, technical retries and review rounds; expandable all-run project totals.
  Unknown totals display **Unavailable / Incomplete**. Per-task usage is unavailable.
- **Settings**: employee name, role, arbitrary manual provider model slug and system
  instructions. Saves apply **only to future runs**, not the next step of an active
  run; immutable historical invocations retain their configuration. Tools, permissions
  and limits are read-only backend configuration. Credentials show configured/not
  configured only. Saving a slug does not select a different provider adapter.
- **Recovery**: inspect interrupted phase/task/operation/certainty and retained
  evidence; select an advertised backend resolution, enter a reason and explicitly
  attest quiescence if required. After resolution, choose **Resume when safe**.
  Resolution never automatically resumes or proves unknown side effects did not occur.

File buttons read only captured immutable artifacts through FastAPI's protected
submission API. Diffs show added/removed lines, task/attempt/submission association
and original hashes. Content is escaped and backend-redacted; older attempts are
historical evidence. Creation time is Unavailable when the backend did not retain
one. Missing/protected/corrupt artifacts have explicit errors and no filesystem
fallback. No `.env`, credential files, arbitrary system path or code editing is exposed.

For reproducible evidence and recovery inspection, replace the backend command:

```bash
AI_OFFICE_M52_FIXTURE=1 PYTHONPATH=. python -m uvicorn app.dev.browser:app --host 127.0.0.1 --port 8000 --workers 1
```

It seeds **Completed evidence fixture** and **Interrupted recovery fixture** in a
disposable database/workspace. Inspect the completed project, then explicitly
resolve/resume the interrupted project before starting another run (one active run
across the application). This exercises actual durable backend fences and captured
files with deterministic providers; it makes no live provider calls. Normal startup
remains `app.main:app`. Provider/workspace setup stays backend-owned; future model
settings alone do not enable a live provider.

`npm run verify:browser` runs all browser scenarios headed; `npm run verify:m52`
runs just M5.2 inspection headed. Browser screenshots are in ignored `test-results/`.
Missing sidecar artifacts may require operator repair before reads/resolution work.
No live-provider browser run, automatic routing, new permission capabilities,
auth/cloud deployment or M7 work is included.


## M6 pixel-art office

The Office is the visual entry point to the existing project workspace. Click an
employee to inspect that agent, a task plate to inspect attempts/evidence, a review
plate to inspect findings, or the resource strip for durable Usage. Navigation and
run controls stay ordinary HTML controls. Day/Night selection persists on this
browser; neither lighting nor animation changes workflow behavior.

The supplied Lazy Agents reference drives a broad cozy room, left-side navigation,
light compact dashboard panels, and Manager/Developer/Reviewer desks arranged
left to right. Empty day/night room shells, transparent character/desk/chair/
equipment atlas layers, plants and handoff documents compose independently.
Characters face their role monitors; attached HTML cards display real projected
status and tasks. Mobile stacks the same stations without the room backdrop.
Artwork and generation prompts are documented in the sprite specification.

Hand/document/cursor motion only follows authoritative active state. New committed
handoffs enable document travel and a brief receiving-character nod; historical or
duplicate events never replay that acknowledgement. Reduced motion keeps static
labels/highlights. See `docs/contracts.md` and the authored sprite specification in
`apps/web/features/office/sprites/README.md`.

Startup remains unchanged (activate the backend virtualenv first):

```bash
# Terminal 1, from repository root
cd apps/api
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

# Terminal 2, from repository root
cd apps/web
npm ci
AI_OFFICE_API_URL=http://127.0.0.1:8000 npm run dev -- --port 3000
```

Open `http://127.0.0.1:3000`. For the explicit disposable browser fixture, replace
`app.main:app` with `app.dev.browser:app`. `AI_OFFICE_M6_VISUAL=1` holds non-Developer
fixture calls for two seconds only when their context contains `M6 visual verification`,
so headed captures can observe real pending operations. Default fixture timing and
production behavior are unaffected. No live-provider billing is exercised.
