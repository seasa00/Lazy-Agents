# M6 3D visual direction — The Pocket Workshop

## Purpose

Replace the rejected pixel-art presentation direction with a cozy miniature
office diorama. This document defines the visual target for a later static-scene
implementation review. It does not change the office scene or workflow
presentation code.

The office should feel like a small, carefully made place where three distinct
specialists coordinate. The room itself carries the visual identity: an
off-center cutaway, recognizable furniture silhouettes, warm material contrast,
and a few purposeful objects. It should feel authored like a premium indie-game
miniature rather than assembled from a general-purpose low-poly office kit.

Exactly three employees are present: Manager, Developer, and Reviewer. The
existing React workspace remains the home for navigation, task and activity
views, details, controls, usage, evidence, settings, and recovery. Scene art is
presentation only; existing state projection, committed events, and workflow
contracts remain authoritative.

## Visual thesis and signature

Think of a **pocket workshop**: compact, calm, and gently playful, with the
precision of a small handcrafted model. It is a workroom, not a corporate office
and not a game level. Its objects suggest coordination through paper, tools,
wood inlay, and distinct work surfaces.

Give the room a clipped, irregular footprint with a visibly thick display base.
Use one short return wall and one longer back wall, leaving the front and one
side open to the viewer. A thin warm-wood inlay branches from a small shared
center table toward the three stations. This is a static architectural detail in
the first scene: it must not imply active work or animate by itself. Repeat a
small trio of paper tabs in the planning area as the office's quiet signature.
Avoid floating logos, luminous tracks, or UI-like symbols inside the room.

## Camera and framing

- Use a fixed orthographic camera, aimed at the center of the room from the
  front-left quarter. Set its elevation around 30 degrees and its horizontal
  angle around 35 degrees from the open front edge.
- Frame the complete base with a small, consistent margin. Keep the back wall,
  all three work surfaces, each character's head and torso, and the shared center
  table visible at once.
- Keep perspective nearly flat so the rear station remains readable. No orbit
  controls or free-fly camera; the composition explains the room without user
  rotation.
- Use a responsive canvas that preserves the three-quarter view. At narrow sizes,
  frame the complete diorama within the available width rather than cropping a
  station. Keep status and task information in normal HTML UI.

## Room composition

Use a compact footprint roughly 8 units wide by 6 units deep, with rounded
corners and a clipped front-right corner. The room is an open-front cutaway, not
a full box. A shallow back wall carries the window, planning board, and selected
shelving; a short side return frames the room without hiding the workstations.
Give the floor a muted sage field and a small, asymmetrical rug in a deeper
blue-green. The warm-wood base and thin floor inlay make the miniature feel
crafted and intentional.

Arrange the stations as a loose triangle, with deliberate differences in depth,
angle, scale, and negative space:

```text
                WINDOW
         Planning board / shelf
             MANAGER

   DEVELOPER     shared table       REVIEWER
       angled                         angled
```

The diagram is a relationship, not a symmetry guide. Put the Manager toward the
back and slightly left of center. Turn the Developer's wider station inward from
the front-left. Give the Reviewer a smaller, more upright station on the
front-right, offset toward the window. Keep the shared table small and low; it
should join the workstations without becoming a fourth workstation. Preserve
clear gaps between silhouettes and keep the room visually occupied without
filling every surface.

Limit room dressing to the large window, one planning board, one compact shelf,
three desks, three chairs, three monitors, one shared table, a few plants, one
small rug, desk lights, and a few role-specific objects. Avoid lounge furniture,
extra screens, decorative clutter, and oversized empty floor.

## Character proportions and silhouettes

Characters should read as stylized small figures, around 2.5 heads tall when
seated or standing. Make the head large enough to read at workspace scale, the
torso short and softly shaped, and the hands slightly oversized. Use simplified
clothing blocks and compact limbs with rounded joints. Keep faces nearly blank:
small dark eyes or a simple nose at most. Personality comes from head shape,
hair/headwear, posture, and role props, not realistic facial detail or skin
shading.

Give each figure a distinct silhouette that survives at thumbnail size:

- **Manager:** tidy side-part or soft swept hair, compact jacket-like upper
  silhouette, open posture, and one hand near the planning materials. Use a warm
  sage or cream clothing accent with a small orange pin or tab.
- **Developer:** darker navy clothing, a broad headphone band and ear cups, and a
  slightly forward working posture. The headset is part of the silhouette and
  must read before small details do.
- **Reviewer:** muted orange or dusty violet accent, a distinct bob, cap, or
  simple side-swept hair shape, and a poised posture near the document stack.
  Avoid glasses as the sole differentiator.

Do not use finished characters made from visible placeholder spheres, cylinders,
or stacked primitives. Underlying simple geometry is fine when it is shaped,
joined, beveled, and art-directed into a coherent figure.

## Shape language

Use soft, crafted forms with controlled faceting: rounded chamfers, tapered
legs, curved or clipped desk corners, wedge-shaped supports, and cushions with
gentle volume. Combine a few broad facets with restrained edge highlights so
the low-poly character is visible without looking crude. Keep the same edge
softness and facet scale across room, furniture, and characters.

Avoid raw box-like tabletops, exposed box piles, identical rectangular desks,
perfectly repeated chair shapes, and primitive stacks that announce the modeling
tool. Structural pieces may be simple; each finished object needs an intentional
silhouette, proportion, and join.

## Material language and palette

Use matte or satin materials with quiet surface variation. Let color blocks and
shape carry the scene; do not depend on large textures, glossy plastic, bloom, or
strong gradients. Keep wood grain very subtle, visible only on a few close
surfaces. Screens may use a small flat code or checklist motif, with no legible
dashboard copy inside WebGL.

| Token | Color | Use |
| --- | --- | --- |
| Chalk cream | `#E9E2D3` | Window trim, selected wall panels, paper, small light surfaces |
| Warm maple | `#A8754D` | Display base, desk surfaces, shelf details, floor inlay |
| Soft sage | `#788F7B` | Main floor field, Manager identity, selected plant pots |
| Muted navy | `#354A60` | Developer identity, screen shells, selected room shadows |
| Persimmon | `#C77D52` | Reviewer identity, small tabs and warm accents |
| Ink charcoal | `#343B3D` | Hair, monitor bezels, chair details, deep structural edges |
| Evening blue | `#28394C` | Night wall and window environment, never as a full-scene wash |

The scene must not collapse into beige. Limit cream to light surfaces and
negative space; let the sage floor, warm wood, navy Developer area, and
persimmon Reviewer cues provide distinct broad color regions. Keep role colors
consistent across character clothing and one or two nearby props without making
each station a matching monochrome set.

## Lighting direction

### Day

Use one broad, soft key from the upper-left/front, as if daylight comes through
the large window. Add restrained ambient fill so faces, chair shapes, and desk
details stay readable. Cast soft directional shadows toward the back-right. Keep
the window bright but not emissive enough to flatten the room. Use a simple
shadow setup with modest resolution and no cinematic post-processing.

### Night

Keep every object and camera position identical. Shift the wall and window
environment toward evening blue, reduce the daylight key, and retain a soft cool
fill. Small desk lamps add warm pools on the three work surfaces; their light
should be localized and gentle. Keep role colors and character silhouettes
readable. Avoid a uniformly blue tint, glowing outlines, or dramatic spotlights.

## Workstation identity

Each desk needs its own outline, working angle, equipment arrangement, and role
props. Shared material quality can unify them, but their shapes and proportions
must not be copied.

| Employee | Work surface and silhouette | Role-specific details | Main identity color |
| --- | --- | --- | --- |
| Manager | Medium, tidy L-shaped or clipped-corner desk at the rear; one monitor offset to leave a clear planning surface | Wall planning board with three paper tabs, one notebook or clipboard, compact desk lamp | Sage with cream and maple |
| Developer | Widest, deeper desk turned inward at the front-left; two monitors at slightly different heights and angles | Keyboard, code-screen color blocks, headphones on the character or a desk hook, a small technical tool | Navy with maple and one sage cue |
| Reviewer | Narrower, upright desk angled toward the shared center at the front-right | One monitor, separated document stack, visible checklist sheet with simple marks, side tray or validation stamp | Persimmon or dusty violet with cream |

The planning board belongs to the Manager station, the dual-screen setup belongs
to the Developer, and the document/checklist arrangement belongs to the
Reviewer. These identities should read from silhouette and equipment even when
characters are hidden or scene colors are muted.

## Asset strategy

Use React Three Fiber for composition and presentation, with reusable components
that can later load authored GLB models. Model only the assets whose outline or
character depends on bespoke design. Keep low polygon counts, share materials,
and use no large texture maps. Preserve model sources with the assets so shapes
can be revised without reconstructing them from code.

### Custom GLB assets

- **Three employee figures:** create three authored silhouettes, sharing a
  consistent rig or attachment scheme where practical. Custom geometry is
  required for heads/hair, clothing mass, hands, and the Developer headset.
- **Three workstation bodies:** custom desk profiles and their role-specific
  surface layouts. The Manager's clipped/L form, Developer's deeper asymmetric
  top, and Reviewer's compact angled desk are central to the composition.
- **Chair family:** one sculpted base design with distinct proportions or back
  shapes per station. Do not repeat a generic office-chair asset three times.
- **Planning board and role props:** author the planning board, distinctive
  monitor housings, Developer's dual-monitor arrangement, and the Reviewer
  document/checklist tray as coherent pieces. Small paper marks can remain simple
  geometry or flat material details.
- **Room shell and display base:** custom rounded/clipped footprint, back wall,
  side return, window opening, and wood inlay. These establish the authored
  miniature rather than a generic floor plane.

### Geometry that can stay procedural

Use simple R3F geometry for hidden supports, desk legs, lamp stems, plant stems
and small leaves, mugs, books, paper sheets, keyboard keys, trim, and low-detail
screen marks. These are secondary forms; bevel, taper, or group them so the
finished silhouette remains intentional. A few reusable rounded shapes are
appropriate for cushions and pots. Do not build the main character or desk
silhouette from default primitive geometry.

Organize assets so a desk, character, chair, and role-prop group can be replaced
independently by GLB files. Keep workflow state out of model assets; state
projection belongs in presentation hooks/components, and model components only
consume normalized visual inputs.

## Art direction checks

- The room reads as one compact miniature with exactly three employee stations.
- Manager, Developer, and Reviewer stations are distinguishable by shape,
  equipment, and role props, not only by color or labels.
- The irregular footprint, slightly staggered station angles, and offset props
  create deliberate asymmetry without making the room feel messy.
- At the intended workspace size, head, headset, board, dual monitors, and review
  papers remain recognizable silhouettes.
- Cream is a supporting material. Sage, maple, navy, persimmon, and charcoal
  have balanced, purposeful presence.
- Day and night preserve the exact same room layout and camera framing.
- The result feels like a carefully composed miniature world, not a primitive
  demo, office template, photoreal room, or crowded game scene.
