import {
  act,
  render,
  screen,
  waitFor,
  fireEvent,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectProvider, useProject } from '@/lib/state/context';
import { copy, event, snapshot } from './fixtures';
import { APIError } from '@/lib/api/client';
const mocks = vi.hoisted(() => ({
  snapshot: vi.fn(),
  permissions: vi.fn(),
  command: vi.fn(),
}));
vi.mock('@/lib/api/client', async (original) => ({
  ...(await original<object>()),
  getSnapshot: mocks.snapshot,
  getPermissions: mocks.permissions,
  sendCommand: mocks.command,
}));
let streams: Array<ReadableStreamDefaultController<Uint8Array>>;
let fetcher: ReturnType<typeof vi.fn<typeof fetch>>;
function Probe() {
  const { state, command, retry } = useProject();
  return (
    <>
      <span data-testid="version">{state.snapshot?.project.version}</span>
      <span data-testid="task">{state.snapshot?.project.tasks[0].status}</span>
      <span data-testid="cursor">{state.cursor}</span>
      <span data-testid="events">{state.events.length}</span>
      <span data-testid="live">
        {state.liveEvents.map((e) => e.sequence).join(',')}
      </span>
      <span data-testid="pending">
        {Object.values(state.pending)
          .map((p) => p.status)
          .join(',')}
      </span>
      <span data-testid="error">{state.error}</span>
      <button onClick={() => void command('pause')}>pause</button>
      <button onClick={() => void retry()}>retry</button>
    </>
  );
}
function frame(sequence: number) {
  return new TextEncoder().encode(
    `id: ${sequence}\nevent: domain\ndata: ${JSON.stringify({ ...event(sequence), event_id: `evt-${sequence}` })}\n\n`,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  streams = [];
  mocks.snapshot.mockResolvedValue(copy(snapshot));
  mocks.permissions.mockResolvedValue([]);
  fetcher = vi.fn(
    async (_input: RequestInfo | URL, init?: RequestInit) =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            streams.push(controller);
            init?.signal?.addEventListener(
              'abort',
              () => {
                try {
                  controller.close();
                } catch {}
              },
              { once: true },
            );
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      ),
  );
  vi.stubGlobal('fetch', fetcher);
});
afterEach(() => vi.unstubAllGlobals());
describe('snapshot and SSE controller', () => {
  it('loads the snapshot before opening one stream from its cursor', async () => {
    const view = render(
      <ProjectProvider id="p1">
        <Probe />
      </ProjectProvider>,
    );
    await waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
    expect(fetcher.mock.calls[0][0]).toContain('after=10');
    expect(screen.getByTestId('version')).toHaveTextContent('3');
    view.unmount();
    expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });
  it('deduplicates replay and refreshes state from the authoritative snapshot', async () => {
    render(
      <ProjectProvider id="p1">
        <Probe />
      </ProjectProvider>,
    );
    await waitFor(() => expect(streams).toHaveLength(1));
    const next = copy(snapshot);
    next.project.version = 4;
    next.project.tasks[0].status = 'review';
    next.event_cursor = 11;
    mocks.snapshot.mockResolvedValue(next);
    await act(async () => {
      streams[0].enqueue(frame(11));
      streams[0].enqueue(frame(11));
    });
    await waitFor(() =>
      expect(screen.getByTestId('task')).toHaveTextContent('review'),
    );
    expect(screen.getByTestId('events')).toHaveTextContent('1');
    expect(screen.getByTestId('cursor')).toHaveTextContent('11');
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('keeps pause pending until backend state confirms it', async () => {
    render(
      <ProjectProvider id="p1">
        <Probe />
      </ProjectProvider>,
    );
    await waitFor(() => expect(streams).toHaveLength(1));
    mocks.command.mockImplementation(
      async (_id, _run, _action, _body, key) => ({
        command_id: key,
        project_id: 'p1',
        status: 'pending',
        project_version: 3,
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    await waitFor(() =>
      expect(screen.getByTestId('pending')).toHaveTextContent('pending'),
    );
    expect(screen.getByTestId('task')).toHaveTextContent('todo');
    const paused = copy(snapshot);
    paused.project.version = 4;
    paused.project.runs[0].status = 'paused';
    paused.event_cursor = 11;
    mocks.snapshot.mockResolvedValue(paused);
    await act(async () => streams[0].enqueue(frame(11)));
    await waitFor(() =>
      expect(screen.getByTestId('pending')).toBeEmptyDOMElement(),
    );
  });
  it('refreshes on stale version rejection without automatically repeating the command', async () => {
    render(
      <ProjectProvider id="p1">
        <Probe />
      </ProjectProvider>,
    );
    await waitFor(() => expect(streams).toHaveLength(1));
    mocks.command.mockRejectedValue(
      new APIError('Stale project version. Review refreshed state.', 409),
    );
    const next = copy(snapshot);
    next.project.version = 4;
    mocks.snapshot.mockResolvedValue(next);
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    await waitFor(() =>
      expect(screen.getByTestId('error')).toHaveTextContent(
        'Stale project version',
      ),
    );
    expect(screen.getByTestId('version')).toHaveTextContent('4');
    expect(mocks.command).toHaveBeenCalledOnce();
    expect(screen.getByTestId('pending')).toBeEmptyDOMElement();
  });
  it('retries an unknown outcome with the exact original body and key', async () => {
    render(
      <ProjectProvider id="p1">
        <Probe />
      </ProjectProvider>,
    );
    await waitFor(() => expect(streams).toHaveLength(1));
    mocks.command.mockRejectedValueOnce(
      new APIError('Backend unavailable.', 502, true),
    );
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    await waitFor(() =>
      expect(screen.getByTestId('pending')).toHaveTextContent('uncertain'),
    );
    const original = mocks.command.mock.calls[0];
    mocks.command.mockImplementation(
      async (_id, _run, _action, _body, key) => ({
        command_id: key,
        project_id: 'p1',
        status: 'pending',
        project_version: 3,
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    await waitFor(() => expect(mocks.command).toHaveBeenCalledTimes(2));
    expect(mocks.command.mock.calls[1]).toEqual(original);
  });
  it('keeps command sending visible until the refresh finishes', async () => {
    render(
      <ProjectProvider id="p1">
        <Probe />
      </ProjectProvider>,
    );
    await waitFor(() => expect(streams).toHaveLength(1));
    let release!: (value: typeof snapshot) => void;
    mocks.snapshot.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    mocks.command.mockImplementation(
      async (_id, _run, _action, _body, key) => ({
        command_id: key,
        project_id: 'p1',
        status: 'applied',
        project_version: 3,
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    await waitFor(() => expect(mocks.command).toHaveBeenCalled());
    expect(screen.getByTestId('pending')).toHaveTextContent('sending');
    await act(async () => release(copy(snapshot)));
    await waitFor(() =>
      expect(screen.getByTestId('pending')).toHaveTextContent(/^$/),
    );
    fireEvent.click(screen.getByRole('button', { name: 'pause' }));
    await waitFor(() => expect(mocks.command).toHaveBeenCalledTimes(2));
  });
});

it('samples a fresh reconnect snapshot to suppress backlog while retaining feed replay', async () => {
  render(
    <ProjectProvider id="p1">
      <Probe />
    </ProjectProvider>,
  );
  await waitFor(() => expect(streams).toHaveLength(1));
  await act(async () => streams[0].enqueue(frame(11)));
  expect(screen.getByTestId('live')).toHaveTextContent('11');
  const next = copy(snapshot);
  next.event_cursor = 13;
  next.project.version = 4;
  mocks.snapshot.mockResolvedValue(next);
  await act(async () => streams[0].close());
  await waitFor(() => expect(streams).toHaveLength(2), { timeout: 3000 });
  expect(
    new Headers(fetcher.mock.calls[1][1]?.headers).get('Last-Event-ID'),
  ).toBe('11');
  await act(async () => {
    streams[1].enqueue(frame(12));
    streams[1].enqueue(frame(13));
  });
  expect(screen.getByTestId('events')).toHaveTextContent('3');
  expect(screen.getByTestId('live')).toBeEmptyDOMElement();
  await act(async () => streams[1].enqueue(frame(14)));
  expect(screen.getByTestId('live')).toHaveTextContent(/^14$/);
});
