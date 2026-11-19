// One fixed logical coordinate system for the whole office.
//   Logical canvas: 480 x 360 (4:3). The approved artwork is drawn by scene.js into its native 228x172 buffer
//   and composited into the logical canvas at an integer 2x (so art pixels are 2x2 logical pixels), centred.
//   Hitboxes are exposed in LOGICAL coordinates, so they stay correct at any display scale.
import { HIT } from './scene.js'
import { W as SCENE_W, H_ as SCENE_H } from './engine.js'

export const LOGICAL_W = 480
export const LOGICAL_H = 360
export const SCENE_SCALE = 2
export const SCENE_OFFSET_X = (LOGICAL_W - SCENE_W * SCENE_SCALE) / 2
export const SCENE_OFFSET_Y = (LOGICAL_H - SCENE_H * SCENE_SCALE) / 2

/** @typedef {{id:'manager'|'developer'|'reviewer', kind:'character'|'workstation', x:number, y:number, width:number, height:number}} AgentHitbox */
const toLogical = (r) => ({ x: r.x * SCENE_SCALE + SCENE_OFFSET_X, y: r.y * SCENE_SCALE + SCENE_OFFSET_Y, width: r.w * SCENE_SCALE, height: r.h * SCENE_SCALE })
const ORDER = ['reviewer', 'developer', 'manager'] // front-most first

/** @returns {AgentHitbox[]} characters first (front-most first), then their workstations. */
export function getAgentHitboxes() {
  const out = []
  for (const kind of ['char', 'desk']) for (const id of ORDER) if (HIT[id]?.[kind]) out.push({ id, kind: kind === 'char' ? 'character' : 'workstation', ...toLogical(HIT[id][kind]) })
  return out
}
export function hitTestLogical(x, y) {
  for (const b of getAgentHitboxes()) if (x >= b.x && x < b.x + b.width && y >= b.y && y < b.y + b.height) return b.id
  return null
}

/** Fit the 4:3 office into an available box. Integer scale when it still uses >=85% of the exact fit. */
export function computeScale(availW, availH) {
  const fit = Math.min(availW / LOGICAL_W, availH / LOGICAL_H)
  if (!(fit > 0)) return { scale: 1, integer: true, fit: 1 }
  const ki = Math.floor(fit)
  const integer = ki >= 1 && ki / fit >= 0.85
  return { scale: integer ? ki : fit, integer, fit }
}
