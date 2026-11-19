import { useEffect, useRef } from 'react'
import { Px, W, H_, present } from './engine.js'
import { drawScene, HIT } from './scene.js'
import { LOGICAL_W, LOGICAL_H, SCENE_SCALE, SCENE_OFFSET_X, SCENE_OFFSET_Y, computeScale, hitTestLogical } from './layout.js'

// Canvas owns: drawing, hover detection, selection visuals, actor click detection.
// Everything is in the fixed 480x360 logical space; the canvas element is only CSS-scaled (nearest neighbour).
export default function PixelOffice({ state, onHover, onSelect, onScale }) {
  const wrap = useRef(), ref = useRef()
  const st = useRef(state), cb = useRef({ onHover, onSelect, onScale })
  st.current = state; cb.current = { onHover, onSelect, onScale }

  useEffect(() => {
    const canvas = ref.current, box = wrap.current
    const ctx = canvas.getContext('2d')
    ctx.imageSmoothingEnabled = false
    canvas.width = LOGICAL_W; canvas.height = LOGICAL_H
    const scene = new Px(W, H_), logical = new Px(LOGICAL_W, LOGICAL_H)
    let raf, last = 0, frame = 0, hover = null
    const fit = () => {
      const { scale, integer } = computeScale(box.clientWidth, box.clientHeight)
      canvas.style.width = `${LOGICAL_W * scale}px`; canvas.style.height = `${LOGICAL_H * scale}px`
      box.dataset.scale = scale.toFixed(2); box.dataset.integer = String(integer)
      cb.current.onScale?.({ scale, integer })
    }
    fit()
    const ro = new ResizeObserver(fit); ro.observe(box)
    const toLogicalPt = (e) => { const r = canvas.getBoundingClientRect(); return [((e.clientX - r.left) * LOGICAL_W) / r.width, ((e.clientY - r.top) * LOGICAL_H) / r.height] }
    const move = (e) => { const id = hitTestLogical(...toLogicalPt(e)); canvas.style.cursor = id ? 'pointer' : 'default'; if (id !== hover) { hover = id; cb.current.onHover?.(id) } }
    const leave = () => { hover = null; canvas.style.cursor = 'default'; cb.current.onHover?.(null) }
    const click = (e) => { const id = hitTestLogical(...toLogicalPt(e)); if (id) cb.current.onSelect?.(id) }
    canvas.addEventListener('pointermove', move); canvas.addEventListener('pointerleave', leave); canvas.addEventListener('click', click)
    // test/debug helper: client-space centre of an agent's character hit region
    window.__officeHit = (id) => {
      const r = HIT[id]?.char, c = canvas.getBoundingClientRect()
      if (!r) return null
      const lx = (r.x + r.w / 2) * SCENE_SCALE + SCENE_OFFSET_X, ly = (r.y + r.h / 2) * SCENE_SCALE + SCENE_OFFSET_Y
      return [c.left + (lx * c.width) / LOGICAL_W, c.top + (ly * c.height) / LOGICAL_H]
    }

    const tick = (t) => {
      raf = requestAnimationFrame(tick)
      const s = st.current, live = !s.reducedMotion
      if (live && t - last < 1000 / 8 && last) return
      last = t; if (live) frame++
      scene.clear(); logical.clear()
      drawScene(scene, s, live ? frame : 0, s.theme)
      logical.blitScaled(scene, SCENE_OFFSET_X, SCENE_OFFSET_Y, SCENE_SCALE)
      present(logical, ctx, s.theme)
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); canvas.removeEventListener('pointermove', move); canvas.removeEventListener('pointerleave', leave); canvas.removeEventListener('click', click) }
  }, [])
  return <div ref={wrap} className="stage"><canvas ref={ref} role="img" aria-label="Lazy Agents office: click Manager, Developer or Reviewer to inspect" /></div>
}
