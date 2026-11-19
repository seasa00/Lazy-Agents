import type { AgentKind } from '@/lib/api/types';
import type { OfficeStatus } from './projections';

export type CharacterCue =
  | 'assigning'
  | 'submitting'
  | 'review-pass'
  | 'review-fail'
  | 'revising'
  | 'approving'
  | 'receiving';

// The state key is a presentation contract. Artwork lives in the sprite sheet,
// while the authoritative office projection decides which state is shown.
export function PixelCharacter({
  kind,
  status,
  active,
  received,
  cue,
}: {
  kind: AgentKind;
  status: OfficeStatus;
  active: boolean;
  received: boolean;
  cue?: CharacterCue;
}) {
  const spriteState =
    cue ??
    (received
      ? 'acknowledging'
      : active
        ? status.toLowerCase()
        : ['Blocked', 'Done', 'Error', 'Waiting'].includes(status)
          ? status.toLowerCase()
          : 'idle');
  return (
    <span
      className="sprite-layer sprite-character pixel-character"
      data-character={kind}
      data-sprite-state={spriteState}
    />
  );
}
