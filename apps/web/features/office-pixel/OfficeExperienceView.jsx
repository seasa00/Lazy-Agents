import { useCallback, useEffect, useRef, useState } from 'react'
import PixelOffice from './pixel/PixelOffice.jsx'
import DevPanel from './ui/DevPanel.jsx'
import { StatusBar, ViewControls, CompactCard } from './ui/Chrome.jsx'
import AgentInspector from './inspector/AgentInspector.jsx'
import { useOfficeController } from './sync/useOfficeController.js'
import { isPopoutRoute } from './sync/officeSync.js'
import { useDisplay } from './layout/useDisplay.js'
import { getInspection, getSnapshot } from '../../lib/api/client'

const ROLES = ['manager', 'developer', 'reviewer']
const emptySnapshot = (kind) => ({
  agentId: kind, source: 'backend', name: kind[0].toUpperCase() + kind.slice(1),
  role: '', status: 'idle', mode: 'live', currentTask: null, currentAction: null,
  model: null, trace: [], tools: [], decisions: [], outputs: [], evidence: [],
  usage: {}, optimizationSignals: [],
})
const emptySnaps = Object.fromEntries(ROLES.map((kind) => [kind, emptySnapshot(kind)]))

function OfficeShell({ office, snaps, dispatch, connection, popout, liveUrl, backend, onSelectionChange }) {
  const display = useDisplay()
  const { mode } = display
  const [selected, setSelected] = useState(null)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [hover, setHover] = useState(null)
  const [scale, setScale] = useState(null)

  const select = useCallback((id) => { setSelected(id); setInspectorOpen(mode !== 'compact'); onSelectionChange?.(id) }, [mode, onSelectionChange])
  const closeInspector = useCallback(() => { setInspectorOpen(false); if (mode !== 'compact') setSelected(null); onSelectionChange?.(null) }, [mode, onSelectionChange])
  const side = inspectorOpen && selected && mode !== 'compact'
  const sheet = inspectorOpen && selected && mode === 'compact'

  return (
    <div ref={display.containerRef} className="office-pixel" data-theme={office.theme} data-mode={mode}>
      <div className="shell">
        <div className="stage-wrap">
          <PixelOffice state={{ ...office, selectedAgent: selected, hoverAgent: hover }} onHover={setHover} onSelect={select} onScale={setScale} />
          <StatusBar agents={office.agents} selected={selected} onSelect={select} connection={connection} />
          <ViewControls popout={popout} fullscreen={display.fullscreen} canFullscreen={display.canFullscreen} onFullscreen={display.toggleFullscreen} scale={scale} url={liveUrl} />
          {mode === 'compact' && selected && !inspectorOpen && <CompactCard snapshot={snaps[selected]} onInspect={() => setInspectorOpen(true)} onClose={() => setSelected(null)} />}
        </div>
        {side && <AgentInspector variant="side" width={display.inspectorWidth} snapshot={snaps[selected]} onClose={closeInspector} />}
      </div>
      {sheet && <AgentInspector variant="sheet" snapshot={snaps[selected]} onClose={closeInspector} />}
      {!backend && <DevPanel state={office} dispatch={dispatch} selected={selected} setSelected={(id) => (id ? select(id) : setSelected(null))} />}
    </div>
  )
}

function DemoOffice() {
  const popout = isPopoutRoute()
  const { office, snaps, dispatch, connection } = useOfficeController({ popout })
  return <OfficeShell office={office} snaps={snaps} dispatch={dispatch} connection={connection} popout={popout} backend={false} />
}

function LiveOffice({ projectId, runId, cursor, connection, runState }) {
  const popout = isPopoutRoute()
  const [inspection, setInspection] = useState(null)
  const [popupConnection, setPopupConnection] = useState('connecting')
  const [selectedAgent, setSelectedAgent] = useState(null)
  const latestCursor = useRef(0)
  const latestRequest = useRef(0)
  const refresh = useCallback(async () => {
    if (!runId) return
    const request = ++latestRequest.current
    const value = await getInspection(projectId, runId, true)
    if (request === latestRequest.current) setInspection(value)
  }, [projectId, runId])

  // The Office follows committed run state. A selected Inspector also follows
  // every cursor so its trace stays current without polling every closed tab.
  useEffect(() => {
    if (cursor == null) return
    let active = true
    const timer = setTimeout(() => {
      void getInspection(projectId, runId, true).then((value) => { if (active) setInspection(value) })
        .catch(() => { if (active) setInspection(null) })
    }, 200)
    return () => { active = false; clearTimeout(timer) }
  }, [projectId, runId, runState, selectedAgent ? cursor : null])
  useEffect(() => {
    if (cursor != null) return
    let active = true, stream, timer
    const schedule = () => {
      clearTimeout(timer)
      timer = setTimeout(() => { void refresh().catch(() => {
        if (active) setPopupConnection('disconnected')
      }) }, 200)
    }
    void getSnapshot(projectId).then((snapshot) => {
      if (!active) return
      latestCursor.current = snapshot.event_cursor
      void refresh().catch(() => { if (active) setPopupConnection('disconnected') })
      stream = new EventSource(`/api/backend/projects/${encodeURIComponent(projectId)}/events?after=${snapshot.event_cursor}`)
      stream.addEventListener('domain', (message) => {
        const sequence = Number(message.lastEventId)
        if (!Number.isSafeInteger(sequence) || sequence <= latestCursor.current) return
        latestCursor.current = sequence
        schedule()
      })
      stream.onopen = () => { if (active) setPopupConnection('live') }
      stream.onerror = () => { if (active) setPopupConnection('disconnected') }
    }).catch(() => { if (active) setPopupConnection('disconnected') })
    return () => { active = false; clearTimeout(timer); stream?.close(); latestRequest.current++ }
  }, [projectId, cursor, refresh])

  const office = { theme: 'day', reducedMotion: false,
    agents: Object.fromEntries(ROLES.map((kind) => [kind,
      { pose: inspection?.office_poses?.[kind] || 'idle' }])) }
  const snaps = Object.fromEntries(ROLES.map((kind) => [kind,
    inspection?.agent_debug?.[kind] || emptySnaps[kind]]))
  const liveUrl = `/office-pixel?project=${encodeURIComponent(projectId)}&run=${encodeURIComponent(runId)}#/popout`
  const state = cursor == null ? popupConnection : connection === 'connected' ? 'live' : 'disconnected'
  return <OfficeShell office={office} snaps={snaps} connection={state} popout={popout} liveUrl={liveUrl} backend onSelectionChange={setSelectedAgent} />
}

export default function OfficeExperienceView({ projectId, runId, cursor, connection, runState }) {
  const params = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search)
  const liveProject = projectId || params?.get('project')
  const liveRun = runId || params?.get('run')
  if (liveProject && liveRun) {
    return <LiveOffice projectId={liveProject} runId={liveRun} cursor={cursor} connection={connection} runState={runState} />
  }
  return <DemoOffice />
}
