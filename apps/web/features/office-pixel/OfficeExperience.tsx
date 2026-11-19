'use client';

import dynamic from 'next/dynamic';
import './index.css';

// Browser APIs belong to this client-only leaf, never the Next.js server render.
const OfficeExperienceView = dynamic(() => import('./OfficeExperienceView'), {
  ssr: false,
});
export default function OfficeExperience() {
  return <OfficeExperienceView />;
}
