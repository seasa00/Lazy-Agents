import { useCallback, useEffect, useState } from 'react'
import PixelOffice from './pixel/PixelOffice.jsx'
import DevPanel from './ui/DevPanel.jsx'
import { StatusBar, ViewControls, CompactCard } from './ui/Chrome.jsx'
import AgentInspector from './inspector/AgentInspector.jsx'
import { useOfficeController } from './sync/useOfficeController.js'
import { isPopoutRoute } from './sync/officeSync.js'
import { useDisplay } from './layout/useDisplay.js'

export default function OfficeExperienceView() {
  const popout = isPopoutRoute()
  const { office, snaps, dispatch, connection } = useOfficeController({ popout })
  const display = useDisplay()
  const { mode } = display
  const [selected, setSelected] = useState(null)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [hover, setHover] = useState(null)
  const [scale, setScale] = useState(null)

  const select = useCallback((id) => { setSelected(id); setInspectorOpen(mode !== 'compact') }, [mode])
  const closeInspector = useCallback(() => { setInspectorOpen(false); if (mode !== 'compact') setSelected(null) }, [mode])
  const side = inspectorOpen && selected && mode !== 'compact'
  const sheet = inspectorOpen && selected && mode === 'compact'

  return (
    <div ref={display.containerRef} className="office-pixel" data-theme={office.theme} data-mode={mode}>
      <div className="shell">
        <div className="stage-wrap">
          <PixelOffice state={{ ...office, selectedAgent: selected, hoverAgent: hover }} onHover={setHover} onSelect={select} onScale={setScale} />
          <StatusBar agents={office.agents} selected={selected} onSelect={select} connection={connection} />
          <ViewControls popout={popout} fullscreen={display.fullscreen} canFullscreen={display.canFullscreen} onFullscreen={display.toggleFullscreen} scale={scale} />
          {mode === 'compact' && selected && !inspectorOpen && <CompactCard snapshot={snaps[selected]} onInspect={() => setInspectorOpen(true)} onClose={() => setSelected(null)} />}
        </div>
        {side && <AgentInspector variant="side" width={display.inspectorWidth} snapshot={snaps[selected]} onClose={closeInspector} />}
      </div>
      {sheet && <AgentInspector variant="sheet" snapshot={snaps[selected]} onClose={closeInspector} />}
      <DevPanel state={office} dispatch={dispatch} selected={selected} setSelected={(id) => (id ? select(id) : setSelected(null))} />
    </div>
  )
}
