# M6 visual direction — AI Office

## Intent

Use the supplied office illustration as a mood and hierarchy reference: the work
should feel like a small, welcoming studio with recognizable desks, warm wood,
windows, plants, paper tools, and three distinct coworkers. The room is the
visual signature; status and task text keep it useful as an operations view.

The supplied reference is the primary visual direction. Its broad room, left-side
navigation and light compact dashboard treatment apply inside the existing project
workspace. Exactly three employees remain: Manager, Developer, Reviewer. All data
comes from backend snapshots and existing inspection queries.

## Layout

The office is a broad panorama above the run controls/current-run panels and task
board/activity columns. Desktop navigation sits to the left; tablet navigation
wraps above the scene. Desks are arranged Manager left, Developer center, Reviewer
right, with independent equipment, character and chair layers. Compact HTML
name/status/task/review cards remain attached beneath each station. Handoff routes
use those same horizontal anchors. The latest explicit user reference supersedes
the earlier 320 × 224 triangular composition.

At mobile widths, remove the room backdrop and stack the same stations in Manager,
Developer, Reviewer order. Preserve labels, keyboard interaction, task inspection,
review inspection and authoritative active-state indicators.

## Room composition

Build a compact room from a tiled floor, cutaway walls, a window, planning board,
bookcase, plants, rug, and threshold. Match the supplied reference's consistent
top-down / three-quarter cutaway perspective: show enough tabletop and floor
surface to make objects readable, with front edges and wall depth giving the room
its cozy, game-like dimensionality. Keep the camera and object angles consistent
across all assets. Warm wood, soft light, material texture, and small highlights
should come from authored pixel-art shading rather than photographic texture or
lighting effects.

Each employee has an independent **80 × 64 logical desk zone** for placement,
interaction, and hit testing. It is not a visual crop or a self-contained diorama.
Shared furniture gives the room coherence; a few role-specific objects make
stations legible at a glance:

- **Manager:** planning display, one monitor, notebook, and clipboard/document.
- **Developer:** dual code monitors, keyboard, and a restrained code-screen cue.
- **Reviewer:** monitor, marked checklist, and paper stack.

The supplied image includes a lounge and a cat. These can inform the room's
friendly tone, but are not part of the current M6 scene footprint or sprite set.
Do not let decorative objects compete with work status or imply another agent.

## Pixel scale and rendering

One logical cell is one pixel in the art coordinate space. Prefer reusable,
authored transparent pixel-art sprites and sprite sheets for characters, desks,
chairs, monitors, plants, shelves, documents, role-specific props, and animation
states. Keep assets aligned to the shared scene coordinates, with transparent bounds
that allow sprites to layer and overlap as a composed room. Use nearest-neighbor
scaling at integer factors where the layout allows. Preserve crisp pixel edges and
deliberate clusters of highlight, shadow, and material texture; avoid blur,
antialias-dependent detail, gradients, and image cropping. SVG and CSS may handle
simple room geometry, overlays, hit regions, status UI, and lightweight structural
elements. They are supporting layers, not a requirement to reconstruct the main
art from rectangles.

Labels and controls remain normal interface text, not pixelated artwork. Preserve
the existing focus indicator and readable status words so meaning does not depend
on color or animation.

## Sprite strategy and asset structure

Keep scene art modular and composable. Do not create a single room illustration
with characters baked in. Prefer reusable transparent sprite assets; sprite sheets
may group related frames or animation states. Preserve these conceptual
responsibilities as the asset structure evolves:

| Asset | Responsibility |
| --- | --- |
| Sprite assets / sheets | Transparent character, furniture, prop, and animation artwork |
| `features/office/OfficeRoom.tsx` | Room composition, simple geometry, and sprite placement |
| `features/office/PixelCharacter.tsx` | Character sprite and state-frame selection |
| `features/office/DeskSprite.tsx` | Desk-zone composition from shared furniture and role props |
| `features/office/PixelArt.tsx` | Stable room, avatar, and document exports |
| `features/office/office.css` | Scale, overlays, status presentation, responsive rules, and lightweight motion |

Add or revise artwork as reusable authored sprite assets, not as a requirement to
edit TypeScript matrices. Reuse props and animation frames where possible. Keep
scene artwork presentational: the agent/task projection and committed event IDs
remain the only sources for visual state and handoffs.

## Palette

The palette is warm, material-led, and restrained: oat and honey floor/desk tones,
weathered sage walls and plants, ink-dark outlines, and muted blue-green screens.
Use the supplied reference's timber warmth as the tone, while retaining the
existing low-noise M6 palette as the implementation baseline.

The current indexed sprite colors provide a useful baseline for the palette, even
as the art source moves toward transparent sprite assets:

| Use | Color |
| --- | --- |
| Outline / deep structure | `#303B40` |
| Hair and dark wood | `#4C403B` |
| Skin shadow / warm midtone | `#D5A17B` |
| Skin highlight | `#EFC39B` |
| Paper | `#EDE3BF` |
| Screen blue | `#49667A` |
| Desk gold | `#C79253` |
| Plant green | `#447966` |
| Reviewer violet | `#756082` |
| Lamp light | `#E9BD6B` |

The room uses CSS custom properties for floor, seams, wall, trim, desks, sky,
window lights, rug, and shadow. Keep colors opaque and use discrete theme values.
Status color can reinforce state, but status text and icon remain visible in every
theme. Avoid applying the whole screenshot's large navigation/dashboard palette to
the scene itself.

## Agent visual identity

Identity is stable across status changes: retain each character's silhouette,
hair/clothing colors, and role props in day, night, idle, and active states.

- **Manager:** formal dark hair and blue clothing; planning and coordination tools.
- **Developer:** green clothing and a headset; paired code monitors.
- **Reviewer:** violet clothing and glasses; checklist and stacked papers.

Each station carries the canonical name, role, current status, and current task
when present. The employee is keyboard-focusable and opens the existing agent
detail view; task and review labels lead to their existing inspection views.
Names and labels must remain readable over both day and night surfaces.

Characters use a **sprite-state contract**: the presentation layer selects an
authored frame or animation by canonical employee kind and projected visual state.
The contract covers `idle`, `thinking`, `working`, `waiting`, `reviewing`,
`blocked`, `done`, and `error`, with a brief `acknowledging` cue for a committed
handoff. Art assets provide the frames; TypeScript maps authoritative state to a
contract key and does not define the character artwork as pixel matrices. Missing
state-specific frames fall back to that character's still frame while the textual
status remains exact.

## Day and night behavior

Day/Night changes the existing room and workspace color tokens and the window
tiles only. Day uses a pale sage wall, honey floor, muted blue daylight, and warm
wood. Night shifts the wall, floor, trim, and sky toward slate/blue-green, darkens
the city silhouette, and keeps window lights and lamps warm. Preserve object
positions, character identity, status contrast, and task text; the scene should
read as the same office after hours, not a second layout. Persist the selected
theme for the next visit when browser storage is available.

## Animation states

Motion is sparse, stepped, and caused by authoritative work or a newly observed
committed handoff. It never simulates an employee lifecycle or affects execution.

| Visual cue | Trigger |
| --- | --- |
| Character work frame (for example, typing or planning) | Existing backend operation is pending for the active employee; selected through the sprite-state contract |
| Checklist/document frame | Manager thinking or Reviewer reviewing while active |
| Code-screen cursor/line frame | Developer working while active |
| Task packet travels between desks | New, deduplicated committed task assignment, submission, review, or revision event |
| Receiving nameplate outline and brief character acknowledgement frame | Same live handoff reaches its destination |

Idle, waiting, paused, blocked, completed, canceled, recovery-required, and error
states remain still. A disconnected view shows its last known state without
presenting it as live work. Historical events on mount, duplicate event IDs, and
replayed events do not replay packet travel. Reduced-motion preference removes
all movement; status labels and the receiving-desk acknowledgement remain
understandable without it. A visual timeout only clears the visual cue.

## Visual acceptance notes

- The office reads as one room and contains exactly three distinct workstations.
- Pixel edges stay crisp at desktop, tablet, and stacked mobile sizes.
- Manager, Developer, and Reviewer can be identified by appearance and station
  tools without relying on their status color.
- Day and night keep the same scene composition and legible controls/statuses.
- Every active cue corresponds to current projected state or a committed event;
  no timer invents work, status, or a handoff.
- The scene remains understandable with motion disabled and at narrow widths.
