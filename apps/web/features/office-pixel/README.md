# Office pixel visual port

**Current status: M6 COMPLETE — frozen and closed.** The approved Pixel Office,
Agent Inspector, pop-out/fullscreen behavior, and existing-system integration
are delivered. The port notes and recorded validation below are historical.
M7 — Agent Runtime Modernization & Production Hardening is In Progress with M7.1 complete; its
runtime trace integration is planned in M7.3, not unfinished M6 work. See the
[roadmap](../../../../docs/IMPLEMENTATION_MILESTONES.md).

Preview and pop-out: `/office-pixel`. The project workspace embeds `OfficeExperience` in a sized container; its previous Office remains available under “Previous Office view.” This is a client-only Next.js leaf, not a second React application.

Source: repository `office-pixel/src`, retained unchanged. Reused pixel/* (renderer, sprites, scene, hitboxes, scaling), ui/*, inspector/AgentInspector.jsx (all tabs), debug/* (contract, redaction, mock adapter), state/* and sync/useOfficeController.js. Mock pose presets are debug fixtures only; no production workflow or API was added.

Adaptations: App.jsx became OfficeExperienceView.jsx; OfficeExperience.tsx provides the client/dynamic boundary. CSS is scoped to the component and document-global theme effects were removed. useDisplay measures the component with ResizeObserver and fullscreens its container. officeSync uses a mock-specific channel and routes pop-outs to /office-pixel. No Vite entry or bootstrap is shipped in the feature.

New verification scripts: scripts/verify-office-pixel.mjs, scripts/compare-office-pixel.mjs, scripts/office-reference.config.mjs. The reference harness serves unchanged prototype sources using installed React/Vite dependencies; it does not reproduce the prototype's React 18 dependency environment.

Validation: typecheck, 128 frontend tests, production build, headed Chromium interaction checks, and Prettier for touched workspace files. Screenshots and comparison.json are in test-results/office-pixel. Day/night canvas pixels and displayed canvas dimensions match at 1280x900 with reduced motion; inspector dimensions match at 384x900. Captures cover main, selected developer, inspector, every tab, usage/optimization, compact/standard pop-out, fullscreen and both themes. No known intentional visual differences in the dedicated preview. The embedded workspace has its own surrounding layout. Exhaustive cross-browser and existing backend-driven M5.2 end-to-end verification were not performed.

The former pending “Second pass” integration checklist is superseded by the accepted M6 completion status. It is not an open M6 backlog. Future LangGraph trace mapping belongs to M7.3; Pixel Office and Agent Inspector remain consumers of backend-authoritative state. Mock fixture labels must never be presented as evidence of live backend connectivity.
