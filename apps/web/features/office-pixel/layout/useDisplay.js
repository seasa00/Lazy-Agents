import { useCallback, useEffect, useState, useRef } from 'react'

// Explicit display modes (not just CSS scaling):
//   large   >= 1100px : office + full inspector, side by side
//   medium   700-1099 : office + narrower inspector, side by side
//   compact   < 700   : office only; click shows a small card, Inspect opens a temporary bottom sheet
export function modeFor(w) { return w >= 1100 ? 'large' : w >= 700 ? 'medium' : 'compact' }
export function inspectorWidthFor(mode, w) {
  if (mode === 'large') return Math.round(Math.min(400, Math.max(360, w * 0.3)))
  if (mode === 'medium') return Math.round(Math.min(340, Math.max(300, w * 0.36)))
  return w
}

export function useDisplay() {
  const containerRef = useRef(null)
  const read = () => ({ w: containerRef.current?.clientWidth || window.innerWidth, h: containerRef.current?.clientHeight || window.innerHeight })
  const [size, setSize] = useState(read)
  const [fullscreen, setFullscreen] = useState(false)
  useEffect(() => {
    const on = () => setSize(read())
    const observer = new ResizeObserver(on)
    if (containerRef.current) observer.observe(containerRef.current)
    on()
    const fs = () => setFullscreen(!!document.fullscreenElement)
    window.addEventListener('resize', on); document.addEventListener('fullscreenchange', fs)
    return () => { observer.disconnect(); window.removeEventListener('resize', on); document.removeEventListener('fullscreenchange', fs) }
  }, [])
  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) document.exitFullscreen?.()
    else containerRef.current?.requestFullscreen?.().catch(() => {})
  }, [])
  const mode = modeFor(size.w)
  return { containerRef, ...size, mode, inspectorWidth: inspectorWidthFor(mode, size.w), fullscreen, toggleFullscreen, canFullscreen: !!document.documentElement.requestFullscreen }
}
