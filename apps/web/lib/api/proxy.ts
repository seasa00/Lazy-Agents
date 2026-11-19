// Server-only HTTP/SSE forwarding. No domain mutation, state, or execution rules.
const routes =
  /^projects(?:\/[^/]+(?:\/(?:snapshot|events|plan|settings|runs\/[^/]+\/(?:approve|start|pause|resume|cancel|permission|tasks|reviews|evidence|inspection|usage|permissions|recovery|artifacts\/[^/]+)))?)?$/;
export async function proxy(
  request: Request,
  path: string,
  fetcher: typeof fetch = fetch,
): Promise<Response> {
  const incoming = new URL(request.url);
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(incoming.hostname))
    return Response.json({ detail: 'Local host required.' }, { status: 403 });
  // Next may construct request.url with localhost while the browser used 127.0.0.1.
  // Validate the actual Host authority; never trust forwarded-host/origin headers.
  const authority = new URL(
    `${incoming.protocol}//${request.headers.get('host') || incoming.host}`,
  );
  if (
    !['127.0.0.1', 'localhost', '[::1]'].includes(authority.hostname) ||
    authority.username ||
    authority.password
  )
    return Response.json({ detail: 'Local host required.' }, { status: 403 });
  const origin = request.headers.get('origin');
  if (origin && origin !== authority.origin)
    return Response.json(
      { detail: 'Cross-origin request denied.' },
      { status: 403 },
    );
  if (
    ['cross-site', 'same-site'].includes(
      request.headers.get('sec-fetch-site') || '',
    )
  )
    return Response.json(
      { detail: 'Cross-site request denied.' },
      { status: 403 },
    );
  if (
    !routes.test(path) ||
    path
      .split('/')
      .some(
        (p) => !p || p === '.' || p === '..' || !/^[a-zA-Z0-9_:.-]+$/.test(p),
      )
  )
    return Response.json({ detail: 'Unsupported API path.' }, { status: 404 });
  const backend = new URL(
    process.env.AI_OFFICE_API_URL || 'http://127.0.0.1:8000',
  );
  if (
    backend.protocol !== 'http:' ||
    !['127.0.0.1', 'localhost', '[::1]'].includes(backend.hostname) ||
    backend.username ||
    backend.password ||
    backend.pathname !== '/'
  )
    return Response.json(
      { detail: 'Backend must use a loopback HTTP URL.' },
      { status: 500 },
    );
  const target = new URL('/' + path + incoming.search, backend);
  const headers = new Headers({ Origin: backend.origin });
  for (const name of ['content-type', 'idempotency-key', 'last-event-id']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  let response: Response;
  try {
    response = await fetcher(target, {
      method: request.method,
      headers,
      body: request.method === 'POST' ? await request.text() : undefined,
      cache: 'no-store',
      signal: request.signal,
      redirect: 'error',
    });
  } catch {
    return Response.json(
      {
        detail:
          'FastAPI is unavailable. Check the backend process and loopback URL.',
      },
      { status: 502 },
    );
  }
  // Flush the HTTP stream immediately even if the backend has no new events.
  // This is a transport keepalive comment, never a fabricated DomainEvent.
  const body =
    response.ok &&
    response.headers.get('content-type')?.startsWith('text/event-stream') &&
    response.body
      ? response.body.pipeThrough(
          new TransformStream<Uint8Array, Uint8Array>({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(': keepalive\n\n'));
            },
          }),
        )
      : response.body;
  return new Response(body, {
    status: response.status,
    headers: {
      'Content-Type':
        response.headers.get('content-type') || 'application/json',
      'Cache-Control': 'no-store',
      'X-Accel-Buffering': 'no',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}
