# Lazy Agents — office display system

**Logical canvas:** 480 × 360 (4:3). `scene.js` draws the approved art into its native 228×172 buffer; `PixelOffice` composites it into
the logical canvas at an integer 2× (centred). Hitboxes are exposed in logical coordinates (`src/pixel/layout.js → getAgentHitboxes()`),
so hover/click stay exact at any display scale. The canvas element is only CSS-scaled (`image-rendering: pixelated`, `imageSmoothingEnabled = false`).

**Scale:** `computeScale()` fits the 4:3 canvas into the stage and uses an integer scale when it still uses ≥ 85% of the exact fit
(e.g. 960×720 → 2×, 2560×1080 → 3×), otherwise the exact fractional fit (e.g. 640×480 → 1.33×, 1440×900 → 2.5×). Never non-uniform.
Leftover space is plain backdrop (CSS two-tone), never stretched art.

**Modes (`src/layout/useDisplay.js`):** large ≥ 1100 px (office + 360–400 px inspector) · medium 700–1099 (office + 300–340 px inspector) ·
compact < 700 (office + slim status strip; clicking an agent shows a small card, **Inspect** opens a temporary bottom sheet).

**Pop-out:** `#/popout` route (`window.open(url, 'lazy-agents-office', 'popup=yes,width=960,height=720')`).
Same state, no duplicated logic: the main window is the *authority* (`useOfficeController`), pop-outs *mirror* it and send actions back
over a BroadcastChannel (`src/sync/officeSync.js`). Heartbeat every 1.5 s; 5 s without one → DISCONNECTED. A pop-out opened with no
authority becomes STANDALONE. Replace `officeSync.js` with the backend/SSE source later: `{t:'state'|'beat'}` in, `{t:'action'}` out.

**Fullscreen:** Fullscreen API on `document.documentElement`; the layout reads the live viewport (no hard-coded sizes).
