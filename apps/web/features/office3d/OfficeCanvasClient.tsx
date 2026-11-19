'use client';

import { Canvas } from '@react-three/fiber';
import { Suspense } from 'react';
import { CameraRig } from './CameraRig';
import { OfficeScene3D } from './OfficeScene3D';
import type { OfficeTheme } from './types';

export default function OfficeCanvasClient({ theme }: { theme: OfficeTheme }) {
  return (
    <Canvas
      orthographic
      shadows="percentage"
      dpr={[1, 1.5]}
      frameloop="demand"
      camera={{ position: [10, 9, 13], near: 0.1, far: 80, zoom: 54 }}
      gl={{ antialias: true, alpha: false, powerPreference: 'low-power' }}
      fallback={<div className="office-canvas-fallback" />}
    >
      <CameraRig />
      <Suspense fallback={null}>
        <OfficeScene3D theme={theme} />
      </Suspense>
    </Canvas>
  );
}
