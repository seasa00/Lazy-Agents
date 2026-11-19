'use client';

import { RoundedBox } from '@react-three/drei';

type DeskProps = {
  position: [number, number, number];
  width: number;
  depth: number;
  drawerSide?: 'left' | 'right' | 'none';
  night: boolean;
};

export function Desk({
  position,
  width,
  depth,
  drawerSide = 'none',
  night,
}: DeskProps) {
  const wood = night ? '#75583f' : '#a87950';
  const darkWood = night ? '#533f33' : '#79543b';
  return (
    <group position={position}>
      <RoundedBox
        position={[0, 0.94, 0]}
        args={[width, 0.16, depth]}
        radius={0.07}
        smoothness={3}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial color={wood} roughness={0.82} />
      </RoundedBox>
      {[-1, 1].map((side) => (
        <mesh
          key={side}
          position={[side * (width / 2 - 0.16), 0.43, 0]}
          castShadow
          receiveShadow
        >
          <boxGeometry args={[0.13, 0.84, depth - 0.1]} />
          <meshStandardMaterial color={darkWood} roughness={0.9} />
        </mesh>
      ))}
      {drawerSide !== 'none' && (
        <group
          position={[
            drawerSide === 'left' ? -width / 2 + 0.4 : width / 2 - 0.4,
            0,
            0,
          ]}
        >
          <RoundedBox
            position={[0, 0.55, 0]}
            args={[0.66, 0.64, depth - 0.16]}
            radius={0.045}
            smoothness={2}
            castShadow
          >
            <meshStandardMaterial color={darkWood} roughness={0.92} />
          </RoundedBox>
          {[0.43, 0.62].map((y) => (
            <mesh key={y} position={[0, y, depth / 2 - 0.07]}>
              <boxGeometry args={[0.22, 0.025, 0.025]} />
              <meshStandardMaterial
                color={night ? '#c6a574' : '#d7b381'}
                roughness={0.6}
              />
            </mesh>
          ))}
        </group>
      )}
    </group>
  );
}
