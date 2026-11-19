import type { AgentKind } from '@/lib/api/types';
import type { OfficeStatus } from './projections';
import { PixelCharacter, type CharacterCue } from './PixelCharacter';

// Columns select employees; rows select independent furniture and character layers.
// The 80 × 64 box is a layout and interaction zone, not a visible mini-scene.
export function DeskSprite({
  kind,
  status = 'Idle',
  active = false,
  received = false,
  cue,
}: {
  kind: AgentKind;
  status?: OfficeStatus;
  active?: boolean;
  received?: boolean;
  cue?: CharacterCue;
}) {
  return (
    <span className={`agent-art atlas-${kind}`} data-desk-sprite={kind}>
      <span className="sprite-layer sprite-desk" data-desk-object="desk" />
      <span
        className="sprite-layer sprite-equipment work-document"
        data-desk-object={
          kind === 'developer'
            ? 'monitors'
            : kind === 'reviewer'
              ? 'checklist'
              : 'planning-tools'
        }
      />
      <PixelCharacter
        kind={kind}
        status={status}
        active={active}
        received={received}
        cue={cue}
      />
      <span className="sprite-layer sprite-chair" data-desk-object="chair" />
      <span className="work-hands" aria-hidden="true" />
      {kind === 'developer' && <span className="screen-lines" />}
    </span>
  );
}
