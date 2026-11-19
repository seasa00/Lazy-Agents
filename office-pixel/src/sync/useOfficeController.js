import { useEffect, useReducer, useRef, useState } from 'react'
import { initOffice, officeReducer } from '../state/officeReducer.js'
import { useAgentDebug } from '../debug/useAgentDebug.js'
import { openChannel } from './officeSync.js'

/**
 * Single source of office state for this window.
 *  - main window  = authority: owns the state (+ mock debug adapter) and broadcasts it
 *  - pop-out      = mirror: receives the state, sends actions back. If no authority answers, it becomes standalone.
 * connection: 'live' | 'standalone' | 'connecting' | 'disconnected'
 */
export function useOfficeController({ popout }) {
  const [office, dispatchLocal] = useReducer(officeReducer, undefined, initOffice)
  const localSnaps = useAgentDebug(office.agents)
  const [role, setRole] = useState(popout ? 'pending' : 'authority')
  const [remote, setRemote] = useState(null)
  const [connection, setConnection] = useState(popout ? 'connecting' : 'live')
  const chRef = useRef(null), roleRef = useRef(role), lastSeen = useRef(0)
  const latest = useRef({ office, snaps: localSnaps })
  roleRef.current = role; latest.current = { office, snaps: localSnaps }

  useEffect(() => {
    const ch = openChannel((m) => {
      if (roleRef.current === 'authority') {
        if (m.t === 'hello') chRef.current.post({ t: 'state', ...latest.current })
        else if (m.t === 'action') dispatchLocal(m.action)
      } else if (m.t === 'state') { setRemote({ office: m.office, snaps: m.snaps }); lastSeen.current = Date.now(); setRole('mirror'); setConnection('live') }
      else if (m.t === 'beat') { lastSeen.current = Date.now(); setConnection('live') }
    })
    chRef.current = ch
    let timer
    if (popout) {
      ch.post({ t: 'hello' })
      timer = setTimeout(() => { if (roleRef.current === 'pending') { setRole('authority'); setConnection('standalone') } }, 900)
    }
    const beat = setInterval(() => { if (roleRef.current === 'authority') ch.post({ t: 'beat' }); else if (roleRef.current === 'mirror' && Date.now() - lastSeen.current > 5000) setConnection('disconnected') }, 1500)
    return () => { clearTimeout(timer); clearInterval(beat); ch.close() }
  }, [popout])

  // authority: broadcast every change
  useEffect(() => { if (role === 'authority') chRef.current?.post({ t: 'state', office, snaps: localSnaps }) }, [role, office, localSnaps])

  const mirror = role === 'mirror' && remote
  const dispatch = role === 'mirror' ? (action) => chRef.current?.post({ t: 'action', action }) : dispatchLocal
  return { office: mirror ? remote.office : office, snaps: mirror ? remote.snaps : localSnaps, dispatch, connection, role }
}
