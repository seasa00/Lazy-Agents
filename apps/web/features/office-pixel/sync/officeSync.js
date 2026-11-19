// Prototype transport for "same office state in several windows": BroadcastChannel (same-origin windows).
// A production source (Lazy Agents backend / SSE) replaces this module: it only has to deliver
//   { t:'state', office, snaps }  — current office state + AgentDebugSnapshots
//   { t:'beat' }                  — liveness heartbeat
// and accept   { t:'action', action }  from viewers. Nothing else in the UI knows about the transport.
export const CHANNEL = 'lazy-agents-office-pixel-mock-v1'

export function openChannel(onMessage) {
  if (typeof BroadcastChannel === 'undefined') return { supported: false, post() {}, close() {} }
  const ch = new BroadcastChannel(CHANNEL)
  ch.onmessage = (e) => onMessage(e.data)
  return { supported: true, post: (m) => ch.postMessage(m), close: () => ch.close() }
}

export const isPopoutRoute = () => typeof location !== 'undefined' && location.hash.startsWith('#/popout')
export const popoutUrl = () => `${location.origin === 'null' ? location.href.split('#')[0] : location.origin + '/office-pixel'}#/popout`
