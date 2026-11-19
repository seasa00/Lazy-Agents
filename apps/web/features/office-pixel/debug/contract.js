/**
 * Lazy Agents — debug / observability contract (what a backend adapter must return).
 * Plain JS + JSDoc so it can be dropped into the Next.js app (or converted to .ts) unchanged.
 *
 * Production flow:   Lazy Agents backend -> debug adapter -> AgentDebugSnapshot -> <AgentInspector />
 * The inspector only ever reads an AgentDebugSnapshot; it never knows where it came from.
 *
 * NOTE: nothing here carries hidden model chain-of-thought. `decisions` are explicit, stored
 * workflow decisions (with an optional human-readable rationale that the workflow itself recorded).
 *
 * @typedef {'manager'|'developer'|'reviewer'} AgentId
 * @typedef {'ok'|'warn'|'error'|'info'} Severity
 *
 * @typedef {Object} TraceEntry
 * @property {string} id
 * @property {string} at             ISO time or HH:MM:SS
 * @property {string} type           task | llm | tool | test | retry | decision | handoff | error | event
 * @property {string} text           short description
 * @property {number} [durationMs]
 * @property {Severity} [severity]
 * @property {string} [detail]       expandable (redacted by the UI)
 *
 * @typedef {Object} ToolInvocation
 * @property {string} id
 * @property {'READ'|'WRITE'|'COMMAND'|'SEARCH'|'API'|string} tool
 * @property {string} input          input summary (path / command / query)
 * @property {string} at
 * @property {number} [durationMs]
 * @property {string} result         one-line result
 * @property {boolean} ok
 * @property {string} [output]       raw output, expandable (redacted by the UI)
 *
 * @typedef {Object} DecisionEntry
 * @property {string} id
 * @property {string} at
 * @property {string} decision       e.g. "FAIL — missing validation for expired tokens"
 * @property {string} [rationale]    stored explanation produced by the workflow (not raw reasoning)
 * @property {'accepted'|'rejected'|'pending'|'info'} [outcome]
 * @property {string[]} [refs]
 *
 * @typedef {Object} PromptDebugInfo
 * @property {string} instructions   agent instructions / system prompt
 * @property {string} taskPrompt
 * @property {string} [requirements]
 * @property {{label:string, tokens?:number, source?:string, preview?:string}[]} context
 * @property {Object} [structuredInputs]
 * @property {{model:string, temperature?:number, maxTokens?:number, tools?:string[]}} modelConfig
 *
 * @typedef {Object} AgentOutput
 * @property {string} id
 * @property {string} kind           plan | assignment | revision | submission | summary | verdict | feedback
 * @property {string} title
 * @property {string} body
 * @property {string[]} [items]
 *
 * @typedef {Object} EvidenceEntry
 * @property {string} id
 * @property {'file'|'diff'|'test'|'review'|'submission'|'log'|'artifact'} kind
 * @property {string} title
 * @property {string} [detail]
 * @property {string} [ref]
 * @property {Severity} [severity]
 *
 * @typedef {Object} OptimizationSignal
 * @property {string} id
 * @property {Severity} severity
 * @property {string} observation
 * @property {string} potential      "Potential optimization: ..."  (an observation, never a verdict)
 *
 * @typedef {Object} AgentDebugSnapshot
 * @property {AgentId} agentId
 * @property {string} name
 * @property {string} role
 * @property {string} status                    idle | thinking | receiving | working | ... (display string)
 * @property {'live'|'historical'} mode
 * @property {string} [currentTask]
 * @property {string} [currentAction]
 * @property {string} [model]
 * @property {string} [startedAt]
 * @property {string} [attempt]                 attempt / review round label
 * @property {string} [lastEvent]
 * @property {number} [lastCallLatencyMs]
 * @property {PromptDebugInfo} [prompt]
 * @property {DecisionEntry[]} decisions
 * @property {TraceEntry[]} trace
 * @property {ToolInvocation[]} tools
 * @property {AgentOutput[]} outputs
 * @property {EvidenceEntry[]} evidence
 * @property {{inputTokens?:number, outputTokens?:number, totalTokens?:number, estimatedCost?:number,
 *            llmCalls?:number, retries?:number, totalLatencyMs?:number,
 *            latency?:{llmMs?:number, toolsMs?:number, testsMs?:number}}} usage
 * @property {{runTotalTokens?:number, reviewRounds?:number, contextTransferTokens?:number}} [runContext]  inputs for signals
 * @property {OptimizationSignal[]} optimizationSignals
 */
export const AGENT_IDS = ['manager', 'developer', 'reviewer']
