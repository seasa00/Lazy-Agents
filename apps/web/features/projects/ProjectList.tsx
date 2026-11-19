'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { getProjects } from '@/lib/api/client';
import type { Project } from '@/lib/api/types';
export function ProjectList() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setProjects(await getProjects());
      setError(null);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : 'Cannot load projects.',
      );
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <main>
      <div className="page-heading">
        <div>
          <p className="eyebrow">AI Office</p>
          <h1>Projects</h1>
          <p>Plan, supervise, and review work with your three agents.</p>
        </div>
        <Link className="button primary" href="/projects/new">
          Create project
        </Link>
      </div>
      {error && (
        <div role="alert" className="error">
          {error}{' '}
          <button onClick={() => void load()}>Retry loading projects</button>
        </div>
      )}
      {!projects && !error && <p role="status">Loading projects…</p>}
      {projects?.length === 0 && (
        <section className="panel">
          <h2>No projects yet</h2>
          <p>Create a project to request your first Manager plan.</p>
        </section>
      )}
      <div className="project-grid">
        {projects?.map((project) => (
          <Link
            className="project-card"
            key={project.id}
            href={`/projects/${encodeURIComponent(project.id)}`}
          >
            <h2>{project.name}</h2>
            <p>{project.goal}</p>
            <span className="badge">
              {project.runs.at(-1)?.status.replaceAll('_', ' ') ||
                'Ready to plan'}
            </span>
            <p className="muted">{project.tasks.length} tasks</p>
            <span>Open project →</span>
          </Link>
        ))}
      </div>
    </main>
  );
}
