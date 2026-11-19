'use client';

import { AgentFigure } from './AgentFigure';

export function ManagerAgent({
  position,
}: {
  position: [number, number, number];
}) {
  return (
    <AgentFigure
      position={position}
      style={{ coat: '#80947d', hair: '#55493f' }}
    />
  );
}
