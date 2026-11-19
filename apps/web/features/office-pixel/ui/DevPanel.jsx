import { useState } from 'react'
import { POSES, handoffPresets } from '../state/mockOfficeState.js'
const label = (s) => s.charAt(0).toUpperCase() + s.slice(1)
function Chips({ options, value, onPick, name, fmt = label }) {
  return <div className="chips" role="group" aria-label={name}>{options.map((o) => <button key={o} type="button" aria-pressed={value === o} onClick={() => onPick(o)}>{fmt(o)}</button>)}</div>
}
export default function DevPanel({ state, dispatch, selected, setSelected }) {
  const [open, setOpen] = useState(false)
  const setPose = (agent, pose) => dispatch({ type: 'pose', agent, pose })
  const preset = (p) => dispatch({ type: 'preset', preset: p })
  return (
    <aside className="dev" aria-label="Development controls">
      <header onClick={() => setOpen((o) => !o)}>DEV CONTROLS <span>{open ? '[-]' : '[+]'}</span></header>
      {open && (
        <div className="body">
          <div className="row"><label>Palette</label><Chips name="Palette" options={['day', 'night']} value={state.theme} fmt={(o) => (o === 'day' ? 'Paper' : 'Neon')} onPick={(v) => dispatch({ type: 'theme', value: v })} /></div>
          <div className="row"><label>Inspect agent</label><Chips name="Inspect" options={['manager', 'developer', 'reviewer']} value={selected} onPick={(v) => setSelected(selected === v ? null : v)} /></div>
          {['manager', 'developer', 'reviewer'].map((r) => <div className="row" key={r}><label>{label(r)}</label><Chips name={r} options={POSES[r]} value={state.agents[r].pose} fmt={(o) => (o === 'pass' || o === 'fail' ? o.toUpperCase() : label(o))} onPick={(v) => setPose(r, v)} /></div>)}
          <div className="row"><label>Handoff poses</label>
            <div className="handoffs">
              <button type="button" onClick={() => preset(handoffPresets.managerToDeveloper)}>Manager → Developer</button>
              <button type="button" onClick={() => preset(handoffPresets.developerToReviewer)}>Developer → Reviewer</button>
              <button type="button" onClick={() => preset(handoffPresets.reviewFail)}>Review FAIL</button>
              <button type="button" onClick={() => preset(handoffPresets.reviewPass)}>Review PASS</button>
            </div></div>
          <div className="row"><label>Reduced motion</label><Chips name="Reduced motion" options={['On', 'Off']} value={state.reducedMotion ? 'On' : 'Off'} fmt={(o) => o} onPick={(v) => dispatch({ type: 'reducedMotion', value: v === 'On' })} /></div>
        </div>
      )}
    </aside>
  )
}
