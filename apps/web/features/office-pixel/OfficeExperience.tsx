'use client';

import dynamic from 'next/dynamic';
import './index.css';

// Browser APIs belong to this client-only leaf, never the Next.js server render.
const OfficeExperienceView = dynamic(() => import('./OfficeExperienceView'), {
  ssr: false,
});
export default function OfficeExperience({ projectId, runId, cursor, connection, runState }: {
  projectId?: string;
  runId?: string;
  cursor?: number;
  connection?: string;
  runState?: string;
}) {
  return <OfficeExperienceView projectId={projectId} runId={runId} cursor={cursor} connection={connection} runState={runState} />;
}
