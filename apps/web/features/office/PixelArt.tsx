export { OfficeRoom } from './OfficeRoom';
export { DeskSprite as AgentAvatar } from './DeskSprite';

export function TaskDocument({ mark }: { mark?: string }) {
  return (
    <span
      className="task-document-art"
      data-mark={mark || undefined}
      aria-hidden="true"
    />
  );
}
