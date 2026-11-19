import { Px, K, D, M, P, H, G, S, S2, R2, A1, A2, A3, OL, FONT, P3, OX, OY, W, H_, chk, dot, flatc } from './engine.js'
import { drawFigure, bubble } from './sprites.js'
import { screenFor } from './screens.js'

// ---- hit regions (scene-buffer px). Rebuilt every frame; consumed by PixelOffice for hover/click. ----
export const HIT = { manager: null, developer: null, reviewer: null }
const bbox = (pts) => { const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]); const x = Math.min(...xs), y = Math.min(...ys); return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y } }
const deskRect = (x0, y0, x1, y1) => bbox([P3(x0, y0, 34), P3(x1, y0, 34), P3(x1, y1, 0), P3(x0, y1, 0)])
const charRect = (cx, cy) => { const [ax, ay] = P3(cx, cy, 7); return { x: ax - 18, y: ay - 30, w: 36, h: 40 } }
const ACCENT_IDX = { manager: A1, developer: A2, reviewer: A3 }
// selection / hover marker: corner brackets around the character + a bobbing arrow (selected only)
function selectionMarker(px, id, mode, f, live) {
  const r = HIT[id]?.char
  if (!r) return
  const c = mode === 'selected' ? ACCENT_IDX[id] : M, t = mode === 'selected' ? 2 : 1, L = 6
  const x0 = r.x, y0 = r.y, x1 = r.x + r.w - 1, y1 = r.y + r.h - 1
  for (let i = 0; i < L; i++) for (let k = 0; k < t; k++) {
    px.set(x0 + i, y0 + k, c); px.set(x0 + k, y0 + i, c); px.set(x1 - i, y0 + k, c); px.set(x1 - k, y0 + i, c)
    px.set(x0 + i, y1 - k, c); px.set(x0 + k, y1 - i, c); px.set(x1 - i, y1 - k, c); px.set(x1 - k, y1 - i, c)
  }
  if (mode === 'selected') { // arrow above head
    const bob = live ? ((f >> 2) & 1) : 0, ax = r.x + (r.w >> 1), ay = r.y - 9 + bob
    for (let j = 0; j < 4; j++) for (let i = -3 + j; i <= 3 - j; i++) px.set(ax + i, ay + j, c)
    for (let i = -4; i <= 4; i++) px.set(ax + i, ay - 1, K)
  }
}

let NIGHT = false // set per frame; used to mute accents in the cyber palette so the focal point stays clear
const acc = (c, dim = M) => (NIGHT ? dim : c)
const ZD = 12 // desk surface height (px)
const ZS = 7 // seat height

function ellipse(px, cx, cy, rx, ry, fill, line = OL) {
  for (let y = -ry; y <= ry; y++) for (let x = -rx; x <= rx; x++) {
    const d = (x * x) / (rx * rx) + (y * y) / (ry * ry)
    if (d <= 1) px.set(cx + x, cy + y, typeof fill === 'function' ? fill(cx + x, cy + y) : fill)
  }
  if (line !== null) for (let a = 0; a < 720; a++) { const t = (a / 720) * Math.PI * 2; px.set(Math.round(cx + Math.cos(t) * rx), Math.round(cy + Math.sin(t) * ry), line) }
}
function cylinder(px, cx, cy, rx, ry, h, top, side) {
  for (let x = -rx; x <= rx; x++) for (let y = 0; y <= h; y++) px.set(cx + x, cy + y, typeof side === 'function' ? side(cx + x, cy + y) : side)
  for (let y = 0; y <= h; y++) { px.set(cx - rx, cy + y, OL); px.set(cx + rx, cy + y, OL) }
  for (let x = -rx; x <= rx; x++) px.set(cx + x, cy + h + Math.round(ry * Math.sqrt(Math.max(0, 1 - (x * x) / (rx * rx)))), OL)
  ellipse(px, cx, cy, rx, ry, top, OL)
}

// ---------- CRT monitor (the hero prop) ----------
// facing 'y' => screen on the +y face (lower-left), facing 'x' => screen on the +x face (lower-right)
function crt(px, x, y, z, facing, w, h, screen, body = P) {
  const iw = Math.round(w * 8)
  const face = (c, v, fw, fh) => {
    if (c >= 1 && c < fw - 1 && v >= 3 && v < fh - 1) return screen(c - 1, v - 3, fw - 2, fh - 4)
    if (v === 1 && c > fw - 5 && c < fw - 2) return H
    return body
  }
  const dark = D
  if (facing === 'y') {
    px.box(x + 0.2, y, z + 2, w - 0.4, 0.62, h - 4, { t: M, l: body, r: dark })
    px.box(x, y + 0.62, z, w, 0.4, h, { t: body, l: face, r: dark })
  } else {
    px.box(x, y + 0.2, z + 2, 0.62, w - 0.4, h - 4, { t: M, l: body, r: dark })
    px.box(x + 0.62, y, z, 0.4, w, h, { t: body, l: dark, r: face })
  }
  void iw
}

function desk(px, x, y, dx, dy, style) {
  const s = {
    dev: { t: D, l: K, r: K, trim: acc(H, M) },
    mgr: { t: P, l: M, r: D, trim: H },
    rev: { t: P, l: M, r: D, trim: acc(H, M) },
  }[style]
  // legs / panel
  for (const [lx, ly] of [[x + 0.1, y + 0.1], [x + dx - 0.4, y + 0.1], [x + 0.1, y + dy - 0.4], [x + dx - 0.4, y + dy - 0.4]]) px.box(lx, ly, 0, 0.3, 0.3, ZD - 2, { t: M, l: D, r: K })
  px.box(x, y, ZD - 2, dx, dy, 2, { t: s.t, l: s.l, r: s.r })
  // desk lip accent line along the front edge
  px.faceL(x, y + dy, ZD - 2, dx, 1, () => s.trim)
  px.faceR(x + dx, y, ZD - 2, dy, 1, () => s.trim)
}

function chair(px, cx, cy, back, col) {
  px.box(cx - 0.12, cy - 0.12, 0, 0.24, 0.24, ZS - 2, { t: K, l: K, r: K })
  px.box(cx - 0.5, cy - 0.5, 0, 1.0, 1.0, 1, { t: K, l: K, r: K })
  px.box(cx - 0.55, cy - 0.55, ZS - 3, 1.1, 1.1, 3, { t: col, l: M, r: D })
  return () => { // backrest drawn after the character (it sits closer to the camera)
    if (back === '+x') px.box(cx + 0.4, cy - 0.5, ZS, 0.2, 1.0, 3, { t: col, l: M, r: D })
    else px.box(cx - 0.5, cy + 0.4, ZS, 1.0, 0.2, 3, { t: col, l: M, r: D })
  }
}

// tiny desk nameplate (the only role label left: subtle, part of the desk)
function plate(px, x, y, txt, face) {
  const fn = (c, v, w, h) => {
    if (c === 0 || v === 0 || c === w - 1 || v === h - 1) return K
    const col = c - 1, row = h - 2 - v, i = Math.floor(col / 4), g = FONT[txt[i]]
    return g && col % 4 < 3 && row >= 0 && row < 5 && g[row][col % 4] === '#' ? K : P
  }
  if (face === 'y') px.box(x, y, ZD, 1.6, 0.18, 7, { t: P, l: fn, r: D })
  else px.box(x, y, ZD, 0.18, 1.6, 7, { t: P, l: D, r: fn })
}
function mug(px, x, y, z, c = H) { px.box(x, y, z, 0.3, 0.3, 3, { t: K, l: c, r: D }) }
function paper(px, x, y, z, dx = 0.6, dy = 0.5) { px.box(x, y, z, dx, dy, 1, { t: P, l: M, r: M }) }
function keyboard(px, x, y, z, dx, dy) { px.box(x, y, z, dx, dy, 1, { t: (a, b) => (((a >> 1) + b) & 1 ? P : M), l: D, r: K }) }
function plant(px, x, y, f, scale = 1, live = true, z = 0) {
  const [sx, sy0] = P3(x, y, z), sy = sy0 - 8 * scale
  const sway = live ? ((f >> 3) & 1) : 0
  cylinder(px, sx, sy, Math.round(5 * scale), 2, Math.round(8 * scale), acc(H, D), chk(acc(H, D), K))
  const top = sy - 1
  const blades = [[-9, 13], [-5, 18], [-1, 22], [3, 19], [8, 14], [5, 10]]
  for (const [dx, len] of blades) {
    const L = Math.round(len * scale), tx = sx + Math.round(dx * scale * 0.7) + (dx > 0 ? sway : 0)
    for (const o of [-1, 1]) px.line(sx + o, top, tx + o, top - L, K)
    px.line(sx, top, tx, top - L, D); px.line(sx + 1, top, tx + 1, top - L, M)
    if (!NIGHT) px.set(tx, top - L, G)
  }
}
function cabinet(px, x, y) {
  px.box(x, y, 0, 1.1, 2.4, 15, {
    t: P, l: (c, v, w, h) => (v === 0 || v === h - 1 ? K : M),
    r: (c, v, w, h) => (v % 5 === 0 || c === 0 || c === w - 1 ? K : (c > 4 && c < 9 && v % 5 === 2) || (c > w - 10 && c < w - 5 && v % 5 === 2) ? acc(H, M) : S2),
  })
}
function pouf(px, x, y, c) { const [sx, sy] = P3(x, y, 0); cylinder(px, sx, sy - 6, 6, 3, 6, c, chk(c, D)) }

function cat(px, x, y, z, f, live) {
  const [sx, sy] = P3(x, y, z)
  ellipse(px, sx, sy - 3, 7, 4, P, K) // body loaf
  ellipse(px, sx + 6, sy - 4, 4, 3, P, K) // head
  px.set(sx + 5, sy - 8, K); px.set(sx + 9, sy - 8, K); px.set(sx + 5, sy - 7, P); px.set(sx + 9, sy - 7, P) // ears
  px.rect(sx - 3, sy - 6, 2, 2, H); px.rect(sx + 1, sy - 2, 3, 2, M) // patches
  px.line(sx - 7, sy - 2, sx - 11, sy - ((f >> 3) & 1 && live ? 5 : 3), K) // tail
  px.set(sx + 7, sy - 4, K); px.set(sx + 9, sy - 4, K)
  if (live) { const k = (f >> 2) % 4; px.text('z', sx + 8, sy - 12 - k, K); if (k > 1) px.text('z', sx + 12, sy - 16 - k, K) }
}

// ---------- room ----------
function room(px, theme) {
  const night = theme === 'night'
  const rim = night ? G : P
  // floor slab + floor (cream boards, tan grid every 2 tiles)
  px.box(0, 0, -6, 12, 12, 6, {
    t: (x, y) => {
      const u = (x - OX) / 8, v = (y - OY) / 4, wx = (u + v) / 2, wy = (v - u) / 2
      const fx = wx / 2 - Math.floor(wx / 2), fy = wy / 2 - Math.floor(wy / 2)
      return fx < 0.045 || fy < 0.09 ? S2 : S
    },
    l: (c, v) => (v < 2 ? K : S2), r: (c, v) => (v < 2 ? K : D),
  })
  // back wall (lit): cream panels, orange wainscot
  const wallBack = (c, v, w, h) => {
    if (night && v < 1) return G
    if (v === 13) return K
    if (v < 13) return v === 12 ? D : H
    if (v === h - 1) return K
    return c % 32 === 0 ? S2 : S
  }
  // left wall (in shade): tan panels, dark wainscot
  const wallLeft = (c, v, w, h) => {
    if (night && v < 1) return M
    if (v === 13) return K
    if (v < 13) return v === 12 ? K : D
    if (v === h - 1) return K
    return c % 32 === 0 ? K : S2
  }
  px.box(-0.5, -0.5, 0, 12.5, 0.5, 52, { t: rim, l: wallBack, r: D })
  px.box(-0.5, 0, 0, 0.5, 12, 52, { t: rim, l: D, r: wallLeft })
  void theme
}

function rugs(px, theme) {
  const night = theme === 'night'
  // manager: cream with orange stripes
  px.flat(2.0, 0.4, 7.3, 3.9, (x, y) => (Math.floor(y * 2) % 2 ? S : (x < 2.6 || x > 6.9 ? H : S)))
  // developer: tan with dark border
  px.flat(0.4, 3.2, 3.9, 8.4, (x, y) => (x < 0.7 || x > 3.6 || y < 3.5 || y > 8.1 ? (night ? M : D) : S2))
  // reviewer: cream with orange border
  px.flat(7.6, 0.4, 11.8, 3.9, (x, y) => (x < 7.9 || x > 11.5 || y < 0.7 || y > 3.6 ? (night ? (Math.floor((x + y) * 3) & 1 ? M : K) : H) : S))
  // shared round rug
  const [cx, cy] = P3(6.4, 8.0, 0)
  ellipse(px, cx, cy, 30, 15, (x, y) => { const d = Math.hypot((x - cx) / 30, (y - cy) / 15); return d > 0.84 ? (night ? M : H) : d > 0.66 ? (night ? S : P) : d > 0.5 ? M : (night ? S : P) }, K)
}

function windowOnLeftWall(px, theme, f) {
  const night = theme === 'night'
  const y0 = 0.7, w = 2.6, z0 = 22, h = 24
  px.faceR(0, y0, z0, w, h, (c, v, fw, fh) => {
    if (c < 2 || v < 2 || c >= fw - 2 || v >= fh - 2) return K
    if (c === 3 || (fh - 1 - v) === 2 + 0 || c === fw - 4 || v === fh - 4) return P
    if (c > fw / 2 - 1 && c < fw / 2 + 1) return P
    if (v === (fh >> 1)) return P
    if (night) {
      const hb = 5 + ((c >> 2) * 5 % 11)
      if (v < hb) { if (v === hb - 1) return c % 6 ? K : G; return c % 4 === 1 && v % 3 === 1 && ((c >> 2) * 3 + (v >> 2)) % 4 === 0 ? (((c >> 2) % 2) ? M : G) : K }
      return (c * 2 + v * 5 + f * 3) % 21 === 0 ? M : D
    }
    return ((c * 5 + v * 3) % 17 === 0) ? P : M
  })
}

function boardOnBackWall(px, f) {
  px.faceL(2.5, 0, 20, 4.4, 28, (c, v, w, h) => {
    if (c === 0 || v === 0 || c === w - 1 || v === h - 1) return K
    if (c === 1 || v === 1 || c === w - 2 || v === h - 2) return D
    if (v > h - 7) { const seg = Math.floor(c / (w / 3)); return v === h - 3 || (c % 10 === 9) ? -1 === 1 ? K : (seg === 0 ? H : seg === 1 ? K : D) : P }
    const lane = Math.floor((c - 2) / ((w - 4) / 3)), lc = (c - 2) % Math.floor((w - 4) / 3)
    if (lc === 0) return M
    const card = [3, 2, 2][lane] ?? 0
    for (let i = 0; i < card; i++) { const y0 = 3 + i * 5; if (v >= y0 && v < y0 + 4 && lc > 1 && lc < 9) return i === 0 ? (lane === 1 ? H : G) : i === 1 ? M : P }
    return P
  })
}

function frameOn(px, plane, a, b, z, w, h, fn) {
  if (plane === 'back') px.faceL(a, 0, z, w, h, fn); else px.faceR(0, b, z, w, h, fn)
}
const art = (c, v, w, h) => (c < 1 || v < 1 || c >= w - 1 || v >= h - 1 ? K : Math.hypot(c - w / 2, v - h / 2) < 3 ? H : P)

function sign(px, theme, f) {
  const night = theme === 'night', txt = 'agents'
  const bit = (c, v, ox, oy) => { const col = c - ox, row = 8 - v - oy, i = Math.floor(col / 4), g = FONT[txt[i]]; return g && col >= 0 && col % 4 < 3 && row >= 0 && row < 5 && g[row][col % 4] === '#' }
  px.faceL(8.0, 0, 33, 3.4, 11, (c, v, w, h) => {
    if (c === 0 || v === 0 || c === w - 1 || v === h - 1) return night ? M : K
    if (bit(c, v, 2, 1)) return night ? G : K
    if (v === 2 && c > 1 && c < w - 2) return night ? D : H
    return night ? K : P
  })
}
function shelfBack(px, x, z) {
  px.box(x, 0, z, 3, 0.9, 2, { t: P, l: D, r: K })
  const books = [H, D, P, M, H, D, M]
  books.forEach((c, i) => px.box(x + 0.2 + i * 0.28, 0.15, z + 2, 0.22, 0.5, 7 + (i % 3) * 2, { t: P, l: c, r: K }))
  px.box(x + 2.4, 0.2, z + 2, 0.4, 0.4, 5, { t: M, l: H, r: D })
}
function shelfLeft(px, y, z) {
  px.box(0, y, z, 0.9, 3, 2, { t: P, l: D, r: K })
  ;[D, H, P, M, H, K].forEach((c, i) => px.box(0.15, y + 0.2 + i * 0.28, z + 2, 0.5, 0.22, 7 + (i % 3) * 2, { t: P, l: K, r: c }))
  // little robot figurine
  px.box(0.2, y + 2.1, z + 2, 0.5, 0.5, 5, { t: P, l: M, r: H })
}

// ---------- stations ----------
function crtScreenFn(role, pose, f, live) { const fn = screenFor(role, pose, f, live); return (c, v, w, h) => fn(c, v, w, h, live ? f : 0) }

function stringLights(px, f, live, theme) {
  const n = 14
  for (let i = 0; i < n; i++) {
    const y = 3.4 + (i / (n - 1)) * 5.4, z = 47 - Math.sin((i / (n - 1)) * Math.PI) * 3
    const [sx, sy] = P3(0.1, y, z)
    px.set(sx, sy, K)
    const on = theme === 'night' || (i + (live ? f >> 3 : 0)) % 3 !== 0
    px.set(sx, sy + 1, on ? (NIGHT ? M : (i & 1 ? G : H)) : D); px.set(sx, sy + 2, K)
  }
}

export function drawScene(px, state, f, theme) {
  NIGHT = theme === 'night'
  HIT.manager = { char: charRect(4.7, 2.8), desk: deskRect(2.4, 0.3, 6.9, 2.3) }
  HIT.developer = { char: charRect(3.1, 5.6), desk: deskRect(0.3, 3.6, 2.4, 8.2) }
  HIT.reviewer = { char: charRect(9.7, 2.8), desk: deskRect(8.0, 0.3, 11.8, 2.2) }
  const live = !state.reducedMotion
  const pose = { m: state.agents.manager.pose, d: state.agents.developer.pose, r: state.agents.reviewer.pose }

  // (backdrop is drawn by the caller so it can fill the whole screen)
  room(px, theme)
  rugs(px, theme)

  // wall decor
  windowOnLeftWall(px, theme, f)
  boardOnBackWall(px, f)
  sign(px, theme, f)
  shelfBack(px, 8.2, 20)
  shelfLeft(px, 4.2, 38)
  frameOn(px, 'left', 0, 8.4, 24, 1.2, 14, art)
  stringLights(px, f, live, theme)
  // clock
  { const [cx, cy] = P3(7.1, 0.05, 40); ellipse(px, cx, cy, 5, 5, P, K); px.line(cx, cy, cx, cy - 3, K); px.line(cx, cy, cx + 2, cy + 1, H) }

  // ---- depth-sorted floor items ----
  const items = []
  const add = (d, fn) => items.push([d, fn])

  // manager (back wall, faces up-right toward the wall)
  add(6, () => {
    desk(px, 2.4, 0.3, 4.5, 2.0, 'mgr')
    crt(px, 3.3, 0.35, ZD, 'y', 2.3, 18, crtScreenFn('manager', pose.m, f, live))
    keyboard(px, 3.7, 1.6, ZD, 1.3, 0.4)
    // planning kit: standing task cards, tablet with status bars, desk lamp, notes
    for (const [i, c] of [[0, H], [1, G], [2, P]]) px.box(5.75 + i * 0.45, 0.75, ZD, 0.3, 0.1, 6 + i, { t: P, l: c, r: D })
    px.box(5.6, 1.25, ZD, 1.1, 0.12, 8, { t: P, l: (c, v, w, h) => (c === 0 || v === 0 || c === w - 1 || v === h - 1 ? K : v === 2 || v === 4 ? (c < 3 + (v * 3) % 5 ? H : M) : K), r: D })
    px.box(2.55, 0.55, ZD, 0.3, 0.3, 9, { t: K, l: D, r: K }); px.box(2.55, 0.5, ZD + 9, 0.7, 0.5, 3, { t: acc(H, G), l: acc(H, G), r: D }) // desk lamp
    paper(px, 6.25, 1.55, ZD, 0.6, 0.55); mug(px, 3.0, 1.6, ZD, H)
    px.box(2.95, 1.35, ZD, 0.4, 0.4, 3, { t: H, l: H, r: D }) // sticky-note stack
    plate(px, 3.05, 1.84, 'mgr', 'y')
  })
  let back1
  add(7.6, () => {
    back1 = chair(px, 4.7, 2.8, '+y', M)
    drawFigure(px, ...P3(4.7, 2.8, ZS), { role: 'manager', facing: '-y', pose: pose.m, frame: f, live, night: NIGHT })
    back1()
    const [bx, by] = P3(4.7, 2.8, 30)
    const ic = { thinking: 'dots', assigning: 'arrow' }[pose.m]
    if (ic) bubble(px, bx + 6, by - 12 - (live ? (f >> 3) & 1 : 0), ic)
  })

  // developer (left wall, faces up-left)
  add(6.9, () => {
    desk(px, 0.3, 3.6, 2.1, 4.6, 'dev')
    crt(px, 0.5, 3.9, ZD, 'x', 2.0, 15, crtScreenFn('developer', pose.d, f, live))
    crt(px, 0.5, 6.1, ZD, 'x', 2.0, 15, crtScreenFn('developer', pose.d === 'testing' ? 'working' : pose.d === 'working' || pose.d === 'submitting' ? 'idle' : pose.d, f, false))
    keyboard(px, 1.85, 4.9, ZD, 0.45, 1.3)
    mug(px, 1.9, 6.4, ZD, D); mug(px, 1.7, 7.4, ZD, H)
    // little rubber duck
    px.box(1.9, 7.8, ZD, 0.3, 0.3, 3, { t: P, l: P, r: M })
    plate(px, 2.1, 7.0, 'dev', 'x')
  })
  let back2
  add(9.0, () => {
    back2 = chair(px, 3.1, 5.6, '+x', M)
    drawFigure(px, ...P3(3.1, 5.6, ZS), { role: 'developer', facing: '-x', pose: pose.d, frame: f, live, night: NIGHT })
    back2()
    const [bx, by] = P3(3.1, 5.6, 30)
    const ic = { receiving: 'bang', testing: 'dots', submitting: 'up', blocked: 'cross' }[pose.d]
    if (ic) bubble(px, bx - 16, by - 12 - (live ? (f >> 3) & 1 : 0), ic, pose.d === 'blocked' && live && (f >> 2) & 1 ? H : K)
  })

  // reviewer (back wall, right)
  add(11.4, () => {
    desk(px, 8.0, 0.3, 3.8, 1.9, 'rev')
    crt(px, 8.8, 0.35, ZD, 'y', 1.9, 15, crtScreenFn('reviewer', pose.r, f, live))
    keyboard(px, 9.0, 1.55, ZD, 1.1, 0.4)
    // checklist clipboard + stamp + tray of papers + magnifier
    px.box(10.6, 0.9, ZD, 0.6, 0.8, 1, { t: (a, b) => (b % 3 === 0 ? H : P), l: D, r: K })
    px.box(8.2, 0.6, ZD, 0.6, 0.6, 2, { t: P, l: M, r: D }); px.box(8.2, 0.6, ZD + 2, 0.6, 0.6, 2, { t: P, l: M, r: D }); px.box(8.2, 0.6, ZD + 4, 0.6, 0.6, 2, { t: P, l: M, r: D })
    px.box(11.0, 1.7, ZD, 0.35, 0.35, 4, { t: H, l: H, r: D }) // stamp
    plate(px, 8.25, 1.82, 'rev', 'y')
  })
  let back3
  add(12.6, () => {
    back3 = chair(px, 9.7, 2.8, '+y', M)
    drawFigure(px, ...P3(9.7, 2.8, ZS), { role: 'reviewer', facing: '-y', pose: pose.r, frame: f, live, night: NIGHT })
    back3()
    const [bx, by] = P3(9.7, 2.8, 30)
    const ic = { receiving: 'bang', reviewing: 'ask', pass: 'check', fail: 'cross' }[pose.r]
    if (ic) bubble(px, bx + 6, by - 12 - (live ? (f >> 3) & 1 : 0), ic, pose.r === 'pass' ? H : K)
  })
  add(8.3, () => { px.box(-0.0, 2.2, 0, 0.5, 0.5, 1, { t: K, l: K, r: K }) })

  // furniture & plants
  add(5, () => plant(px, 1.5, 1.3, f, 1.0, live))
  add(7.4, () => plant(px, 7.5, 1.0, f + 4, 0.9, live))
  add(14, () => {
    const [tx, ty] = P3(6.4, 8.0, 0)
    cylinder(px, tx, ty - 11, 10, 5, 11, P, M)
    px.box(5.7, 7.6, 11, 0.35, 0.35, 3, { t: K, l: H, r: D }); px.box(7.0, 8.4, 11, 0.35, 0.35, 3, { t: K, l: M, r: D })
    cat(px, 6.45, 8.0, 11, f, live)
  })
  add(16, () => pouf(px, 3.2, 9.6, acc(H, D)))
  add(16.5, () => pouf(px, 9.6, 8.6, D))
  add(17, () => { cabinet(px, 0.4, 9.2); plant(px, 0.95, 10.0, f + 2, 0.55, live, 15) })
  add(15, () => { // floor lamp
    const [lx, ly] = P3(10.8, 5.2, 0)
    px.rect(lx, ly - 34, 1, 34, K); ellipse(px, lx, ly - 36, 5, 3, P, K); px.rect(lx - 4, ly - 36, 9, 2, P)
    if (theme === 'night') for (let i = 0; i < 14; i++) { const a = i * 2.4; px.set(Math.round(lx + Math.cos(a) * (6 + i % 7)), Math.round(ly - 30 + Math.sin(a) * (4 + i % 5)), M) }
    cylinder(px, lx, ly - 2, 4, 2, 2, D, K)
  })

  items.sort((a, b) => a[0] - b[0]).forEach(([, fn]) => fn())
  items.length = 0
  for (const id of ['manager', 'developer', 'reviewer']) {
    if (state.selectedAgent === id) selectionMarker(px, id, 'selected', f, live)
    else if (state.hoverAgent === id) selectionMarker(px, id, 'hover', f, live)
  }

}
