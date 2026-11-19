'use client';

import dynamic from 'next/dynamic';
import type { OfficeTheme } from './types';

const OfficeCanvasClient = dynamic(() => import('./OfficeCanvasClient'), {
  ssr: false,
  loading: () => <div className="office-canvas-loading" aria-hidden="true" />,
});

export function OfficeCanvas({ theme }: { theme: OfficeTheme }) {
  return (
    <div className="office-canvas" data-scene-layout="fixed" aria-hidden="true">
      <OfficeCanvasClient theme={theme} />
    </div>
  );
}
