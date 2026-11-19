import { describe, expect, it } from 'vitest';
import { initialState, reducer } from '@/lib/state/reducer';
import { copy, event, snapshot } from './fixtures';
describe('authoritative project reducer', () => {
  const loaded = () =>
    reducer(initialState, { type: 'snapshot', snapshot: copy(snapshot) });
  it('loads the snapshot and exclusive cursor', () => {
    const state = loaded();
    expect(state.snapshot).toEqual(snapshot);
    expect(state.cursor).toBe(10);
  });
  it('records a committed event without synthesizing task state', () => {
    const state = reducer(loaded(), { type: 'event', event: event(11) });
    expect(state.events).toHaveLength(1);
    expect(state.snapshot?.project.tasks[0].status).toBe('todo');
    expect(state.cursor).toBe(11);
  });
  it('ignores duplicate events', () => {
    const first = reducer(loaded(), { type: 'event', event: event(11) });
    expect(reducer(first, { type: 'event', event: event(11) })).toBe(first);
  });
  it('never rolls cursor backward on out-of-order events, allowing sequence gaps', () => {
    const state = reducer(loaded(), { type: 'event', event: event(14) });
    expect(reducer(state, { type: 'event', event: event(12) })).toBe(state);
    expect(state.cursor).toBe(14);
  });
  it('rejects other-project events', () => {
    const state = loaded();
    expect(
      reducer(state, {
        type: 'event',
        event: { ...event(11), project_id: 'other' },
      }),
    ).toBe(state);
  });
  it('refreshes task status from the backend only', () => {
    const state = reducer(loaded(), { type: 'event', event: event(11) });
    const next = copy(snapshot);
    next.project.version++;
    next.project.tasks[0].status = 'done';
    next.event_cursor = 11;
    expect(
      reducer(state, { type: 'snapshot', snapshot: next }).snapshot?.project
        .tasks[0].status,
    ).toBe('done');
  });
  it('does not advance received-event cursor just because refresh sees later commits', () => {
    const next = copy(snapshot);
    next.event_cursor = 20;
    expect(reducer(loaded(), { type: 'snapshot', snapshot: next }).cursor).toBe(
      10,
    );
  });
  it('reset replaces cursor and clears replay UI entries', () => {
    const state = reducer(loaded(), { type: 'event', event: event(11) });
    const next = copy(snapshot);
    next.event_cursor = 14;
    const reset = reducer(state, {
      type: 'snapshot',
      snapshot: next,
      reset: true,
    });
    expect(reset.events).toEqual([]);
    expect(reset.cursor).toBe(14);
  });
  it('an explicit reset can replace a cursor from a restored database', () => {
    const next = copy(snapshot);
    next.project.version = 1;
    next.event_cursor = 1;
    const reset = reducer(loaded(), {
      type: 'snapshot',
      snapshot: next,
      reset: true,
    });
    expect(reset.snapshot).toEqual(next);
    expect(reset.cursor).toBe(1);
  });
  it('discards stale snapshot responses', () => {
    const stale = copy(snapshot);
    stale.project.version = 2;
    expect(reducer(loaded(), { type: 'snapshot', snapshot: stale })).toEqual(
      loaded(),
    );
  });
  it('ignores a stale command response without a matching pending key', () => {
    const state = loaded();
    expect(
      reducer(state, {
        type: 'ack',
        key: 'old',
        ack: {
          command_id: 'old',
          project_id: 'p1',
          status: 'applied',
          project_version: 1,
        },
      }),
    ).toBe(state);
  });
  it('acknowledgment never overrides snapshot versions or state', () => {
    const state = reducer(loaded(), {
      type: 'sending',
      command: {
        key: 'pause',
        action: 'pause',
        status: 'sending',
        baseline: 3,
      },
    });
    const next = reducer(state, {
      type: 'ack',
      key: 'pause',
      ack: {
        command_id: 'pause',
        project_id: 'p1',
        status: 'pending',
        project_version: 2,
      },
    });
    expect(next.snapshot).toEqual(snapshot);
    expect(next.pending.pause.status).toBe('pending');
  });
  it('records an uncertain command for same-key retry', () => {
    const state = reducer(loaded(), {
      type: 'sending',
      command: { key: 'k', action: 'start', status: 'sending', baseline: 3 },
    });
    expect(
      reducer(state, { type: 'uncertain', key: 'k' }).pending.k.status,
    ).toBe('uncertain');
  });
  it('settles UI pending state only', () => {
    const state = reducer(loaded(), {
      type: 'sending',
      command: { key: 'k', action: 'pause', status: 'sending', baseline: 3 },
    });
    const next = reducer(state, { type: 'settled', key: 'k' });
    expect(next.pending).toEqual({});
    expect(next.snapshot).toEqual(snapshot);
  });
  it('bounds logical feed entries to 250', () => {
    let state = loaded();
    for (let i = 11; i < 400; i++)
      state = reducer(state, { type: 'event', event: event(i) });
    expect(state.events).toHaveLength(250);
    expect(state.events.at(-1)?.sequence).toBe(399);
  });
});
