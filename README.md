# AI Office

AI Office is a local three-agent workspace: Manager, Developer, and Reviewer.

## Current status

M3.2 is implemented: Developer commands require exact, single-use human approval;
execution has timeout/output limits and pause/cancel cleanup. Reviewer receives
immutable file and test evidence with stale-version detection. **180 tests pass**
and the disposable command demonstration passes. M4.1 has not started.

The roadmap's additional live-provider smoke remains unverified because the
current process has no OpenRouter credential. See the milestone handoff.

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
tool, SQLite, HTTP API or frontend was added.

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
