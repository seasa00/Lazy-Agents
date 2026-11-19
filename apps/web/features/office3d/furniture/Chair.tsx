'use client';

import { RoundedBox } from '@react-three/drei';

export function Chair({
  position,
  color = '#53606a',
}: {
  position: [number, number, number];
  color?: string;
}) {
  return (
    <group position={position}>
      <RoundedBox
        position={[0, 0.65, -0.1]}
        args={[0.76, 0.16, 0.68]}
        radius={0.12}
        smoothness={3}
        castShadow
      >
        <meshStandardMaterial color={color} roughness={0.9} />
      </RoundedBox>
      <RoundedBox
        position={[0, 1.05, -0.38]}
        args={[0.74, 0.82, 0.16]}
        radius={0.12}
        smoothness={3}
        castShadow
      >
        <meshStandardMaterial color={color} roughness={0.9} />
      </RoundedBox>
      {[-1, 1].flatMap((x) =>
        [-1, 1].map((z) => (
          <mesh
            key={`${x}-${z}`}
            position={[x * 0.28, 0.31, -0.1 + z * 0.24]}
            castShadow
          >
            <cylinderGeometry args={[0.045, 0.055, 0.58, 8]} />
            <meshStandardMaterial color="#594b40" roughness={0.95} />
          </mesh>
        )),
      )}
    </group>
  );
}
