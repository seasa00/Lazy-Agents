'use client';

import { AgentFigure } from './AgentFigure';

export function DeveloperAgent({
  position,
}: {
  position: [number, number, number];
}) {
  return (
    <AgentFigure
      position={position}
      style={{ coat: '#536887', hair: '#303941', headphones: true }}
    />
  );
}
