import { describe, expect, it, vi } from 'vitest';
import { connect, consume, frames, SnapshotReset } from '@/lib/events/stream';
import { event } from './fixtures';
function response(text: string) {
  return new Response(
    new ReadableStream({
      start(c) {
        c.enqueue(new TextEncoder().encode(text));
        c.close();
      },
    }),
    { headers: { 'content-type': 'text/event-stream' } },
  );
}
const frame = (id: number) =>
  `id: ${id}\nevent: domain\ndata: ${JSON.stringify(event(id))}\n\n`;
describe('committed SSE transport', () => {
  it('parses frames and ignores keepalive comments', async () => {
    const result = [];
    for await (const f of frames(response(': keepalive\n\n' + frame(11)).body!))
      result.push(f);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('11');
  });
  it('handles split UTF-8, CRLF, and multiline data', async () => {
    const bytes = new TextEncoder().encode(
      'id: 11\r\nevent: domain\r\ndata: café\r\ndata: second\r\n\r\n',
    );
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        for (const b of bytes) c.enqueue(new Uint8Array([b]));
        c.close();
      },
    });
    const result = [];
    for await (const f of frames(stream)) result.push(f);
    expect(result[0].data).toBe('café\nsecond');
  });
  it('delivers ordered replay envelopes', async () => {
    const events: number[] = [];
    await consume(response(frame(11) + frame(13)), 'p1', (e) =>
      events.push(e.sequence),
    );
    expect(events).toEqual([11, 13]);
  });
  it('recognizes unavailable cursors', async () => {
    await expect(
      consume(new Response('', { status: 409 }), 'p1', () => {}),
    ).rejects.toBeInstanceOf(SnapshotReset);
  });
  it('rejects mismatched frame/domain IDs', async () => {
    await expect(
      consume(response(frame(11).replace('id: 11', 'id: 12')), 'p1', () => {}),
    ).rejects.toBeInstanceOf(SnapshotReset);
  });
  it('rejects cross-project envelopes', async () => {
    await expect(
      consume(response(frame(11)), 'other', () => {}),
    ).rejects.toBeInstanceOf(SnapshotReset);
  });
  it('connects from snapshot cursor and reconnects with Last-Event-ID', async () => {
    const abort = new AbortController();
    let cursor = 10;
    const urls: string[] = [];
    const ids: Array<string | null> = [];
    const statuses: string[] = [];
    const fetcher = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        urls.push(String(input));
        ids.push(new Headers(init?.headers).get('Last-Event-ID'));
        return response(frame(fetcher.mock.calls.length === 1 ? 11 : 12));
      },
    );
    await connect({
      projectId: 'p1',
      cursor: () => cursor,
      signal: abort.signal,
      delay: 1,
      fetcher,
      event: (e) => {
        cursor = e.sequence;
        if (cursor === 12) abort.abort();
      },
      status: (s) => statuses.push(s),
      reset: async () => {},
      error: () => {},
    });
    expect(urls[0]).toContain('after=10');
    expect(ids).toEqual([null, '11']);
    expect(statuses).toContain('disconnected');
  });
  it('resets snapshot and reconnects with the new cursor', async () => {
    const abort = new AbortController();
    let cursor = 10;
    const statuses: string[] = [];
    let calls = 0;
    const fetcher = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >(async () =>
      ++calls === 1 ? new Response('', { status: 409 }) : response(frame(21)),
    );
    const reset = vi.fn(async () => {
      cursor = 20;
    });
    await connect({
      projectId: 'p1',
      cursor: () => cursor,
      signal: abort.signal,
      delay: 1,
      fetcher,
      event: () => abort.abort(),
      status: (s) => statuses.push(s),
      reset,
      error: () => {},
    });
    expect(reset).toHaveBeenCalledOnce();
    expect(statuses).toContain('resetting');
    expect(String(fetcher.mock.calls[1][0])).toContain('after=20');
    expect(
      new Headers(fetcher.mock.calls[1][1]?.headers).get('Last-Event-ID'),
    ).toBe('20');
  });
  it('stops reconnecting on view teardown', async () => {
    const abort = new AbortController();
    abort.abort();
    const fetcher = vi.fn();
    await connect({
      projectId: 'p1',
      cursor: () => 10,
      signal: abort.signal,
      fetcher,
      event: () => {},
      status: () => {},
      reset: async () => {},
      error: () => {},
    });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
