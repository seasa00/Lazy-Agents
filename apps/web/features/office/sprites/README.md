# Layered M6 office art

The primary visual reference is the supplied Lazy Agents dashboard. The office
uses a broad, shallow panorama and three stations, left to right: Manager,
Developer, Reviewer. Characters face their monitors, with chairs in front and
role equipment on the wooden desktops. HTML status and task cards sit beneath.

Assets under `apps/web/public/office/`:

- `room-panorama-day.png` and `room-panorama-night.png`: matching empty structural
  shells (walls, windows, floor and threshold), without employees or furniture.
- `stations-v2.png`: transparent 3-column × 4-row atlas. Columns select Manager,
  Developer and Reviewer; rows select character, desk, chair and equipment.
  `DeskSprite.tsx` composes these independent layers with explicit depth order.
- `plant.png` and `document.png`: separate reusable decorations and handoff packet.

Original assets remain available. The new panorama and atlas were generated with
the built-in imagegen tool; exact prompts are in [M6_PROMPTS.md](M6_PROMPTS.md).
The night shell is a lighting edit with matching geometry. CSS uses full shell
bounds and atlas cells, nearest-neighbor rendering, and no flattened workstation
illustration. No backend values are painted into artwork; screen marks are
abstract decorative cues.

`PixelCharacter.tsx` selects a visual state key from authoritative projections;
state-specific art currently falls back to each employee's still sprite. Hands,
work cues and committed handoff acknowledgements remain separate CSS layers.
Motion is disabled for paused, blocked, disconnected and reduced-motion states.
No presentation timer changes task or execution state.

Desktop uses a broad scene with attached cards. Tablet retains the panorama;
mobile removes the shell and stacks the same station components in role order.
The dashboard reuses the existing controls, task board, activity and inspection
views. Day/Night selection persists locally and preserves object positions.
