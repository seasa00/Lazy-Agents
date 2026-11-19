# Lazy Agents — Agent Inspector data contract

Production flow:

    Lazy Agents backend → debug/observability adapter → AgentDebugSnapshot → <AgentInspector />

The inspector (`src/inspector/AgentInspector.jsx`) reads **only** an `AgentDebugSnapshot`. Today the snapshot
comes from `src/debug/mockData.js` + `useAgentDebug.js` (dev-only simulation). Replace those two files with a real
adapter that returns the same shape; no inspector code changes are needed. Full JSDoc types: `src/debug/contract.js`.

## What the backend must provide (per agent: manager | developer | reviewer)

| Field | Purpose | Notes |
|---|---|---|
| `agentId, name, role` | identity | |
| `status`, `mode` (`live`/`historical`) | header, LIVE badge | status should mirror the office pose |
| `currentTask`, `currentAction` | header + Overview | |
| `model`, `startedAt`, `attempt`, `lastEvent`, `lastCallLatencyMs` | Overview | `attempt` = attempt / review round label |
| `trace[]` | Execution Trace | `{id, at, type, text, durationMs?, severity ok/warn/error/info, detail?}` — chronological, append-only |
| `tools[]` | Tools | `{tool READ/WRITE/COMMAND/…, input, at, durationMs, result, ok, output?}` |
| `prompt` | Prompt & Context | `{instructions, taskPrompt, requirements?, context[{label,tokens,source}], structuredInputs, modelConfig}` |
| `decisions[]` | Decisions | explicit, stored workflow decisions + optional stored `rationale`. **Never raw chain-of-thought.** |
| `outputs[]` | Output | plan/assignment/revision (Manager), submission/summary (Developer), verdict/feedback (Reviewer) |
| `evidence[]` | Evidence | file / diff / test / review / submission / log / artifact references |
| `usage` | Usage | input/output/total tokens, estimatedCost, llmCalls, retries, totalLatencyMs, `latency{llmMs,toolsMs,testsMs}` |
| `runContext` | optimization signals | `runTotalTokens`, `reviewRounds`, `contextTransferTokens` |
| `optimizationSignals[]` | Usage tab | optional: backend may send its own; otherwise compute client-side (see `analyzeSignals`) |

## Events the backend should emit (for live updates)

`agent.state_changed {agentId, state}` (drives office pose + status), `trace.appended`, `tool.started/finished`,
`llm.started/finished {tokens, latency, cost}`, `decision.recorded`, `handoff {from,to}`, `review.result {pass|fail, feedback}`.
The adapter folds these into snapshots; the office scene only needs the pose per agent.

## Security

- Everything rendered passes through `src/debug/redact.js` (`redactDeep` on the whole snapshot): API keys, bearer
  tokens, JWTs, passwords, secret-named fields, credentials in URLs. Do the same server-side — redact **before** the
  snapshot leaves the backend; the client redaction is a second line of defence.
- Do not send hidden model reasoning. Send structured `decisions` the workflow stored on purpose.

## Canvas ↔ React boundary

Canvas (`src/pixel/*`) draws, hit-tests (`HIT` rects per agent: character + workstation), shows hover/selection markers.
React owns `selectedAgent`, the inspector, tabs, trace/log/prompt UI, usage and signals.
