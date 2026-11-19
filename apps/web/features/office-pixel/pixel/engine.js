// Tiny indexed-colour pixel engine. Everything is drawn into a Uint8Array of palette
// indices, so swapping a theme is just swapping the palette (no redraw logic changes).

export const K = 0, D = 1, M = 2, P = 3, H = 4, G = 5, S = 6, S2 = 7, R2 = 8, A1 = 9, A2 = 10, A3 = 11, OL = 12 // ink, deep, mid, pale, hot, glow, room-light, room-dark
export const PALETTES = {
  // print palette from the reference: black-brown, orange, cream, tan (+ a deep shade)
  day: ['#2b1a12', '#8a3516', '#cbbb97', '#efe4c8', '#ff5a1f', '#ff5a1f', '#efe4c8', '#cbbb97', '#8a3516', '#2c5a45', '#2f79b3', '#7d5c94', '#4a2c1e'],
  // cyberpunk-2077 night: ink / steel / teal / cold white / yellow / cyan / (room) / red
  night: ['#04050a', '#141f2c', '#24516a', '#cfe3ea', '#fcee0a', '#00e5ff', '#101c2a', '#070e18', '#ff1a4f', '#1e7a63', '#1aa6c9', '#8a68d0', '#0b1726'],
}
export const BACKDROP = { day: [M, K], night: [D, K] } // [upper-right, lower-left]

export const W = 228, H_ = 172 // tight around the room so the scene fills the screen
export const OX = 114, OY = 63 // screen position of world (0,0,0)

export const P3 = (x, y, z = 0) => [Math.round(OX + (x - y) * 8), Math.round(OY + (x + y) * 4 - z)]

export class Px {
  constructor(w, h) { this.w = w; this.h = h; this.buf = new Uint8Array(w * h).fill(255) }
  clear(c = 255) { this.buf.fill(c) }
  set(x, y, c) { if (c >= 0 && c !== 255 && x >= 0 && y >= 0 && x < this.w && y < this.h) this.buf[y * this.w + x] = c }
  get(x, y) { return x < 0 || y < 0 || x >= this.w || y >= this.h ? 255 : this.buf[y * this.w + x] }
  rect(x, y, w, h, c) { for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) this.set(x + i, y + j, typeof c === 'function' ? c(x + i, y + j) : c) }
  line(x0, y0, x1, y1, c) {
    let dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1, err = dx + dy
    for (;;) {
      this.set(x0, y0, c)
      if (x0 === x1 && y0 === y1) break
      const e2 = 2 * err
      if (e2 >= dy) { err += dy; x0 += sx }
      if (e2 <= dx) { err += dx; y0 += sy }
    }
  }
  poly(pts, fill) {
    let minY = Infinity, maxY = -Infinity
    for (const p of pts) { minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]) }
    for (let y = minY; y <= maxY; y++) {
      const xs = []
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i], b = pts[(i + 1) % pts.length]
        if ((a[1] <= y && b[1] > y) || (b[1] <= y && a[1] > y)) xs.push(a[0] + ((y - a[1]) * (b[0] - a[0])) / (b[1] - a[1]))
      }
      xs.sort((p, q) => p - q)
      for (let i = 0; i + 1 < xs.length; i += 2) for (let x = Math.ceil(xs[i] - 0.01); x <= Math.floor(xs[i + 1] + 0.01); x++) this.set(x, y, typeof fill === 'function' ? fill(x, y) : fill)
    }
  }
  loop(pts, c) { for (let i = 0; i < pts.length; i++) { const a = pts[i], b = pts[(i + 1) % pts.length]; this.line(a[0], a[1], b[0], b[1], c) } }
  blit(src, ox, oy, flip = false) {
    for (let y = 0; y < src.h; y++) for (let x = 0; x < src.w; x++) { const c = src.buf[y * src.w + x]; if (c !== 255) this.set(ox + (flip ? src.w - 1 - x : x), oy + y, c) }
  }
  // nearest-neighbour upscale blit (integer factor)
  blitScaled(src, ox, oy, k) {
    for (let y = 0; y < src.h; y++) for (let x = 0; x < src.w; x++) { const c = src.buf[y * src.w + x]; if (c === 255) continue; for (let j = 0; j < k; j++) for (let i = 0; i < k; i++) this.set(ox + x * k + i, oy + y * k + j, c) }
  }
  outline(c = K) { // 1px silhouette outline (around all non-transparent pixels)
    const out = []
    for (let y = 0; y < this.h; y++) for (let x = 0; x < this.w; x++) {
      if (this.get(x, y) !== 255) continue
      if (this.get(x - 1, y) !== 255 || this.get(x + 1, y) !== 255 || this.get(x, y - 1) !== 255 || this.get(x, y + 1) !== 255) out.push([x, y])
    }
    for (const [x, y] of out) this.set(x, y, c)
  }
  // faces in the 2:1 projection --------------------------------------------------
  // faceL: plane facing +y (visible lower-left face), spans +x. faceR: plane facing +x (lower-right face), spans +y.
  faceL(x, y, z, wTiles, h, fn) {
    const [sx, sy] = P3(x, y, z), w = Math.round(wTiles * 8)
    for (let c = 0; c < w; c++) for (let v = 0; v < h; v++) this.set(sx + c, sy + (c >> 1) - v, fn(c, v, w, h))
  }
  faceR(x, y, z, wTiles, h, fn) {
    const [sx, sy] = P3(x, y, z), w = Math.round(wTiles * 8)
    for (let c = 0; c < w; c++) for (let v = 0; v < h; v++) this.set(sx - c, sy + (c >> 1) - v, fn(c, v, w, h))
  }
  // box: x,y in tiles, z & dz in px. t/l/r = colour or fn. l = +y face, r = +x face.
  box(x, y, z, dx, dy, dz, { t = P, l = M, r = D, o = OL } = {}) {
    const top = z + dz
    const A = P3(x, y, top), B = P3(x + dx, y, top), C = P3(x + dx, y + dy, top), Dd = P3(x, y + dy, top)
    this.faceL(x, y + dy, z, dx, dz, typeof l === 'function' ? l : () => l)
    this.faceR(x + dx, y, z, dy, dz, typeof r === 'function' ? r : () => r)
    this.poly([A, B, C, Dd], typeof t === 'function' ? t : t)
    if (o !== null && o !== undefined) {
      this.loop([A, B, C, Dd], o)
      const Cb = P3(x + dx, y + dy, z), Db = P3(x, y + dy, z), Bb = P3(x + dx, y, z)
      this.line(Dd[0], Dd[1], Db[0], Db[1], o); this.line(C[0], C[1], Cb[0], Cb[1], o); this.line(B[0], B[1], Bb[0], Bb[1], o)
      this.line(Db[0], Db[1], Cb[0], Cb[1], o); this.line(Cb[0], Cb[1], Bb[0], Bb[1], o)
    }
  }
  // flat quad on the floor (rugs). pat(worldX, worldY) -> colour
  flat(x0, y0, x1, y1, pat, o = OL, z = 0) {
    const pts = [P3(x0, y0, z), P3(x1, y0, z), P3(x1, y1, z), P3(x0, y1, z)]
    this.poly(pts, (px, py) => { const u = (px - OX) / 8, v = (py - OY) / 4; return pat((u + v) / 2, (v - u) / 2) })
    if (o !== null) this.loop(pts, o)
  }
  text(str, x, y, c) {
    let cx = x
    for (const ch of str) {
      const g = FONT[ch]
      if (!g) { cx += 2; continue }
      for (let j = 0; j < 5; j++) for (let i = 0; i < 3; i++) if (g[j][i] === '#') this.set(cx + i, y + j, c)
      cx += 4
    }
  }
  glyph(rows, x, y, c) { rows.forEach((r, j) => [...r].forEach((ch, i) => { if (ch === '#') this.set(x + i, y + j, c) })) }
}

export const chk = (a, b) => (p, q) => ((p + q) & 1 ? a : b)
export const dot = (a, b) => (p, q) => ((p & 1) === 0 && (q & 1) === 0 ? b : a)
export const flatc = (c) => () => c

// Writes the index buffer to the canvas. Transparent pixels (255) stay transparent so the stage backdrop shows through.
export function present(px, ctx, theme) {
  const pal = PALETTES[theme].map((h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)])
  const img = ctx.createImageData(px.w, px.h)
  for (let i = 0; i < px.buf.length; i++) {
    const c = px.buf[i], o = i * 4
    if (c === 255) { img.data[o + 3] = 0; continue }
    const col = pal[c]
    const y = (i / px.w) | 0, k = theme === 'night' && ((y >> 1) & 1) ? 0.86 : 1 // CRT scanlines in cyber mode (per art pixel row)
    img.data[o] = col[0] * k; img.data[o + 1] = col[1] * k; img.data[o + 2] = col[2] * k; img.data[o + 3] = 255
  }
  ctx.putImageData(img, 0, 0)
}

// 3x5 lowercase pixel font
const F = (s) => s.split('|')
export const FONT = {
  a: F('.#.|#.#|###|#.#|#.#'), b: F('##.|#.#|##.|#.#|##.'), c: F('.##|#..|#..|#..|.##'), d: F('##.|#.#|#.#|#.#|##.'),
  e: F('###|#..|##.|#..|###'), f: F('###|#..|##.|#..|#..'), g: F('.##|#..|#.#|#.#|.##'), h: F('#.#|#.#|###|#.#|#.#'),
  i: F('###|.#.|.#.|.#.|###'), j: F('..#|..#|..#|#.#|.#.'), k: F('#.#|#.#|##.|#.#|#.#'), l: F('#..|#..|#..|#..|###'),
  m: F('#.#|###|###|#.#|#.#'), n: F('##.|#.#|#.#|#.#|#.#'), o: F('.#.|#.#|#.#|#.#|.#.'), p: F('##.|#.#|##.|#..|#..'),
  q: F('.#.|#.#|#.#|###|.##'), r: F('##.|#.#|##.|#.#|#.#'), s: F('.##|#..|.#.|..#|##.'), t: F('###|.#.|.#.|.#.|.#.'),
  u: F('#.#|#.#|#.#|#.#|###'), v: F('#.#|#.#|#.#|#.#|.#.'), w: F('#.#|#.#|###|###|#.#'), x: F('#.#|#.#|.#.|#.#|#.#'),
  y: F('#.#|#.#|.#.|.#.|.#.'), z: F('###|..#|.#.|#..|###'),
  '.': F('...|...|...|...|.#.'), '!': F('.#.|.#.|.#.|...|.#.'), '?': F('##.|..#|.#.|...|.#.'), '-': F('...|...|###|...|...'),
}

export const ICON = {
  dots: ['.....', '.....', '.....', '.....', '#.#.#'],
  arrow: ['..#..', '...#.', '#####', '...#.', '..#..'],
  bang: ['..#..', '..#..', '..#..', '.....', '..#..'],
  up: ['..#..', '.###.', '#.#.#', '..#..', '..#..'],
  cross: ['#...#', '.#.#.', '..#..', '.#.#.', '#...#'],
  ask: ['.###.', '#...#', '..##.', '.....', '..#..'],
  check: ['.....', '....#', '#..#.', '.##..', '..#..'],
  smile: ['.....', '#...#', '.....', '#...#', '.###.'],
}
