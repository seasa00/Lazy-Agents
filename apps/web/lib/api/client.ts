import {
  apiBase,
  projectPath,
  type Acknowledgement,
  type Action,
  type Command,
  type CreateProject,
  type Permission,
  type Project,
  type Snapshot,
} from './types';
export class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public uncertain = false,
  ) {
    super(message);
    this.name = 'APIError';
  }
}
export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiBase + path, { ...init, cache: 'no-store' });
  } catch {
    throw new APIError(
      'Backend unavailable. Check FastAPI and retry.',
      0,
      init.method === 'POST',
    );
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new APIError(
      `Backend returned an invalid response (HTTP ${response.status}). Check FastAPI and the local proxy.`,
      response.status,
      init.method === 'POST',
    );
  }
  if (!response.ok || body.status === 'rejected') {
    const detail =
      body.error ||
      (typeof body.detail === 'string'
        ? body.detail
        : 'Input rejected. Check the required fields.');
    const prefix =
      response.status === 409 && detail.includes('version')
        ? 'Stale project version. State refreshed; review it before retrying. '
        : response.status === 403
          ? 'Permission denied. '
          : response.status === 502
            ? 'Backend unavailable. '
            : 'Command or request rejected. ';
    throw new APIError(
      prefix + detail,
      response.status,
      response.status === 502 && init.method === 'POST',
    );
  }
  return body as T;
}
export const getSnapshot = (id: string) =>
  request<Snapshot>(projectPath(id) + '/snapshot');
export const getProjects = () => request<Project[]>('/projects');
export const getPermissions = (id: string, runId: string) =>
  request<Permission[]>(
    `${projectPath(id)}/runs/${encodeURIComponent(runId)}/permissions`,
  );
export function createProject(body: CreateProject, key: string) {
  return request<Acknowledgement>('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
    body: JSON.stringify(body),
  });
}
export function sendCommand(
  id: string,
  runId: string | undefined,
  action: Action,
  body: Command,
  key: string,
) {
  const path =
    action === 'plan'
      ? projectPath(id) + '/plan'
      : `${projectPath(id)}/runs/${encodeURIComponent(runId!)}/${action}`;
  return request<Acknowledgement>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
    body: JSON.stringify(body),
  });
}

export const getInspection = (id: string, run: string) =>
  request<import('./types').Inspection>(
    `${projectPath(id)}/runs/${encodeURIComponent(run)}/inspection`,
  );
export const getSettings = (id: string) =>
  request<import('./types').Settings>(projectPath(id) + '/settings');
export const saveSettings = (
  id: string,
  body: import('./types').SettingsCommand,
  key: string,
) =>
  request<Acknowledgement>(projectPath(id) + '/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
    body: JSON.stringify(body),
  });
export const getArtifact = (
  id: string,
  run: string,
  submission: string,
  path: string,
) =>
  request<import('./types').Artifact>(
    `${projectPath(id)}/runs/${encodeURIComponent(run)}/artifacts/${encodeURIComponent(submission)}?path=${encodeURIComponent(path)}`,
  );
