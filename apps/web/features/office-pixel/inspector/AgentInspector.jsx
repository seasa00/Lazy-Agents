import { useEffect, useMemo, useRef, useState } from 'react'
import { redactDeep } from '../debug/redact.js'
import './inspector.css'

const TABS = [
  ['overview', 'Overview'], ['trace', 'Execution Trace'], ['prompt', 'Prompt & Context'], ['decisions', 'Decisions'],
  ['tools', 'Tools'], ['output', 'Output'], ['evidence', 'Evidence'], ['usage', 'Usage'],
]
const ACCENT = { manager: 'mgr', developer: 'dev', reviewer: 'rev' }
const fmtMs = (ms) => (ms == null ? '—' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`)
const fmtN = (n) => (n == null ? '—' : n.toLocaleString('en-US'))
const fmtCost = (c) => (c == null ? '—' : `$${c.toFixed(3)}`)
const sevCls = (s) => ({ ok: 'ok', warn: 'warn', error: 'err', info: 'info' }[s] || 'ok')
const TYPE_GLYPH = { task: '▸', llm: '◆', tool: '⚙', test: '✓', retry: '↻', decision: '◇', handoff: '→', error: '✕', event: '●' }

function CopyBtn({ text, label = 'Copy' }) {
  const [done, setDone] = useState(false)
  const copy = async (e) => {
    e.stopPropagation()
    try { await navigator.clipboard.writeText(text) } catch { /* clipboard may be blocked in sandboxed frames */ }
    setDone(true); setTimeout(() => setDone(false), 1200)
  }
  return <button type="button" className="ai-copy" onClick={copy} aria-label={`${label} to clipboard`}>{done ? 'Copied' : label}</button>
}

function Collapsible({ title, meta, defaultOpen = false, copyText, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="ai-card">
      <header className="ai-card-h" onClick={() => setOpen(!open)}>
        <button type="button" className="ai-chev" aria-expanded={open}>{open ? '▾' : '▸'}</button>
        <span className="ai-card-t">{title}</span>
        {meta && <span className="ai-meta">{meta}</span>}
        {copyText != null && <CopyBtn text={copyText} />}
      </header>
      {open && <div className="ai-card-b">{children}</div>}
    </section>
  )
}

function OutputLines({ text }) {
  return (
    <pre className="ai-pre">{String(text).split('\n').map((l, i) => (
      <span key={i} className={/FAILED|failed|Error|error|✕/.test(l) ? 'ln-err' : /passed|ok\b|clean/.test(l) ? 'ln-ok' : /warn/i.test(l) ? 'ln-warn' : ''}>{l}{'\n'}</span>
    ))}</pre>
  )
}

/* ---------------- tabs ---------------- */
function Overview({ s, go }) {
  const u = s.usage || {}
  const rows = [
    ['Status', s.status], ['Task', s.currentTask], ['Current action', s.currentAction], ['Model', s.model], ['Started', s.startedAt],
    ['Attempt / round', s.attempt], ['Last event', s.lastEvent], ['Tokens', fmtN(u.totalTokens)], ['Est. cost', fmtCost(u.estimatedCost)],
    ['Latency (last call)', fmtMs(s.lastCallLatencyMs)], ['Retries', fmtN(u.retries)], ['LLM calls', fmtN(u.llmCalls)],
  ]
  const n = s.optimizationSignals?.length || 0
  return (
    <div>
      <div className="ai-hero"><span className="ai-k">Current action</span><strong>{s.currentAction || '—'}</strong></div>
      <dl className="ai-kv">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v ?? '—'}</dd></div>)}</dl>
      {n > 0 && <button type="button" className="ai-chip-btn" onClick={() => go('usage')}>⚠ {n} optimization signal{n > 1 ? 's' : ''} — view in Usage</button>}
    </div>
  )
}

function Trace({ s }) {
  const [errOnly, setErrOnly] = useState(false)
  const [open, setOpen] = useState({})
  const list = (s.trace || []).filter((t) => !errOnly || t.severity === 'error' || t.severity === 'warn')
  return (
    <div>
      <label className="ai-toggle"><input type="checkbox" checked={errOnly} onChange={(e) => setErrOnly(e.target.checked)} /> Errors &amp; warnings only</label>
      <ol className="ai-trace">
        {list.map((t) => (
          <li key={t.id} className={`ai-tr ${sevCls(t.severity)}`}>
            <button type="button" className="ai-tr-row" onClick={() => t.detail && setOpen({ ...open, [t.id]: !open[t.id] })} aria-expanded={!!open[t.id]} disabled={!t.detail}>
              <time>{t.at}</time>
              <span className="ai-glyph" aria-hidden>{TYPE_GLYPH[t.type] || '●'}</span>
              <span className="ai-tr-text">{t.text}</span>
              {t.durationMs != null && <span className="ai-dur">{fmtMs(t.durationMs)}</span>}
              {t.detail && <span className="ai-chev">{open[t.id] ? '▾' : '▸'}</span>}
            </button>
            {open[t.id] && <OutputLines text={t.detail} />}
          </li>
        ))}
      </ol>
    </div>
  )
}

function Prompt({ s, redactions }) {
  const p = s.prompt
  if (!p) return <p className="ai-empty">No prompt information captured.</p>
  const mc = p.modelConfig || {}
  const json = (o) => JSON.stringify(o, null, 2)
  return (
    <div>
      <p className="ai-note">Secrets are always redacted{redactions ? ` — ${redactions} value${redactions > 1 ? 's' : ''} masked in this snapshot` : ''}.</p>
      <Collapsible title="Agent instructions" copyText={p.instructions} defaultOpen><pre className="ai-pre wrap">{p.instructions}</pre></Collapsible>
      <Collapsible title="Task prompt" copyText={p.taskPrompt} defaultOpen><pre className="ai-pre wrap">{p.taskPrompt}</pre></Collapsible>
      {p.requirements && <Collapsible title="User / project requirements" copyText={p.requirements}><pre className="ai-pre wrap">{p.requirements}</pre></Collapsible>}
      <Collapsible title={s.source === 'backend' ? 'Retained context references' : 'Context passed to this invocation'} meta={s.source === 'backend' ? 'stored references' : `${fmtN((p.context || []).reduce((a, c) => a + (c.tokens || 0), 0))} tokens`}>
        <ul className="ai-ctx">{(p.context || []).map((c, i) => <li key={i}><span>{c.label}</span><em>{c.source}</em>{c.tokens != null && <b>{fmtN(c.tokens)} tok</b>}</li>)}</ul>
      </Collapsible>
      <Collapsible title="Structured inputs" copyText={json(p.structuredInputs)}><OutputLines text={json(p.structuredInputs)} /></Collapsible>
      <Collapsible title="Model configuration" copyText={json(mc)}><OutputLines text={json(mc)} /></Collapsible>
    </div>
  )
}

function Decisions({ s }) {
  return (
    <div>
      <p className="ai-note">Structured decision summaries recorded by the workflow. This is not raw model reasoning.</p>
      {(s.decisions || []).map((d) => (
        <article key={d.id} className={`ai-card ai-dec ${d.outcome || ''}`}>
          <header><time>{d.at}</time>{d.outcome && <span className={`ai-tag ${d.outcome}`}>{d.outcome}</span>}</header>
          <p className="ai-dec-t">{d.decision}</p>
          {d.rationale && <p className="ai-dec-r"><span className="ai-k">Stored rationale</span>{d.rationale}</p>}
          {d.refs?.length > 0 && <p className="ai-refs">{d.refs.map((r) => <code key={r}>{r}</code>)}</p>}
        </article>
      ))}
      {!s.decisions?.length && <p className="ai-empty">No decisions recorded yet.</p>}
    </div>
  )
}

function Tools({ s }) {
  const [open, setOpen] = useState({})
  return (
    <ul className="ai-tools">
      {(s.tools || []).map((t) => (
        <li key={t.id} className={t.ok ? 'ok' : 'err'}>
          <button type="button" className="ai-tool-row" onClick={() => t.output && setOpen({ ...open, [t.id]: !open[t.id] })} aria-expanded={!!open[t.id]} disabled={!t.output}>
            <span className={`ai-tool-badge ${t.tool.toLowerCase()}`}>{t.tool}</span>
            <code className="ai-tool-in">{t.input}</code>
            <span className="ai-dur">{fmtMs(t.durationMs)}</span>
            {t.output && <span className="ai-chev">{open[t.id] ? '▾' : '▸'}</span>}
          </button>
          <div className="ai-tool-res"><time>{t.at}</time><span className={t.ok ? 'ln-ok' : 'ln-err'}>{t.ok ? '✓' : '✕'} {t.result}</span></div>
          {open[t.id] && <OutputLines text={t.output} />}
        </li>
      ))}
    </ul>
  )
}

function Output({ s }) {
  return (
    <div>
      {(s.outputs || []).map((o) => (
        <article key={o.id} className="ai-card ai-out">
          <header><span className="ai-tag">{o.kind}</span><strong className={o.title === 'FAIL' ? 'ln-err' : o.title === 'PASS' ? 'ln-ok' : ''}>{o.title}</strong></header>
          <p>{o.body}</p>
          {o.items?.length > 0 && <ul>{o.items.map((i, k) => <li key={k}>{i}</li>)}</ul>}
        </article>
      ))}
    </div>
  )
}

function Evidence({ s }) {
  const G = { file: 'F', diff: 'Δ', test: 'T', review: 'R', submission: 'S', log: 'L', artifact: 'A' }
  return (
    <div className="ai-ev">
      {(s.evidence || []).map((e) => (
        <article key={e.id} className={`ai-card ai-evc ${sevCls(e.severity)}`}>
          <span className="ai-ev-ic">{G[e.kind] || '•'}</span>
          <div><strong>{e.title}</strong>{e.detail && <p>{e.detail}</p>}{e.ref && <code>{e.ref}</code>}</div>
          {e.ref && <CopyBtn text={e.ref} label="Copy ref" />}
        </article>
      ))}
    </div>
  )
}

function Bar({ label, value, total, cls }) {
  const pct = total ? Math.max(2, Math.round((value / total) * 100)) : 0
  return <div className="ai-bar"><span>{label}</span><div><i className={cls} style={{ width: `${pct}%` }} /></div><b>{fmtMs(value)}</b></div>
}
function Usage({ s }) {
  const u = s.usage || {}, l = u.latency || {}
  const tot = u.totalLatencyMs || (l.llmMs || 0) + (l.toolsMs || 0) + (l.testsMs || 0)
  const tokTot = u.totalTokens || 1
  return (
    <div>
      <dl className="ai-kv ai-kv3">
        {[['Input tokens', fmtN(u.inputTokens)], ['Output tokens', fmtN(u.outputTokens)], ['Total tokens', fmtN(u.totalTokens)], ['Est. cost', fmtCost(u.estimatedCost)], ['Model', s.model], ['LLM calls', fmtN(u.llmCalls)], ['Retries', fmtN(u.retries)], ['Total latency', fmtMs(u.totalLatencyMs)], ['Tool time', fmtMs((l.toolsMs || 0) + (l.testsMs || 0))]].map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
      </dl>
      <h4 className="ai-h">Token split</h4>
      <div className="ai-split"><i className="in" style={{ width: `${((u.inputTokens || 0) / tokTot) * 100}%` }} /><i className="out" style={{ width: `${((u.outputTokens || 0) / tokTot) * 100}%` }} /></div>
      <p className="ai-legend"><span className="in">input {fmtN(u.inputTokens)}</span><span className="out">output {fmtN(u.outputTokens)}</span></p>
      <h4 className="ai-h">Latency breakdown</h4>
      <Bar label="LLM" value={l.llmMs || 0} total={tot} cls="llm" />
      <Bar label="Tools" value={l.toolsMs || 0} total={tot} cls="tools" />
      <Bar label="Tests" value={l.testsMs || 0} total={tot} cls="tests" />
      <Bar label="Total" value={tot} total={tot} cls="total" />
      <h4 className="ai-h">Optimization signals</h4>
      <p className="ai-note">{s.source === 'backend' ? 'Observations from retained backend records — signals, not definitive recommendations.' : 'Observations from deterministic mock analysis — signals, not definitive recommendations.'}</p>
      {(s.optimizationSignals || []).map((o) => (
        <div key={o.id} className={`ai-sig ${sevCls(o.severity)}`}><strong>⚠ {o.observation}</strong><p>{o.potential}</p></div>
      ))}
      {!s.optimizationSignals?.length && <p className="ai-empty">No signals for this agent.</p>}
    </div>
  )
}

/* ---------------- shell ---------------- */
export default function AgentInspector({ snapshot, onClose, variant = 'side', width }) {
  const [tab, setTab] = useState('overview')
  const [frozen, setFrozen] = useState(null)
  const panel = useRef()
  const live = !frozen
  const raw = frozen || snapshot
  const { value: s, redactions } = useMemo(() => redactDeep(raw), [raw])
  useEffect(() => { setFrozen(null) }, [snapshot.agentId])
  useEffect(() => { const k = (e) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [onClose])
  useEffect(() => { panel.current?.scrollTo?.({ top: 0 }) }, [tab, snapshot.agentId])
  const idle = /idle/i.test(s.status)
  return (
    <aside className={`ai ${variant} ai-${ACCENT[s.agentId]}`} style={width ? { '--ai-w': `${width}px` } : undefined} aria-label={`${s.name} inspector`}>
      <header className="ai-head">
        <div className="ai-id">
          <span className="ai-avatar" aria-hidden />
          <div>
            <h2>{s.name} <span className={`ai-live ${live && !idle ? 'on' : ''}`}>{!live ? '❚❚ SNAPSHOT' : s.mode === 'historical' ? '○ HISTORICAL' : idle ? '○ IDLE' : '● LIVE'}</span></h2>
            <p className="ai-sub"><strong>{s.status}</strong> · {s.role}</p>
          </div>
        </div>
        <button type="button" className="ai-close" onClick={onClose} aria-label="Close inspector">✕</button>
        <p className="ai-task"><span className="ai-k">Task</span> {s.currentTask}</p>
        <div className="ai-bar-row">
          {s.source !== 'backend' && <span className="ai-mock">MOCK DATA</span>}
          <button type="button" className="ai-seg" onClick={() => setFrozen(frozen ? null : snapshot)} aria-pressed={!live}>{live ? 'Freeze snapshot' : 'Resume live'}</button>
        </div>
      </header>
      <nav className="ai-tabs" role="tablist" aria-label="Inspector sections">
        {TABS.map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>{label}</button>)}
      </nav>
      <div className="ai-body" ref={panel} role="tabpanel">
        {tab === 'overview' && <Overview s={s} go={setTab} />}
        {tab === 'trace' && <Trace s={s} />}
        {tab === 'prompt' && <Prompt s={s} redactions={redactions} />}
        {tab === 'decisions' && <Decisions s={s} />}
        {tab === 'tools' && <Tools s={s} />}
        {tab === 'output' && <Output s={s} />}
        {tab === 'evidence' && <Evidence s={s} />}
        {tab === 'usage' && <Usage s={s} />}
      </div>
    </aside>
  )
}
