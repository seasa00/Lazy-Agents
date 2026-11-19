import { initialOfficeState } from './mockOfficeState.js'

// The ONE office state (theme, reduced motion, agent poses). Windows never keep their own copy of this:
// the authority window owns it; pop-outs mirror it and send actions back (see src/sync).
export const initOffice = () => ({
  ...initialOfficeState,
  reducedMotion: typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches,
})

export function officeReducer(state, a) {
  switch (a.type) {
    case 'theme': return { ...state, theme: a.value }
    case 'reducedMotion': return { ...state, reducedMotion: !!a.value }
    case 'pose': return { ...state, agents: { ...state.agents, [a.agent]: { pose: a.pose } } }
    case 'preset': return { ...state, agents: { manager: { pose: a.preset.manager }, developer: { pose: a.preset.developer }, reviewer: { pose: a.preset.reviewer } } }
    default: return state
  }
}
