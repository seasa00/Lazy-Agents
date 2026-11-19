'use client';

import { RoundedBox } from '@react-three/drei';

export function Plant({
  position,
  night = false,
  scale = 1,
}: {
  position: [number, number, number];
  night?: boolean;
  scale?: number;
}) {
  return (
    <group position={position} scale={scale}>
      <RoundedBox
        position={[0, 0.25, 0]}
        args={[0.55, 0.46, 0.52]}
        radius={0.09}
        smoothness={2}
        castShadow
      >
        <meshStandardMaterial
          color={night ? '#786250' : '#ad8060'}
          roughness={0.9}
        />
      </RoundedBox>
      {[
        [-0.23, 0.8, 0],
        [0.21, 0.91, 0.04],
        [0, 1.16, -0.04],
        [-0.04, 0.93, 0.2],
        [0.08, 0.82, -0.2],
      ].map(([x, y, z], index) => (
        <mesh
          key={index}
          position={[x, y, z]}
          rotation={[0, index * 0.7, (index % 2 ? -1 : 1) * 0.36]}
          castShadow
        >
          <coneGeometry args={[0.22, 0.72, 5]} />
          <meshStandardMaterial
            color={
              night
                ? index % 2
                  ? '#5d7b6c'
                  : '#738b75'
                : index % 2
                  ? '#75917c'
                  : '#8ea187'
            }
            roughness={0.94}
          />
        </mesh>
      ))}
    </group>
  );
}
