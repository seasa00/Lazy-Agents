import { K, D, M, P, H, G, ICON } from './engine.js'

// Each fn(c, v, w, h, t) -> palette index, drawn inside the CRT's screen area (c = column, v = row from bottom).
const base = (c, v, w, h) => (c === 0 || v === 0 || c === w - 1 || v === h - 1 ? D : K) // inset glass edge

function icon(rows, ox, oy, col) {
  return (c, v, w, h) => {
    const i = c - ox, j = h - 1 - v - oy
    return rows[j] && rows[j][i] === '#' ? col : -1
  }
}
const over = (...fns) => (c, v, w, h, t) => { for (const f of fns) { const r = f(c, v, w, h, t); if (r !== -1 && r !== undefined) return r } return K }

export function screenFor(role, pose, frame, live) {
  const t = live ? frame : 0
  if (pose === 'blocked') return over((c, v, w, h) => (c > 1 && c < w - 2 && v > 1 && v < h - 2 && ((c + v + (t >> 1)) & 3) === 0 ? H : -1), icon(ICON.cross, 3, 1, H), base)
  if (role === 'developer' && pose === 'testing') {
    return (c, v, w, h) => {
      if (c === 0 || v === 0 || c === w - 1 || v === h - 1) return D
      const row = Math.floor((h - 2 - v) / 2), y = (h - 2 - v) % 2
      if (y === 1 || row > 4) return K
      const done = ((t >> 1) % 7) + 1
      if (c < 3) return row < done ? G : D
      return c < 3 + 2 + ((row * 5) % 7) ? P : K
    }
  }
  if (role === 'developer' && (pose === 'working' || pose === 'submitting')) {
    return (c, v, w, h) => {
      if (c === 0 || v === 0 || c === w - 1 || v === h - 1) return D
      const row = (h - 2 - v + (t >> 1)) % 6
      if (row === 5) return K
      const len = 2 + ((row * 7 + (h - v + (t >> 1) >> 2) * 3) % 5) * 1.4
      const ind = row % 3 === 1 ? 2 : 0
      return c >= 2 + ind && c < 2 + ind + len ? (row % 2 ? G : P) : K
    }
  }
  if (pose === 'submitting') return over(icon(ICON.up, 3, 1, G), base)
  if (role === 'manager' && (pose === 'thinking' || pose === 'assigning')) {
    return (c, v, w, h) => {
      if (c === 0 || v === 0 || c === w - 1 || v === h - 1) return D
      const col = Math.floor((c - 1) / 4)
      if ((c - 1) % 4 === 3) return K
      const card = [3, 2, 1][col] ?? 0
      const moving = pose === 'assigning' && col === 1 && (t >> 1) % 2
      if (v > h - 4) return col === 0 ? H : col === 1 ? G : P
      for (let i = 0; i < card; i++) if (v > 1 + i * 3 && v <= 3 + i * 3) return moving && i === 0 ? H : P
      return K
    }
  }
  if (role === 'reviewer' && (pose === 'reviewing' || pose === 'pass' || pose === 'fail' || pose === 'receiving')) {
    if (pose === 'pass') return over(icon(ICON.check, 3, 1, G), base)
    if (pose === 'fail') return over(icon(ICON.cross, 3, 1, H), base)
    return (c, v, w, h) => {
      if (c === 0 || v === 0 || c === w - 1 || v === h - 1) return D
      const row = Math.floor((h - 2 - v) / 3)
      const y = (h - 2 - v) % 3
      if (row > 2 || y === 2) return K
      const shown = pose === 'reviewing' ? (t >> 2) % 4 : 3
      if (c < 4) return row < shown ? (row === 1 ? H : G) : D
      return c < 4 + 3 + ((row * 5) % 4) * 1.6 ? P : K
    }
  }
  if (pose === 'receiving') return over(icon(ICON.bang, 3, 1, G), base)
  // idle: the little smiley from the reference
  return over(icon(ICON.smile, 3, 1, role === 'developer' ? G : H), base)
}
