'use client';

import type { OfficeTheme } from '../types';

export function OfficeLighting({ theme }: { theme: OfficeTheme }) {
  const night = theme === 'night';
  return (
    <>
      <ambientLight
        intensity={night ? 1.2 : 1.45}
        color={night ? '#a8b9d0' : '#fff0d3'}
      />
      <hemisphereLight
        args={[
          night ? '#8094b2' : '#fff8e9',
          night ? '#334154' : '#89745e',
          night ? 0.9 : 0.7,
        ]}
      />
      <directionalLight
        position={[-5, 9, 7]}
        intensity={night ? 0.9 : 2.1}
        color={night ? '#aabedb' : '#fff0d6'}
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-9}
        shadow-camera-right={9}
        shadow-camera-top={9}
        shadow-camera-bottom={-9}
        shadow-bias={-0.0003}
      />
    </>
  );
}
