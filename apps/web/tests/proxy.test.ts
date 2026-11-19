// Node Web APIs exercise the server adapter without any backend rule implementation.
// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import { proxy } from '@/lib/api/proxy';
afterEach(() => vi.unstubAllEnvs());
describe('same-origin loopback proxy', () => {
  it('validates actual Host when Next constructs a canonical localhost URL', async () => {
    const req = new Request('http://localhost:3011/api/backend/projects', {
      headers: { host: '127.0.0.1:3011', origin: 'http://127.0.0.1:3011' },
    });
    expect(
      (
        await proxy(
          req,
          'projects',
          vi.fn(async () => Response.json([])),
        )
      ).status,
    ).toBe(200);
  });
  it('rejects a remote Host even with a local canonical URL', async () => {
    expect(
      (
        await proxy(
          new Request('http://localhost:3011/api/backend/projects', {
            headers: { host: 'evil.example', origin: 'http://evil.example' },
          }),
          'projects',
        )
      ).status,
    ).toBe(403);
  });
  it('forwards mutation version/key and maps the validated origin', async () => {
    const fetcher = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >(async () => Response.json({ status: 'applied' }));
    const req = new Request(
      'http://127.0.0.1:3000/api/backend/projects/p/plan',
      {
        method: 'POST',
        headers: {
          origin: 'http://127.0.0.1:3000',
          'idempotency-key': 'k',
          'content-type': 'application/json',
        },
        body: '{"expected_version":3}',
      },
    );
    expect((await proxy(req, 'projects/p/plan', fetcher)).status).toBe(200);
    const init = fetcher.mock.calls[0][1]!;
    expect(new Headers(init.headers).get('origin')).toBe(
      'http://127.0.0.1:8000',
    );
    expect(new Headers(init.headers).get('idempotency-key')).toBe('k');
    expect(init.body).toBe('{"expected_version":3}');
  });
  it('forwards replay cursor and Last-Event-ID without buffering', async () => {
    const fetcher = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >(
      async () =>
        new Response('id: 11\n\n', {
          headers: { 'content-type': 'text/event-stream' },
        }),
    );
    const req = new Request(
      'http://localhost:3000/api/backend/projects/p/events?after=10',
      { headers: { 'last-event-id': '12' } },
    );
    const result = await proxy(req, 'projects/p/events', fetcher);
    expect(String(fetcher.mock.calls[0][0])).toContain('?after=10');
    expect(
      new Headers(fetcher.mock.calls[0][1]!.headers).get('last-event-id'),
    ).toBe('12');
    expect(await result.text()).toBe(': keepalive\n\nid: 11\n\n');
  });
  it('rejects cross-origin requests before contacting backend', async () => {
    const fetcher = vi.fn();
    expect(
      (
        await proxy(
          new Request('http://localhost:3000/api/backend/projects', {
            headers: { origin: 'http://evil.example' },
          }),
          'projects',
          fetcher,
        )
      ).status,
    ).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('rejects cross-site browser requests', async () => {
    expect(
      (
        await proxy(
          new Request('http://localhost:3000/api/backend/projects', {
            headers: { 'sec-fetch-site': 'cross-site' },
          }),
          'projects',
        )
      ).status,
    ).toBe(403);
  });
  it('rejects remote hosts', async () => {
    expect(
      (
        await proxy(
          new Request('http://evil.example/api/backend/projects'),
          'projects',
        )
      ).status,
    ).toBe(403);
  });
  it('does not accept arbitrary upstream paths', async () => {
    expect(
      (
        await proxy(
          new Request('http://localhost:3000/api/backend/admin'),
          'admin',
        )
      ).status,
    ).toBe(404);
  });
  it('requires loopback backend configuration', async () => {
    vi.stubEnv('AI_OFFICE_API_URL', 'https://remote.example');
    expect(
      (
        await proxy(
          new Request('http://localhost:3000/api/backend/projects'),
          'projects',
        )
      ).status,
    ).toBe(500);
  });
  it('reports unavailable FastAPI clearly', async () => {
    const response = await proxy(
      new Request('http://localhost:3000/api/backend/projects'),
      'projects',
      vi.fn(async () => {
        throw new Error('internal credential detail');
      }),
    );
    expect(response.status).toBe(502);
    expect(await response.text()).not.toContain('credential');
  });
  it('never forwards browser cookies or authorization to backend', async () => {
    const fetcher = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >(async () => Response.json([]));
    await proxy(
      new Request('http://localhost:3000/api/backend/projects', {
        headers: { authorization: 'secret', cookie: 'token=secret' },
      }),
      'projects',
      fetcher,
    );
    const headers = new Headers(fetcher.mock.calls[0][1]!.headers);
    expect(headers.has('authorization')).toBe(false);
    expect(headers.has('cookie')).toBe(false);
  });
});
