import { Px, PALETTES } from './src/pixel/engine.js'
import { drawFigure } from './src/pixel/sprites.js'
import fs from 'fs'
const theme = process.argv[2] || 'day'
const poses = { manager: ['idle', 'thinking', 'assigning'], developer: ['idle', 'working', 'receiving', 'blocked'], reviewer: ['idle', 'reviewing', 'pass', 'fail'] }
const cols = 4, cw = 60, ch = 44
const roles = Object.keys(poses)
const px = new Px(cols * cw, roles.length * ch)
roles.forEach((r, ri) => poses[r].forEach((p, ci) => { drawFigure(px, ci * cw + 36, ri * ch + 34, { role: r, facing: ci % 2 ? '-y' : '-x', pose: p, frame: 1, live: true }) }))
const pal = PALETTES[theme].map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)))
const bg = theme === 'day' ? [203, 187, 151] : [20, 31, 44]
const k = 8, W = px.w * k, H = px.h * k
const out = Buffer.alloc(W * H * 3)
for (let y = 0; y < px.h; y++) for (let x = 0; x < px.w; x++) { const c = px.buf[y * px.w + x]; const col = c === 255 ? bg : pal[c]; for (let j = 0; j < k; j++) for (let i = 0; i < k; i++) { const o = ((y * k + j) * W + x * k + i) * 3; out[o] = col[0]; out[o + 1] = col[1]; out[o + 2] = col[2] } }
fs.writeFileSync('/home/claude/shot/sheet.ppm', Buffer.concat([Buffer.from(`P6 ${W} ${H} 255\n`), out]))
