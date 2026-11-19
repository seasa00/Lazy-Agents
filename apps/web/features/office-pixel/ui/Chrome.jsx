import { useState } from 'react'
import { popoutUrl } from '../sync/officeSync.js'

const ROLES = [['manager', 'Manager', 'r-mgr'], ['developer', 'Developer', 'r-dev'], ['reviewer', 'Reviewer', 'r-rev']] // (class 'dev' would collide with the DEV CONTROLS panel)
const CONN = { live: ['● LIVE', 'ok'], standalone: ['● STANDALONE', 'ok'], connecting: ['◌ CONNECTING', 'warn'], disconnected: ['✕ DISCONNECTED', 'err'] }
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)

// Slim, low-contrast status strip: one chip per agent (also a keyboard-accessible way to select) + connection.
export function StatusBar({ agents, selected, onSelect, connection }) {
  const [txt, cls] = CONN[connection] || CONN.live
  return (
    <div className="sb" role="toolbar" aria-label="Agents">
      {ROLES.map(([id, name, k]) => (
        <button key={id} type="button" className={`sb-chip ${k}${selected === id ? ' on' : ''}`} onClick={() => onSelect(id)} aria-pressed={selected === id}>
          <i aria-hidden />{name}<em>{cap(agents[id].pose)}</em>
        </button>
      ))}
      <span className={`sb-conn ${cls}`}>{txt}</span>
    </div>
  )
}

// Pop out / Fullscreen — deliberately small and quiet.
export function ViewControls({ popout, fullscreen, canFullscreen, onFullscreen, scale }) {
  const [note, setNote] = useState('')
  const open = () => {
    let w = null
    try { w = window.open(popoutUrl(), 'lazy-agents-office', 'popup=yes,width=960,height=720') } catch { /* blocked */ }
    setNote(w ? '' : 'Pop-up blocked — allow pop-ups for this page')
    if (!w) setTimeout(() => setNote(''), 4000)
  }
  return (
    <div className="vc">
      {note && <span className="vc-note">{note}</span>}
      {scale && <span className="vc-scale" title="Display scale of the 480×360 logical office">{scale.scale.toFixed(2).replace(/\.00$/, '')}×{scale.integer ? '' : ' fit'}</span>}
      {!popout && <button type="button" onClick={open} title="Open the office in a separate window">Pop out ⧉</button>}
      {canFullscreen && <button type="button" onClick={onFullscreen}>{fullscreen ? 'Exit fullscreen' : 'Fullscreen ⛶'}</button>}
    </div>
  )
}

// Compact mode: small card instead of the full inspector.
export function CompactCard({ snapshot, onInspect, onClose }) {
  const u = snapshot.usage || {}
  return (
    <div className={`cc cc-${{ manager: 'mgr', developer: 'dev', reviewer: 'rev' }[snapshot.agentId]}`} role="dialog" aria-label={`${snapshot.name} summary`}>
      <button type="button" className="cc-x" onClick={onClose} aria-label="Deselect agent">✕</button>
      <strong>{snapshot.name} · {cap(snapshot.status)}</strong>
      <p>{snapshot.currentAction}</p>
      <div className="cc-row"><small>{(u.totalTokens ?? 0).toLocaleString('en-US')} tok · ${(u.estimatedCost ?? 0).toFixed(3)}</small><button type="button" className="cc-go" onClick={onInspect}>Inspect</button></div>
    </div>
  )
}
