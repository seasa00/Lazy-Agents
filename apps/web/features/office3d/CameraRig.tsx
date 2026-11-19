'use client';

import { useLayoutEffect } from 'react';
import { useThree } from '@react-three/fiber';
import { OrthographicCamera } from 'three';

export function CameraRig() {
  const { camera, size } = useThree();

  useLayoutEffect(() => {
    if (!(camera instanceof OrthographicCamera)) return;
    const aspect = size.width / Math.max(size.height, 1);
    const worldHeight = Math.max(11.8, Math.min(16, 15.5 / aspect));
    camera.zoom = size.height / worldHeight;
    camera.lookAt(0, 1.05, 0);
    camera.updateProjectionMatrix();
  }, [camera, size.height, size.width]);

  return null;
}
