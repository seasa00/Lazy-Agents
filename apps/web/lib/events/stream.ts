import type { DomainEvent } from '../api/types';
export class SnapshotReset extends Error {}
export interface Frame {
  id: string;
  event: string;
  data: string;
}
export async function* frames(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<Frame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let frame: Frame = { id: '', event: 'message', data: '' };
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      let index: number;
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, index).replace(/\r$/, '');
        buffer = buffer.slice(index + 1);
        if (!line) {
          if (frame.data) yield { ...frame, data: frame.data.slice(0, -1) };
          frame = { id: '', event: 'message', data: '' };
          continue;
        }
        if (line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        const field = colon < 0 ? line : line.slice(0, colon);
        const raw = colon < 0 ? '' : line.slice(colon + 1);
        const text = raw.startsWith(' ') ? raw.slice(1) : raw;
        if (field === 'data') frame.data += text + '\n';
        else if (field === 'id') frame.id = text;
        else if (field === 'event') frame.event = text;
      }
      if (
        buffer.length > 8 * 1024 * 1024 ||
        frame.data.length > 8 * 1024 * 1024
      )
        throw new SnapshotReset('Event exceeds the supported size.');
      if (done) return;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
export async function consume(
  response: Response,
  projectId: string,
  onEvent: (event: DomainEvent) => void,
) {
  if (response.status === 409)
    throw new SnapshotReset('Event cursor unavailable. Reloading snapshot.');
  if (
    !response.ok ||
    !response.body ||
    !response.headers.get('content-type')?.startsWith('text/event-stream')
  )
    throw new Error(`SSE disconnected (HTTP ${response.status}).`);
  for await (const frame of frames(response.body)) {
    if (frame.event !== 'domain') continue;
    let event: DomainEvent;
    try {
      event = JSON.parse(frame.data);
    } catch {
      throw new SnapshotReset('Malformed event. Reloading snapshot.');
    }
    if (
      event.schema_version !== 1 ||
      event.project_id !== projectId ||
      !Number.isSafeInteger(event.sequence) ||
      event.sequence < 1 ||
      String(event.sequence) !== frame.id ||
      typeof event.type !== 'string'
    )
      throw new SnapshotReset(
        'Unsupported event envelope. Reloading snapshot.',
      );
    onEvent(event);
  }
}
export interface StreamOptions {
  projectId: string;
  cursor: () => number;
  event: (event: DomainEvent) => void;
  status: (
    value: 'connecting' | 'connected' | 'disconnected' | 'resetting',
  ) => void;
  reset: () => Promise<void>;
  error: (message: string) => void;
  signal: AbortSignal;
  fetcher?: typeof fetch;
  delay?: number;
}
async function wait(signal: AbortSignal, delay: number) {
  if (signal.aborted) return;
  await new Promise<void>((resolve) => {
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', done);
      resolve();
    };
    const timer = setTimeout(done, delay);
    signal.addEventListener('abort', done, { once: true });
  });
}
export async function connect(options: StreamOptions) {
  let first = true;
  const fetcher = options.fetcher || fetch;
  while (!options.signal.aborted) {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      options.status('disconnected');
      options.error(
        'SSE disconnected: browser offline. Execution continues on the backend.',
      );
      await wait(options.signal, options.delay ?? 1000);
      continue;
    }
    options.status('connecting');
    const attempt = new AbortController();
    const abortAttempt = () => attempt.abort();
    options.signal.addEventListener('abort', abortAttempt, { once: true });
    if (typeof window !== 'undefined')
      window.addEventListener('offline', abortAttempt, { once: true });
    try {
      const cursor = options.cursor();
      const response = await fetcher(
        `/api/backend/projects/${encodeURIComponent(options.projectId)}/events?after=${cursor}`,
        {
          signal: attempt.signal,
          cache: 'no-store',
          headers: first ? {} : { 'Last-Event-ID': String(cursor) },
        },
      );
      first = false;
      if (response.ok) options.status('connected');
      await consume(response, options.projectId, options.event);
      if (!options.signal.aborted)
        throw new Error(
          'SSE disconnected. Reconnecting from the last committed event.',
        );
    } catch (error) {
      if (options.signal.aborted) return;
      if (error instanceof SnapshotReset) {
        options.status('resetting');
        options.error(error.message);
        try {
          await options.reset();
        } catch {
          options.error(
            'Snapshot reset failed: backend unavailable. Retrying.',
          );
        }
      } else {
        options.status('disconnected');
        options.error(
          error instanceof Error
            ? `SSE disconnected. ${error.message}`
            : 'SSE disconnected. Reconnecting.',
        );
      }
    } finally {
      options.signal.removeEventListener('abort', abortAttempt);
      if (typeof window !== 'undefined')
        window.removeEventListener('offline', abortAttempt);
      attempt.abort();
    }
    await wait(options.signal, options.delay ?? 1000);
  }
}
