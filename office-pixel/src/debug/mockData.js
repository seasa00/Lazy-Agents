// MOCK data source (development only). Replace by an adapter that returns real AgentDebugSnapshots.
// All names, files, prompts, numbers and "secrets" below are fabricated for the prototype.

const T = (id, at, type, text, extra = {}) => ({ id, at, type, text, severity: 'ok', ...extra })

const REQUIREMENTS = `Feature: token-based authentication for the Acme API.
- POST /auth/login returns an access token (15 min) and refresh token (7 d)
- Protected routes must reject expired / malformed tokens with 401
- Unit tests required for every new branch (pytest)
- Do not change the public response schema of /users`

function manager() {
  return {
    agentId: 'manager', name: 'Manager', role: 'Planner / coordinator', status: 'thinking', mode: 'live',
    currentTask: 'Plan authentication feature (API + tests)', currentAction: 'Planning — breaking the task into subtasks',
    model: 'gpt-4.1-mini', startedAt: '14:01:38', attempt: 'Plan v1', lastEvent: '14:02:47 Revision feedback routed → Developer',
    lastCallLatencyMs: 5200,
    prompt: {
      instructions: `You are the Manager of a 3-agent software team (Manager, Developer, Reviewer).\nYour job: turn the user's request into a small, testable plan, assign it to the Developer, and route Reviewer feedback back.\nRules: keep subtasks independently verifiable; state acceptance criteria; never write code yourself.`,
      taskPrompt: 'Plan the implementation of token-based authentication for the Acme API. Produce subtasks with acceptance criteria and assign them.',
      requirements: REQUIREMENTS,
      context: [
        { label: 'requirements.md', tokens: 1210, source: 'repo' },
        { label: 'Repository file tree (src/, tests/)', tokens: 640, source: 'tool:git ls-files' },
        { label: 'Previous run summary (none)', tokens: 0, source: 'memory' },
      ],
      structuredInputs: { runId: 'run-0182', project: 'acme-api', branch: 'feat/auth', env: { OPENAI_API_KEY: 'sk-proj-FAKEFAKEFAKE1234567890', DATABASE_URL: 'postgres://svc_app:hunter2-fake@db.internal:5432/acme' }, limits: { maxSubtasks: 4 } },
      modelConfig: { model: 'gpt-4.1-mini', temperature: 0.2, maxTokens: 1500, tools: ['read_file', 'list_files', 'write_plan'] },
    },
    decisions: [
      { id: 'm-d1', at: '14:01:46', decision: 'Split authentication work into API implementation and tests.', rationale: 'Requirements explicitly require tests; two independently verifiable units reduce review scope.', outcome: 'accepted', refs: ['requirements.md'] },
      { id: 'm-d2', at: '14:01:47', decision: 'Assign both subtasks to a single Developer agent.', rationale: 'Files overlap (src/auth.ts, tests/test_auth.py); parallel work would cause merge conflicts.', outcome: 'accepted' },
      { id: 'm-d3', at: '14:02:47', decision: 'Route FAIL feedback to Developer without re-planning.', rationale: 'Reviewer feedback is a localized defect (token expiry validation); plan structure is still valid.', outcome: 'accepted', refs: ['review-round-3'] },
    ],
    trace: [
      T('m1', '14:01:38', 'task', 'Run started — user request received'),
      T('m2', '14:01:39', 'tool', 'Read requirements.md', { durationMs: 90 }),
      T('m3', '14:01:40', 'tool', 'Listed repository files', { durationMs: 310 }),
      T('m4', '14:01:41', 'llm', 'LLM invocation started', { detail: 'model: gpt-4.1-mini · context: 1,850 tokens' }),
      T('m5', '14:01:46', 'llm', 'Plan created — 2 subtasks', { durationMs: 5200, detail: 'subtask 1: implement auth API\nsubtask 2: unit tests for auth branches' }),
      T('m6', '14:01:47', 'decision', 'Decision recorded: split into API + tests'),
      T('m7', '14:01:48', 'handoff', 'Assigned subtasks → Developer', { detail: 'assignment message: 1.1k tokens' }),
      T('m8', '14:02:47', 'handoff', 'Revision feedback routed → Developer', { severity: 'warn', detail: 'source: Reviewer FAIL (round 3)' }),
    ],
    tools: [
      { id: 'mt1', tool: 'READ', input: 'requirements.md', at: '14:01:39', durationMs: 90, result: '1,210 tokens', ok: true, output: REQUIREMENTS },
      { id: 'mt2', tool: 'COMMAND', input: 'git ls-files src tests', at: '14:01:40', durationMs: 310, result: '37 files', ok: true, output: 'src/auth.ts\nsrc/users.ts\nsrc/validation.ts\ntests/test_auth.py\ntests/test_users.py\n… (32 more)' },
      { id: 'mt3', tool: 'WRITE', input: '.lazy/plan.md', at: '14:01:46', durationMs: 40, result: 'plan saved (2 subtasks)', ok: true },
    ],
    outputs: [
      { id: 'mo1', kind: 'plan', title: 'Plan v1', body: 'Implement token authentication in two verifiable units.', items: ['1. Implement /auth/login + token validation middleware (src/auth.ts, src/validation.ts)', '2. Unit tests for success, malformed and expired tokens (tests/test_auth.py)'] },
      { id: 'mo2', kind: 'assignment', title: 'Assignment → Developer', body: 'Implement subtasks 1–2. Acceptance: all auth tests pass; expired and malformed tokens return 401; /users schema unchanged.' },
      { id: 'mo3', kind: 'revision', title: 'Revision instructions (round 3)', body: 'Reviewer: FAIL — add validation for expired tokens in the refresh path and cover it with a test.' },
    ],
    evidence: [
      { id: 'me1', kind: 'file', title: 'requirements.md', detail: '1,210 tokens loaded', ref: 'repo://requirements.md' },
      { id: 'me2', kind: 'artifact', title: 'Plan v1', detail: '2 subtasks · acceptance criteria included', ref: 'artifact://run-0182/plan.md' },
      { id: 'me3', kind: 'log', title: 'Assignment message', detail: 'sent 14:01:48 → Developer', ref: 'log://run-0182/handoffs/1' },
    ],
    usage: { inputTokens: 3380, outputTokens: 720, totalTokens: 4100, estimatedCost: 0.011, llmCalls: 2, retries: 0, totalLatencyMs: 6700, latency: { llmMs: 6100, toolsMs: 600, testsMs: 0 } },
    runContext: { runTotalTokens: 9760, reviewRounds: 3, contextTransferTokens: 1100 },
  }
}

function developer() {
  return {
    agentId: 'developer', name: 'Developer', role: 'Implementation', status: 'working', mode: 'live',
    currentTask: 'Implement authentication API', currentAction: 'Editing src/auth.ts',
    model: 'gpt-4.1', startedAt: '14:02:01', attempt: 'Attempt 3 · revision 2', lastEvent: '14:02:31 Handoff → Reviewer', lastCallLatencyMs: 4800,
    prompt: {
      instructions: `You are the Developer agent. Implement the assigned subtasks in the repository using the provided tools.\nRules: read before you write; run the test suite after every edit; keep changes minimal; submit a summary with files changed.`,
      taskPrompt: 'Implement subtasks 1–2 from Plan v1: token authentication (login, validation middleware) and unit tests.',
      requirements: REQUIREMENTS,
      context: [
        { label: 'Assignment from Manager', tokens: 1100, source: 'handoff' },
        { label: 'src/auth.ts', tokens: 1480, source: 'tool:read' },
        { label: 'tests/test_auth.py', tokens: 1210, source: 'tool:read' },
        { label: 'Reviewer feedback (rounds 1–2)', tokens: 420, source: 'handoff' },
      ],
      structuredInputs: { runId: 'run-0182', branch: 'feat/auth', testCommand: 'pytest tests/auth/', headers: { Authorization: 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.FAKESIGNATURE12345' }, repoToken: 'ghp_FAKEFAKEFAKEFAKEFAKE12345678' },
      modelConfig: { model: 'gpt-4.1', temperature: 0.1, maxTokens: 4000, tools: ['read_file', 'write_file', 'run_command'] },
    },
    decisions: [
      { id: 'd-d1', at: '14:02:08', decision: 'Validate token expiry inside the middleware, not in the route handlers.', rationale: 'One enforcement point avoids route-by-route gaps.', outcome: 'accepted', refs: ['src/auth.ts'] },
      { id: 'd-d2', at: '14:02:18', decision: 'Retry the test run after updating validation.', rationale: 'pytest reported 2 failures in the expired-token cases.', outcome: 'accepted', refs: ['pytest #1'] },
      { id: 'd-d3', at: '14:02:30', decision: 'Submit v3 for review once all 19 tests pass.', rationale: 'Acceptance criteria from the assignment are met.', outcome: 'accepted' },
    ],
    trace: [
      T('d1', '14:02:01', 'task', 'Task received from Manager'),
      T('d2', '14:02:02', 'llm', 'LLM invocation started', { detail: 'model: gpt-4.1 · context: 4,210 tokens' }),
      T('d3', '14:02:05', 'tool', 'Read src/auth.ts', { durationMs: 120 }),
      T('d4', '14:02:07', 'tool', 'Read tests/test_auth.py', { durationMs: 95 }),
      T('d5', '14:02:10', 'tool', 'Edited src/auth.ts', { durationMs: 210, detail: '+34 −6 · added expiry check to validateToken()' }),
      T('d6', '14:02:12', 'test', 'Ran pytest tests/auth/', { durationMs: 4800 }),
      T('d7', '14:02:17', 'test', '2 tests failed', { severity: 'error', detail: 'FAILED tests/auth/test_expired.py::test_expired_access_token\nFAILED tests/auth/test_expired.py::test_expired_refresh_token' }),
      T('d8', '14:02:18', 'retry', 'Retry started', { severity: 'warn' }),
      T('d9', '14:02:19', 'tool', 'Read src/auth.ts', { durationMs: 110 }),
      T('d10', '14:02:21', 'tool', 'Read src/auth.ts', { durationMs: 105 }),
      T('d11', '14:02:23', 'tool', 'Edited validation logic', { durationMs: 190, detail: '+12 −3 · src/validation.ts' }),
      T('d12', '14:02:25', 'test', 'Ran pytest tests/auth/', { durationMs: 3600 }),
      T('d13', '14:02:29', 'test', '19 tests passed', { severity: 'ok' }),
      T('d14', '14:02:30', 'event', 'Submission v3 created', { detail: 'files: src/auth.ts, src/validation.ts, tests/test_auth.py' }),
      T('d15', '14:02:31', 'handoff', 'Handoff → Reviewer'),
    ],
    tools: [
      { id: 'dt1', tool: 'READ', input: 'src/auth.ts', at: '14:02:05', durationMs: 120, result: '1,480 tokens', ok: true, output: 'export function validateToken(token: string) {\n  // TODO: check expiry\n  return verify(token, SECRET)\n}' },
      { id: 'dt2', tool: 'READ', input: 'tests/test_auth.py', at: '14:02:07', durationMs: 95, result: '1,210 tokens', ok: true },
      { id: 'dt3', tool: 'WRITE', input: 'src/auth.ts', at: '14:02:10', durationMs: 210, result: '+34 −6', ok: true },
      { id: 'dt4', tool: 'COMMAND', input: 'pytest tests/auth/', at: '14:02:12', durationMs: 4800, result: '17 passed, 2 failed', ok: false, output: '===== test session starts =====\ncollected 19 items\ntests/auth/test_login.py ........\ntests/auth/test_expired.py FF\ntests/auth/test_malformed.py .......\n\nFAILED tests/auth/test_expired.py::test_expired_access_token - AssertionError: expected 401, got 200\nFAILED tests/auth/test_expired.py::test_expired_refresh_token - AssertionError: expected 401, got 200\n===== 2 failed, 17 passed in 4.62s =====' },
      { id: 'dt5', tool: 'READ', input: 'src/auth.ts', at: '14:02:19', durationMs: 110, result: '1,520 tokens', ok: true },
      { id: 'dt6', tool: 'READ', input: 'src/auth.ts', at: '14:02:21', durationMs: 105, result: '1,520 tokens', ok: true },
      { id: 'dt7', tool: 'WRITE', input: 'src/validation.ts', at: '14:02:23', durationMs: 190, result: '+12 −3', ok: true },
      { id: 'dt8', tool: 'COMMAND', input: 'pytest tests/auth/', at: '14:02:25', durationMs: 3600, result: '19 passed', ok: true, output: '===== test session starts =====\ncollected 19 items\ntests/auth/test_login.py ........\ntests/auth/test_expired.py ..\ntests/auth/test_malformed.py .......\n===== 19 passed in 3.51s =====' },
    ],
    outputs: [
      { id: 'do1', kind: 'submission', title: 'Submission v3', body: 'Token authentication implemented; expired and malformed tokens now return 401 on access and refresh paths.', items: ['src/auth.ts (+34 −6)', 'src/validation.ts (+12 −3)', 'tests/test_auth.py (+41 −0)'] },
      { id: 'do2', kind: 'summary', title: 'Implementation summary', body: 'Added expiry validation inside the shared middleware, fixed refresh-token path, and added 6 unit tests. All 19 auth tests pass.' },
    ],
    evidence: [
      { id: 'de1', kind: 'diff', title: '3 files changed', detail: '+87 −9 across src/auth.ts, src/validation.ts, tests/test_auth.py', ref: 'artifact://run-0182/submission-v3.patch' },
      { id: 'de2', kind: 'test', title: 'pytest tests/auth/ — 19 passed', detail: 'previous run: 17 passed, 2 failed', ref: 'log://run-0182/pytest/2', severity: 'ok' },
      { id: 'de3', kind: 'test', title: 'pytest #1 — 2 failed', detail: 'test_expired_access_token, test_expired_refresh_token', ref: 'log://run-0182/pytest/1', severity: 'error' },
      { id: 'de4', kind: 'submission', title: 'Submission v3', detail: 'created 14:02:30 → Reviewer', ref: 'submission://run-0182/3' },
    ],
    usage: { inputTokens: 2610, outputTokens: 810, totalTokens: 3420, estimatedCost: 0.018, llmCalls: 3, retries: 1, totalLatencyMs: 19700, latency: { llmMs: 7200, toolsMs: 4100, testsMs: 8400 } },
    runContext: { runTotalTokens: 9760, reviewRounds: 3, contextTransferTokens: 4210 },
  }
}

function reviewer() {
  return {
    agentId: 'reviewer', name: 'Reviewer', role: 'Verification', status: 'idle', mode: 'live',
    currentTask: 'Review authentication API submission', currentAction: 'Idle — awaiting submission',
    model: 'o4-mini', startedAt: '14:02:31', attempt: 'Review round 3', lastEvent: '14:02:45 Revision feedback sent → Developer', lastCallLatencyMs: 3900,
    prompt: {
      instructions: `You are the Reviewer agent. Verify a submission against the acceptance criteria and the review checklist.\nOutput exactly PASS or FAIL with evidence references. Never edit code.`,
      taskPrompt: 'Review Submission v3 for token authentication against the acceptance criteria.',
      requirements: REQUIREMENTS,
      context: [
        { label: 'Submission v3 (diff + summary)', tokens: 3100, source: 'handoff' },
        { label: 'Review checklist (7 items)', tokens: 380, source: 'config' },
        { label: 'Previous review rounds', tokens: 1650, source: 'memory' },
      ],
      structuredInputs: { runId: 'run-0182', submission: 3, checklist: ['schema unchanged', 'expired → 401', 'malformed → 401', 'tests added', 'no secrets in diff', 'lint clean', 'docs updated'], credentials: { password: 'fake-reviewer-pass-1', apiKey: 'sk-live-FAKEKEYFAKEKEY99' } },
      modelConfig: { model: 'o4-mini', temperature: 0, maxTokens: 1200, tools: ['read_diff', 'run_command'] },
    },
    decisions: [
      { id: 'r-d1', at: '14:02:36', decision: 'Checklist 6/7 passed — docs updated item is missing.', rationale: 'No change to API docs in the diff.', outcome: 'info' },
      { id: 'r-d2', at: '14:02:44', decision: 'FAIL — missing validation for expired tokens on the refresh path.', rationale: 'Diff validates access tokens only; refresh endpoint still accepts expired refresh tokens in one branch.', outcome: 'rejected', refs: ['src/auth.ts:88', 'review-round-3'] },
    ],
    trace: [
      T('r1', '14:02:31', 'handoff', 'Submission v3 received', { detail: 'context: 3,100 tokens' }),
      T('r2', '14:02:32', 'llm', 'LLM invocation started', { detail: 'model: o4-mini' }),
      T('r3', '14:02:34', 'tool', 'Read diff (3 files, +87 −9)', { durationMs: 140 }),
      T('r4', '14:02:36', 'event', 'Checklist evaluated: 6/7 items passed', { severity: 'warn' }),
      T('r5', '14:02:38', 'test', 'Ran pytest tests/auth/', { durationMs: 3500 }),
      T('r6', '14:02:42', 'test', '19 tests passed'),
      T('r7', '14:02:44', 'decision', 'Review FAIL — missing validation for expired tokens', { severity: 'error', durationMs: 3900 }),
      T('r8', '14:02:45', 'handoff', 'Revision feedback sent → Developer'),
    ],
    tools: [
      { id: 'rt1', tool: 'READ', input: 'submission-v3.patch', at: '14:02:34', durationMs: 140, result: '3 files, +87 −9', ok: true, output: 'diff --git a/src/auth.ts b/src/auth.ts\n@@ -80,6 +80,14 @@ export function refresh(token: string) {\n+  // access token expiry validated here\n…' },
      { id: 'rt2', tool: 'COMMAND', input: 'pytest tests/auth/', at: '14:02:38', durationMs: 3500, result: '19 passed', ok: true, output: '===== 19 passed in 3.40s =====' },
      { id: 'rt3', tool: 'COMMAND', input: 'eslint src/auth.ts src/validation.ts', at: '14:02:41', durationMs: 900, result: 'clean', ok: true },
    ],
    outputs: [
      { id: 'ro1', kind: 'verdict', title: 'FAIL', body: 'Missing validation for expired tokens on the refresh path.', items: ['Checklist: 6/7 passed', 'Tests: 19/19 passed', 'Blocking issue: expired refresh token accepted (src/auth.ts:88)'] },
      { id: 'ro2', kind: 'feedback', title: 'Revision feedback → Developer', body: 'Reject expired refresh tokens in refresh(); add a test covering the expired refresh path; update API docs.' },
    ],
    evidence: [
      { id: 're1', kind: 'review', title: 'Review round 3: FAIL', detail: 'blocking: expired refresh token accepted', ref: 'review://run-0182/3', severity: 'error' },
      { id: 're2', kind: 'test', title: 'pytest tests/auth/ — 19 passed', detail: 'tests pass but do not cover the refresh-expiry branch', ref: 'log://run-0182/pytest/3', severity: 'warn' },
      { id: 're3', kind: 'diff', title: 'src/auth.ts:88', detail: 'branch missing expiry check', ref: 'artifact://run-0182/submission-v3.patch#L88' },
    ],
    usage: { inputTokens: 1720, outputTokens: 520, totalTokens: 2240, estimatedCost: 0.009, llmCalls: 2, retries: 0, totalLatencyMs: 12500, latency: { llmMs: 5400, toolsMs: 1900, testsMs: 5200 } },
    runContext: { runTotalTokens: 9760, reviewRounds: 3, contextTransferTokens: 3100 },
  }
}

export const createMockSnapshots = () => ({ manager: manager(), developer: developer(), reviewer: reviewer() })

// ---- deterministic MOCK analysis -> optimization signals (observations, not verdicts) ----
export function analyzeSignals(s) {
  const out = []
  const reads = {}
  for (const t of s.tools || []) if (t.tool === 'READ') reads[t.input] = (reads[t.input] || 0) + 1
  for (const [f, n] of Object.entries(reads)) if (n >= 3) out.push({ id: `reads-${f}`, severity: 'warn', observation: `Same file read ${n} times (${f})`, potential: 'Potential optimization: reuse the existing file context instead of re-reading.' })
  const failedRuns = (s.tools || []).filter((t) => t.tool === 'COMMAND' && !t.ok).length
  if ((s.usage?.retries || 0) >= 1 || failedRuns >= 1) out.push({ id: 'retries', severity: 'warn', observation: `${Math.max(s.usage?.retries || 0, failedRuns)} failed test run${failedRuns > 1 ? 's' : ''} led to a retry`, potential: 'Potential optimization: run the failing test in isolation first, or add the failing case to the task prompt.' })
  if ((s.runContext?.reviewRounds || 0) >= 3 && s.agentId === 'reviewer') out.push({ id: 'rounds', severity: 'warn', observation: `Reviewer caused ${s.runContext.reviewRounds} revision rounds`, potential: 'Potential optimization: improve task acceptance criteria so issues are caught earlier.' })
  const share = s.runContext?.runTotalTokens ? (s.usage?.totalTokens || 0) / s.runContext.runTotalTokens : 0
  if (share >= 0.4) out.push({ id: 'share', severity: 'info', observation: `${s.name} consumed ${Math.round(share * 100)}% of run tokens`, potential: 'Potential optimization: reduce planning context.' })
  const lat = s.usage?.latency
  if (lat && s.usage.totalLatencyMs) { const toolShare = ((lat.toolsMs || 0) + (lat.testsMs || 0)) / s.usage.totalLatencyMs; if (toolShare >= 0.6) out.push({ id: 'toolshare', severity: 'info', observation: `Tool/test execution is ${Math.round(toolShare * 100)}% of total latency`, potential: 'Potential optimization: cache dependencies or run a targeted test subset.' }) }
  if ((s.runContext?.contextTransferTokens || 0) >= 3000 && s.agentId !== 'manager') out.push({ id: 'ctx', severity: 'info', observation: `Large context transferred between agents (${(s.runContext.contextTransferTokens / 1000).toFixed(1)}k tokens)`, potential: 'Potential optimization: pass a summary + diff instead of full file contents.' })
  return out
}

// ---- development-only simulation: office state -> appended mock events ----
const STATUS = {
  manager: { idle: ['idle', 'Idle — awaiting request'], thinking: ['thinking', 'Planning — breaking the task into subtasks'], assigning: ['assigning', 'Assigning subtasks → Developer'] },
  developer: { idle: ['idle', 'Idle — awaiting task'], receiving: ['receiving', 'Reading assignment from Manager'], working: ['working', 'Editing src/auth.ts'], testing: ['testing', 'Running pytest tests/auth/'], submitting: ['submitting', 'Creating Submission v4'], blocked: ['blocked', 'Blocked — tests failing after retry'] },
  reviewer: { idle: ['idle', 'Idle — awaiting submission'], receiving: ['receiving', 'Receiving Submission v4'], reviewing: ['reviewing', 'Reviewing diff against checklist'], pass: ['PASS', 'Review complete — PASS'], fail: ['FAIL', 'Review complete — FAIL'] },
}
const EVENTS = {
  manager: {
    thinking: [['llm', 'LLM invocation started (planning)', 'ok', { dur: 0 }]],
    assigning: [['decision', 'Decision recorded: assign subtasks to Developer', 'ok'], ['handoff', 'Assigned subtasks → Developer', 'ok']],
  },
  developer: {
    receiving: [['task', 'Task received from Manager', 'ok']],
    working: [['llm', 'LLM invocation started', 'ok'], ['tool', 'Edited src/auth.ts', 'ok', { dur: 200 }]],
    testing: [['test', 'Ran pytest tests/auth/', 'ok', { dur: 4100 }]],
    submitting: [['event', 'Submission v4 created', 'ok'], ['handoff', 'Handoff → Reviewer', 'ok']],
    blocked: [['test', '2 tests failed (retry limit reached)', 'error', { detail: 'FAILED tests/auth/test_expired.py::test_expired_refresh_token' }], ['error', 'Blocked — awaiting guidance', 'warn']],
  },
  reviewer: {
    receiving: [['handoff', 'Submission v4 received', 'ok']],
    reviewing: [['llm', 'LLM invocation started (review)', 'ok'], ['tool', 'Read diff (3 files)', 'ok', { dur: 140 }]],
    pass: [['decision', 'Review PASS — all checklist items satisfied', 'ok']],
    fail: [['decision', 'Review FAIL — missing validation for expired tokens', 'error'], ['handoff', 'Revision feedback sent → Developer', 'ok']],
  },
}
const clockAdd = (hms, secs) => { const [h, m, s] = hms.split(':').map(Number); const t = h * 3600 + m * 60 + s + secs; return [Math.floor(t / 3600) % 24, Math.floor(t / 60) % 60, t % 60].map((n) => String(n).padStart(2, '0')).join(':') }
const lastAt = (s) => s.trace[s.trace.length - 1]?.at || '14:02:00'

export function applyTransition(snap, agentId, pose) {
  const st = STATUS[agentId]?.[pose]
  if (!st) return snap
  const evs = EVENTS[agentId]?.[pose] || []
  let at = lastAt(snap)
  const trace = [...snap.trace], tools = [...snap.tools], decisions = [...snap.decisions], evidence = [...snap.evidence]
  const usage = { ...snap.usage, latency: { ...snap.usage.latency } }
  evs.forEach(([type, text, sev, x = {}], i) => {
    at = clockAdd(at, 2 + i)
    const id = `sim-${trace.length}`
    trace.push({ id, at, type, text, severity: sev, durationMs: x.dur || undefined, detail: x.detail })
    if (type === 'llm') { usage.llmCalls = (usage.llmCalls || 0) + 1; usage.inputTokens = (usage.inputTokens || 0) + 420; usage.outputTokens = (usage.outputTokens || 0) + 160; usage.totalTokens = usage.inputTokens + usage.outputTokens; usage.estimatedCost = +((usage.estimatedCost || 0) + 0.004).toFixed(3); usage.latency.llmMs = (usage.latency.llmMs || 0) + 1800; usage.totalLatencyMs = (usage.totalLatencyMs || 0) + 1800 }
    if (type === 'tool') { tools.push({ id: `${id}-t`, tool: text.startsWith('Edited') ? 'WRITE' : 'READ', input: text.replace(/^(Edited|Read) /, ''), at, durationMs: x.dur || 120, result: 'ok', ok: true }); usage.latency.toolsMs = (usage.latency.toolsMs || 0) + (x.dur || 120); usage.totalLatencyMs = (usage.totalLatencyMs || 0) + (x.dur || 120) }
    if (type === 'test') { const ok = sev !== 'error'; tools.push({ id: `${id}-c`, tool: 'COMMAND', input: 'pytest tests/auth/', at, durationMs: x.dur || 3000, result: ok ? '19 passed' : '17 passed, 2 failed', ok, output: x.detail }); usage.latency.testsMs = (usage.latency.testsMs || 0) + (x.dur || 3000); usage.totalLatencyMs = (usage.totalLatencyMs || 0) + (x.dur || 3000); if (!ok) usage.retries = (usage.retries || 0) + 1 }
    if (type === 'decision') decisions.push({ id: `${id}-d`, at, decision: text.replace(/^Decision recorded: /, ''), rationale: 'Recorded by the workflow (simulated).', outcome: sev === 'error' ? 'rejected' : 'accepted' })
    if (type === 'handoff' || type === 'event') evidence.push({ id: `${id}-e`, kind: 'log', title: text, detail: `simulated at ${at}`, ref: `log://run-0182/${id}` })
  })
  return analyzeAndStamp({ ...snap, status: st[0], currentAction: st[1], trace, tools, decisions, evidence, usage, lastEvent: evs.length ? `${at} ${trace[trace.length - 1].text}` : snap.lastEvent })
}
export function analyzeAndStamp(s) { return { ...s, optimizationSignals: analyzeSignals(s) } }
export function initialSnapshots(poses) {
  const base = createMockSnapshots()
  const out = {}
  for (const id of Object.keys(base)) {
    const st = STATUS[id]?.[poses?.[id]]
    out[id] = analyzeAndStamp({ ...base[id], ...(st ? { status: st[0], currentAction: st[1] } : {}) })
  }
  return out
}
