'use client';

import { RoundedBox } from '@react-three/drei';

export function Shelf({
  position,
  night = false,
}: {
  position: [number, number, number];
  night?: boolean;
}) {
  const timber = night ? '#634b3c' : '#8c6446';
  return (
    <group position={position}>
      <RoundedBox
        position={[0, 1.23, 0]}
        args={[1.1, 2.5, 0.46]}
        radius={0.07}
        smoothness={2}
        castShadow
      >
        <meshStandardMaterial color={timber} roughness={0.9} />
      </RoundedBox>
      {[0.48, 1.22, 1.96].map((y) => (
        <mesh key={y} position={[0, y, 0.25]} castShadow>
          <boxGeometry args={[0.94, 0.08, 0.48]} />
          <meshStandardMaterial
            color={night ? '#98765a' : '#b4855c'}
            roughness={0.88}
          />
        </mesh>
      ))}
      {[
        [-0.29, 0.77, '#718978'],
        [-0.03, 0.81, '#c58b62'],
        [0.25, 0.77, '#6a7c8f'],
        [-0.23, 1.51, '#9d8069'],
        [0.08, 1.55, '#7a8e76'],
        [0.32, 1.5, '#bd976a'],
        [-0.3, 2.25, '#647b86'],
        [0.02, 2.2, '#bc805e'],
        [0.3, 2.25, '#788b74'],
      ].map(([x, y, color], index) => (
        <RoundedBox
          key={index}
          position={[Number(x), Number(y), 0.24]}
          args={[0.17, 0.46, 0.24]}
          radius={0.025}
          smoothness={1}
        >
          <meshStandardMaterial color={String(color)} roughness={0.96} />
        </RoundedBox>
      ))}
    </group>
  );
}
