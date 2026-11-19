'use client';

import { AgentFigure } from './AgentFigure';

export function ReviewerAgent({
  position,
}: {
  position: [number, number, number];
}) {
  return (
    <AgentFigure
      position={position}
      style={{ coat: '#a37d83', hair: '#795749', bob: true }}
    />
  );
}
