'use client';
import { useEffect, useState } from 'react';
import { getArtifact } from '@/lib/api/client';
import type { Artifact } from '@/lib/api/types';
export function Diff({ content }: { content: string }) {
  return (
    <pre className="diff" aria-label="File diff">
      {content.split('\n').map((line, i) => (
        <span
          key={i}
          className={
            line.startsWith('+')
              ? 'added'
              : line.startsWith('-')
                ? 'removed'
                : ''
          }
        >
          {line || ' '}
          {'\n'}
        </span>
      ))}
    </pre>
  );
}
export function ArtifactViewer({
  projectId,
  runId,
  submissionId,
  path,
  stale = false,
  close,
}: {
  projectId: string;
  runId: string;
  submissionId: string;
  path: string;
  stale?: boolean;
  close: () => void;
}) {
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true;
    setArtifact(null);
    setError(null);
    void getArtifact(projectId, runId, submissionId, path)
      .then((a) => {
        if (live) setArtifact(a);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [projectId, runId, submissionId, path, retry]);
  return (
    <section className="artifact" aria-label="Artifact viewer">
      <div className="page-heading">
        <h4>Artifact · {path}</h4>
        <button onClick={close}>Close artifact</button>
      </div>
      {stale && (
        <p className="warning">
          Stale evidence: retained historical content, not current workspace
          state.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          Artifact unavailable: {error}{' '}
          <button onClick={() => setRetry((v) => v + 1)}>Retry artifact</button>
        </p>
      )}
      {!artifact && !error && <p>Loading protected immutable artifact…</p>}
      {artifact && (
        <>
          <dl>
            <dt>Artifact ID</dt>
            <dd>
              <code>{artifact.artifact_id}</code>
            </dd>
            <dt>Task / attempt</dt>
            <dd>
              {artifact.task_id} / {artifact.attempt_id}
            </dd>
            <dt>Submission / version</dt>
            <dd>
              {artifact.submission_id} / {artifact.version}
            </dd>
            <dt>Content hash</dt>
            <dd>
              <code>{artifact.content_hash}</code>
            </dd>
            <dt>Created</dt>
            <dd>
              {artifact.created_at ||
                'Unavailable (capture contract has no timestamp)'}
            </dd>
          </dl>
          <p className="muted">
            Backend redaction applies to displayed text. Hashes identify the
            original immutable capture; this viewer does not read the live
            filesystem.
          </p>
          <h5>Immutable file diff · {artifact.path}</h5>
          <Diff content={artifact.diff} />
          <details>
            <summary>Captured text</summary>
            <pre>{artifact.content}</pre>
          </details>
        </>
      )}
    </section>
  );
}
