import { Px, K, D, M, P, H, G, R2, A1, A2, A3, ICON } from './engine.js'

// ---------------------------------------------------------------------------
// One shared seated base body (~27px tall incl. seat height). Built in the room's
// 2:1 isometric language: thighs/arms run along 2:1 slopes toward the desk.
// Sprite faces UP-LEFT (toward -x); mirrored for the up-right desks (toward -y).
// Roles differ only by silhouette: hair shape, headphones / clipboard / glasses+checklist.
// ---------------------------------------------------------------------------
export const SW = 36, SH = 34, HX = 18, HY = 24 // sprite size, hip anchor inside the sprite
const sp = new Px(SW, SH)

const LOOK = {
  manager: { hair: D, hi: M, shirt: P, shade: M, pants: D, pshade: K, shoe: D },
  developer: { hair: K, hi: D, shirt: H, shade: D, pants: M, pshade: D, shoe: P },
  reviewer: { hair: K, hi: D, shirt: D, shade: K, pants: M, pshade: D, shoe: D },
}

const px2 = (c, x, y, col) => c.set(x, y, col)
function thick(c, x0, y0, x1, y1, col, t = 2) { for (let i = 0; i < t; i++) c.line(x0, y0 + i, x1, y1 + i, col) }
function fillEllipse(c, cx, cy, rx, ry, col) {
  for (let y = Math.floor(cy - ry); y <= Math.ceil(cy + ry); y++) for (let x = Math.floor(cx - rx); x <= Math.ceil(cx + rx); x++) { const dx = (x - cx) / rx, dy = (y - cy) / ry; if (dx * dx + dy * dy <= 1.02) c.set(x, y, col) }
}
// 2:1 parallelogram "slab" running up-left: from (x,y) leftward `len` px, `th` px thick
function slab(c, x, y, len, th, col) { for (let i = 0; i < len; i++) for (let j = 0; j < th; j++) c.set(x - i, y - (i >> 1) + j, col) }

function leg(c, L, x, y) { // thigh on the seat, shin down, shoe
  slab(c, x, y, 9, 4, L.pants)
  for (let i = 0; i < 9; i++) c.set(x - i, y - (i >> 1) + 3, L.pshade) // shaded underside
  const kx = x - 8, ky = y - 4
  c.rect(kx - 2, ky + 1, 4, 10, L.pants); c.rect(kx + 1, ky + 1, 1, 10, L.pshade)
  c.rect(kx - 5, ky + 10, 7, 3, L.shoe); c.rect(kx - 5, ky + 10, 7, 1, P)
}

function head(c, role, L, x, y, pose, t) {
  // x,y = head centre
  fillEllipse(c, x, y, 6, 5.6, P) // skin base
  fillEllipse(c, x + 0.6, y - 1.2, 6.2, 4.8, L.hair) // hair cap (back + top)
  c.rect(x + 1, y + 1, 5, 3, L.hair) // back of head
  c.rect(x - 6, y, 3, 4, P); c.set(x - 6, y + 1, K) // left ear / cheek (the side the camera sees)
  c.set(x - 3, y - 3, L.hi); c.set(x - 2, y - 4, L.hi); c.set(x - 1, y - 4, L.hi)
  c.rect(x - 2, y + 5, 4, 2, P) // neck
}

export function drawFigure(px, ax, ay, { role, facing = '-x', pose = 'idle', frame = 0, live = true, night = false }) {
  const L = { ...LOOK[role] }
  if (night && role === 'developer') { L.shirt = M; L.shade = D }
  if (night && role === 'reviewer') { L.shirt = M; L.shade = D } // cyber mode: yellow stays on the headphones only, so the manager desk is the focal point
  const f = live ? frame : 0, alt = f & 1
  sp.clear()
  const hx = HX, hy = HY
  // vertical offsets from pose
  const breathe = live && pose === 'idle' ? (f >> 2) & 1 : 0
  const lean = pose === 'working' || pose === 'testing' || pose === 'reviewing' || pose === 'blocked' || pose === 'fail' ? 1 : 0
  const nod = live && pose === 'receiving' ? (f >> 1) & 1 : 0
  const shake = live && pose === 'fail' ? ((f >> 1) & 1 ? 1 : -1) : 0
  const down = pose === 'blocked' ? 2 : lean

  // far leg + far arm (behind torso)
  leg(sp, L, hx + 2, hy - 2)
  // torso (trapezoid) + shading + hem
  const T = [[hx - 6, hy - 8 + lean], [hx - 4, hy - 11 + lean], [hx + 4, hy - 11 + lean], [hx + 7, hy - 8 + lean], [hx + 6, hy + 1], [hx - 5, hy + 1]]
  sp.poly(T, L.shirt)
  sp.poly([[hx + 3, hy - 11 + lean], [hx + 4, hy - 11 + lean], [hx + 7, hy - 8 + lean], [hx + 6, hy + 1], [hx + 2, hy + 1]], L.shade)
  sp.rect(hx - 5, hy, 12, 1, role === 'developer' ? D : K)
  if (role === 'manager') { // dark vest over a cream shirt: separates torso from sleeves
    sp.poly([[hx - 3, hy - 9 + lean], [hx + 4, hy - 9 + lean], [hx + 5, hy + 0], [hx - 3, hy + 0]], A1)
    sp.rect(hx - 1, hy - 10 + lean, 4, 2, P); sp.set(hx + 1, hy - 8 + lean, H); sp.set(hx + 1, hy - 6 + lean, H)
  }
  // head
  const hyH = hy - 17 + lean + breathe + (down - lean)
  head(sp, role, L, hx + 1 + shake, hyH + nod, pose, f)
  // role silhouette on head / torso
  if (role === 'developer') {
    fillEllipse(sp, hx + 3, hy - 10 + lean, 4, 2.2, night ? M : H) // hood behind the neck
    const bx = hx + 1 + shake, by = hyH + nod
    for (let i = -6; i <= 7; i++) { const yy = by - 6 + (Math.abs(i) > 5 ? 1 : 0); sp.set(bx + i, yy, A2); sp.set(bx + i, yy + 1, A2) } // thick band over the head
    sp.rect(hx - 7 + shake, by - 1, 4, 7, A2); sp.rect(hx - 7 + shake, by - 1, 4, 1, P); sp.rect(hx - 6 + shake, by + 1, 2, 3, D) // near ear cup
    sp.rect(hx + 7 + shake, by, 3, 6, A2) // far cup peeks out behind the head
    sp.line(hx - 8 + shake, by + 5, hx - 12 + shake, by + 8, A2); sp.rect(hx - 13 + shake, by + 8, 2, 2, K) // mic boom
  }
  if (role === 'manager') {
    fillEllipse(sp, hx + 2, hyH - 6 + breathe, 2.3, 2, L.hair) // neat bun
    sp.set(hx - 2, hyH - 4, A1); sp.set(hx - 3, hyH - 3, A1) // hair clip
    sp.line(hx - 6, hyH + 1, hx - 9, hyH - 3, K); sp.set(hx - 9, hyH - 3, H) // pen behind the ear
  }
  if (role === 'reviewer') {
    sp.rect(hx - 4 + shake, hyH + 2, 2, 4, L.hair); sp.rect(hx + 4 + shake, hyH + 2, 3, 4, L.hair) // bob hangs past the chin
    sp.rect(hx - 8 + shake, hyH, 3, 1, K) // glasses arm
    for (const [gx, gy] of [[-12, -2], [-11, -2], [-13, -1], [-10, -1], [-13, 0], [-10, 0], [-12, 1], [-11, 1]]) sp.set(hx + gx + shake, hyH + gy, K) // round lens ring
    sp.set(hx - 12 + shake, hyH - 1, P); sp.set(hx - 11 + shake, hyH, P) // lens glint
    sp.rect(hx - 4, hy - 10 + lean, 9, 2, A3) // scarf
  }

  // near leg + near arm (in front)
  leg(sp, L, hx - 1, hy - 1)
  const S = [hx - 5, hy - 8 + lean] // shoulder (near side)
  const arm = (E, Hd, extra) => {
    thick(sp, S[0], S[1], E[0], E[1], L.shirt, 3); thick(sp, E[0], E[1], Hd[0], Hd[1], role === 'developer' && !night ? H : L.shirt, 3)
    sp.rect(Hd[0] - 1, Hd[1] - 1, 3, 3, P); void extra
  }
  const typeY = live && (pose === 'working' || pose === 'testing' || pose === 'submitting' || pose === 'fail') ? alt : 0
  const holdsBoard = role === 'manager' && pose !== 'assigning'
  const holdsSheet = role === 'reviewer'
  const raise = pose === 'pass' ? 6 : 0
  if (holdsBoard) arm([hx - 9, hy - 3], [hx - 13, hy - 5])
  else if (holdsSheet) arm([hx - 9, hy - 3], [hx - 14, hy - 5 - raise])
  else switch (pose) {
    case 'working': case 'testing': arm([hx - 10, hy - 4], [hx - 17, hy - 6 + typeY]); break
    case 'submitting': arm([hx - 10, hy - 4], [hx - 17, hy - 7 - (live && (f >> 1) & 1 ? 2 : 0)]); break
    case 'reviewing': arm([hx - 10, hy - 4], [hx - 16 + (live ? Math.round(Math.sin(f * 0.8) * 2) : 0), hy - 6]); break
    case 'thinking': arm([hx - 9, hy - 5], [hx - 7, hy - 12]); break
    case 'assigning': arm([hx - 13, hy - 10], [hx - 22, hy - 15 - alt]); break
    case 'receiving': arm([hx - 11, hy - 8], [hx - 8, hyH + nod + 1]); break
    case 'blocked': arm([hx - 11, hy - 10], [hx - 8, hyH + 2]); break
    case 'pass': arm([hx - 12, hy - 13], [hx - 12, hy - 24 - (live ? alt : 0)]); break
    case 'fail': arm([hx - 10, hy - 4], [hx - 17, hy - 6]); break
    default: arm([hx - 9, hy - 3], [hx - 11, hy + 1])
  }
  // role props that live with the body
  if (role === 'manager') { // the planning board: big orange-framed clipboard with sticky notes (lowered onto the lap while assigning)
    const cx = holdsBoard ? hx - 18 : hx - 13, cy = holdsBoard ? hy - 19 : hy - 6
    const hh = holdsBoard ? 13 : 6
    sp.poly([[cx, cy], [cx + 8, cy + 4], [cx + 8, cy + 4 + hh], [cx, cy + hh]], H)
    sp.poly([[cx + 1, cy + 2], [cx + 7, cy + 5], [cx + 7, cy + 3 + hh], [cx + 1, cy + hh - 1]], P)
    sp.line(cx, cy, cx + 8, cy + 4, K); sp.line(cx + 8, cy + 4, cx + 8, cy + 4 + hh, K); sp.line(cx, cy, cx, cy + hh, K); sp.line(cx, cy + hh, cx + 8, cy + 4 + hh, K)
    sp.rect(cx + 2, cy - 1, 4, 2, K)
    if (holdsBoard) {
      sp.rect(cx + 2, cy + 4, 2, 2, H); sp.rect(cx + 5, cy + 6, 2, 2, G); sp.rect(cx + 2, cy + 8, 2, 2, G); sp.rect(cx + 5, cy + 10, 2, 2, H) // sticky notes
      sp.line(cx + 2, cy + 7, cx + 4, cy + 8, M)
    }
    if (pose === 'assigning') sp.rect(hx - 26, hy - 19 - alt, 4, 4, G) // task card in the pointing hand
  }
  if (role === 'reviewer') { // checklist sheet: plain paper, tick boxes, pen (distinct from the manager's orange planning board)
    const cx = hx - 19, cy = hy - 14 - raise
    sp.poly([[cx, cy], [cx + 8, cy + 4], [cx + 8, cy + 15], [cx, cy + 11]], P)
    sp.line(cx, cy, cx + 8, cy + 4, K); sp.line(cx + 8, cy + 4, cx + 8, cy + 15, K); sp.line(cx, cy, cx, cy + 11, K); sp.line(cx, cy + 11, cx + 8, cy + 15, K)
    for (let i = 0; i < 3; i++) { const yy = cy + 3 + i * 3; sp.set(cx + 2, yy, K); sp.set(cx + 3, yy, i === 2 && pose !== 'pass' ? H : G); sp.line(cx + 5, yy + 1, cx + 7, yy + 2, M) }
    if (pose === 'fail') { sp.set(cx + 4, cy + 11, H); sp.set(cx + 5, cy + 12, H); sp.set(cx + 5, cy + 11, H); sp.set(cx + 4, cy + 12, H) }
    if (pose === 'pass') for (let i = 0; i < 3; i++) sp.set(cx + 3, cy + 3 + i * 3, G)
    sp.line(cx + 9, cy + 6 + (live && pose === 'reviewing' ? alt : 0), cx + 12, cy + 4, K); sp.set(cx + 12, cy + 4, A3) // pen
  }
  sp.outline(K)

  // blit with anchor (ax,ay) = seat-top centre on screen; mirrored for the up-right desks
  const ox = ax - HX, oy = ay - HY - 3
  px.blit(sp, ox, oy, facing === '-y')
  return [ox, oy]
}

// speech/status bubble above a character (compact, 9px tall)
export function bubble(px, x, y, icon, col = K, bg = P) {
  const g = ICON[icon]
  px.rect(x, y, 9, 9, bg)
  px.rect(x, y, 9, 1, K); px.rect(x, y + 8, 9, 1, K); px.rect(x, y, 1, 9, K); px.rect(x + 8, y, 1, 9, K)
  px.set(x, y, 255); px.set(x + 8, y, 255); px.set(x, y + 8, 255); px.set(x + 8, y + 8, 255)
  px.glyph(g, x + 2, y + 2, col)
  px.set(x + 3, y + 9, K); px.set(x + 4, y + 9, K); px.set(x + 4, y + 10, K)
}
