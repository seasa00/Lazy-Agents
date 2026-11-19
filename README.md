# AI Office

**Project status:** M1–M6 are complete. M6's production Office Experience,
approved Pixel Office, Agent Inspector, pop-out/fullscreen, and system integration
are frozen and closed. **M7 — Agent Runtime Modernization & Production Hardening
is In Progress; M7.1 is complete.** The [roadmap](docs/IMPLEMENTATION_MILESTONES.md) defines six
phases: LangChain agents (complete), then LangGraph orchestration, runtime
observability, recovery hardening, evaluations, and production/portfolio finish.
The later phases remain planned; startup below uses the existing runtime.

**A local-first workspace for supervised AI software work.** AI Office gives
three roles—Manager, Developer, and Reviewer—a shared project workflow, while
keeping plans, approvals, changes, reviews, and recovery visible to you.

The office view turns real project state into a small pixel-art workspace. You
can follow tasks across planning, implementation, and review, then open the
underlying evidence whenever you need more detail.

## What you can do

- Describe a project and review the Manager's proposed plan before work starts.
- Follow sequential task execution across the Developer and Reviewer.
- Approve requested local commands and inspect their receipts.
- Review submissions, file changes, test evidence, and revision history.
- Pause or cancel a run, inspect interrupted work, and choose when to resume.
- Browse retained usage, project settings, and prior runs from the workspace.
- Switch the office between Day and Night themes.

## Open the project locally

You need Python 3.11 or later, Node.js with npm, and two terminal windows. The
normal setup uses a local SQLite database and does not require an API key.

### 1. Start the backend

In the first terminal, from the repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Keep this terminal running. The API listens on `http://127.0.0.1:8000` and
stores local state in `apps/api/data/state.db` by default.

### 2. Start the web app

In a second terminal, from the repository root:

```bash
cd apps/web
npm ci
npm run dev -- --port 3000
```

Keep this terminal running and open **http://127.0.0.1:3000** in your browser.
The web server forwards requests to the local API at `http://127.0.0.1:8000`.
If you run the API on another loopback port, set `AI_OFFICE_API_URL` to match
when starting the web server. For example, if the API uses port 8100:

```bash
AI_OFFICE_API_URL=http://127.0.0.1:8100 npm run dev -- --port 3000
```

### 3. Try a workflow

Create a project with a goal and acceptance criteria. Request a plan, review and
approve it, then start the run. Select employees, tasks, or review cards in the
office to inspect current activity and retained evidence.

The browser app uses an offline scripted provider by default, so you can explore
the workflow without provider credentials or usage charges. The OpenRouter
adapter is an opt-in CLI path; its credential must be supplied through the
backend process environment. A model name saved in the web settings does not by
itself enable a live provider.

## How the system is organized

The FastAPI backend owns workflow transitions, permissions, persistence, and
recovery. The Next.js app presents backend snapshots and committed events; the
browser cannot grant permissions or mark tasks complete on its own. SQLite
retains project history and evidence, while one Server-Sent Events stream keeps
the workspace current.

The office is the visual layer over that workflow. Its characters, task cards,
handoffs, and status cues reflect project state; they do not control execution.

## Project map

| Path | Contents |
|---|---|
| `apps/api` | Python workflow engine, local API, SQLite persistence, and recovery |
| `apps/web` | Next.js workspace, office view, inspection, settings, and usage |
| `office-pixel` | Pixel-office reference app and reusable visual prototype |
| `docs/` | Current milestone, contracts, decisions, and verification records |
| `AI_OFFICE_BLUEPRINT.md` | Product concept and architecture rationale |

## Scope and safety

AI Office is designed for one local user and one active run at a time. Keep both
servers bound to loopback; the application does not include user authentication
or public hosting. Approved commands run as trusted local code, not inside an
operating-system sandbox. Review the command scope before approving it.

For the implementation status and verified behavior, see
[the current milestone](docs/CURRENT_MILESTONE.md) and
[the verification record](docs/verification.md). The detailed API and UI
invariants are indexed in [the contracts](docs/contracts.md).
