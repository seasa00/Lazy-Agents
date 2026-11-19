'use client';

import { RoundedBox } from '@react-three/drei';
import type { OfficeTheme } from '../types';

type MonitorProps = {
  position: [number, number, number];
  width?: number;
  mode: 'plan' | 'code' | 'review';
  theme: OfficeTheme;
};

const screenColors = {
  plan: ['#7f9a84', '#d1a66e', '#8696a5'],
  code: ['#73b6a2', '#d59a68', '#88a4d0'],
  review: ['#c78961', '#92a184', '#9b87a1'],
};

export function Monitor({ position, width = 0.96, mode, theme }: MonitorProps) {
  const night = theme === 'night';
  const height = width * 0.62;
  const colors = screenColors[mode];
  return (
    <group position={position}>
      <mesh position={[0, 1.12, -0.02]} castShadow>
        <boxGeometry args={[0.12, 0.31, 0.1]} />
        <meshStandardMaterial
          color={night ? '#303b49' : '#56606a'}
          roughness={0.68}
        />
      </mesh>
      <RoundedBox
        position={[0, 1.42, -0.02]}
        args={[width, height, 0.12]}
        radius={0.06}
        smoothness={3}
        castShadow
      >
        <meshStandardMaterial
          color={night ? '#303944' : '#515a60'}
          roughness={0.62}
        />
      </RoundedBox>
      <RoundedBox
        position={[0, 1.42, 0.047]}
        args={[width - 0.1, height - 0.1, 0.015]}
        radius={0.025}
        smoothness={2}
      >
        <meshStandardMaterial
          color={night ? '#293847' : mode === 'code' ? '#344954' : '#d9dfd3'}
          emissive={night ? '#263d55' : mode === 'code' ? '#142a35' : '#000000'}
          emissiveIntensity={night ? 0.22 : 0.08}
          roughness={0.74}
        />
      </RoundedBox>
      {mode === 'code' ? (
        Array.from({ length: 5 }, (_, index) => (
          <RoundedBox
            key={index}
            position={[
              -width * 0.24 + (index % 2) * 0.08,
              1.59 - index * 0.09,
              0.06,
            ]}
            args={[width * (index % 2 === 0 ? 0.48 : 0.32), 0.025, 0.012]}
            radius={0.012}
            smoothness={1}
          >
            <meshStandardMaterial
              color={colors[index % colors.length]}
              roughness={0.8}
            />
          </RoundedBox>
        ))
      ) : (
        <>
          {[0, 1, 2].map((index) => (
            <group
              key={index}
              position={[-width * 0.25, 1.57 - index * 0.105, 0.06]}
            >
              <mesh position={[-0.06, 0, 0]}>
                <circleGeometry args={[0.035, 8]} />
                <meshBasicMaterial color={colors[index]} />
              </mesh>
              <RoundedBox
                position={[width * 0.08, 0, 0]}
                args={[width * 0.4, 0.024, 0.012]}
                radius={0.01}
                smoothness={1}
              >
                <meshStandardMaterial
                  color={night ? '#a6b4b8' : '#969d90'}
                  roughness={0.9}
                />
              </RoundedBox>
            </group>
          ))}
        </>
      )}
      <mesh position={[0, 0.98, -0.04]}>
        <boxGeometry args={[0.42, 0.035, 0.24]} />
        <meshStandardMaterial
          color={night ? '#4a545f' : '#656c6b'}
          roughness={0.78}
        />
      </mesh>
    </group>
  );
}
