import type {
  Acknowledgement,
  Action,
  DomainEvent,
  Snapshot,
} from '../api/types';
export type Connection =
  'connecting' | 'connected' | 'disconnected' | 'resetting';
export interface PendingCommand {
  key: string;
  action: Action;
  status: 'sending' | 'pending' | 'applied' | 'uncertain';
  baseline: number;
  acknowledgement?: Acknowledgement;
}
export interface State {
  snapshot: Snapshot | null;
  cursor: number;
  events: DomainEvent[];
  liveEvents: DomainEvent[]; // Ephemeral visual acknowledgements, never persisted.
  selectedTask: string | null;
  pending: Record<string, PendingCommand>;
  connection: Connection;
  streamError: string | null;
  error: string | null;
}
export const initialState: State = {
  snapshot: null,
  cursor: 0,
  events: [],
  liveEvents: [],
  selectedTask: null,
  pending: {},
  connection: 'connecting',
  streamError: null,
  error: null,
};
export type Update =
  | { type: 'snapshot'; snapshot: Snapshot; reset?: boolean }
  | { type: 'event'; event: DomainEvent; live?: boolean }
  | { type: 'connection'; connection: Connection }
  | { type: 'select'; id: string | null }
  | { type: 'error'; message: string | null }
  | { type: 'stream-error'; message: string | null }
  | { type: 'sending'; command: PendingCommand }
  | { type: 'ack'; key: string; ack: Acknowledgement }
  | { type: 'settled'; key: string }
  | { type: 'uncertain'; key: string };
export function reducer(state: State, update: Update): State {
  switch (update.type) {
    case 'snapshot': {
      if (
        !update.reset &&
        state.snapshot &&
        (update.snapshot.project.version < state.snapshot.project.version ||
          update.snapshot.event_cursor < state.snapshot.event_cursor)
      )
        return state;
      return {
        ...state,
        snapshot: update.snapshot,
        cursor:
          update.reset || !state.snapshot
            ? update.snapshot.event_cursor
            : state.cursor,
        events: update.reset ? [] : state.events,
        liveEvents: update.reset ? [] : state.liveEvents,
        selectedTask:
          state.selectedTask &&
          update.snapshot.project.tasks.some((t) => t.id === state.selectedTask)
            ? state.selectedTask
            : null,
      };
    }
    case 'event':
      if (
        !state.snapshot ||
        update.event.project_id !== state.snapshot.project.id ||
        update.event.sequence <= state.cursor ||
        Boolean(
          update.event.event_id &&
          state.events.some((e) => e.event_id === update.event.event_id),
        )
      )
        return state;
      // Domain events are often deltas, not complete state. Refresh the snapshot in the controller.
      return {
        ...state,
        cursor: update.event.sequence,
        events: [...state.events, update.event].slice(-250),
        liveEvents:
          update.live && update.event.event_id
            ? [...state.liveEvents, update.event].slice(-32)
            : state.liveEvents,
      };
    case 'connection':
      return {
        ...state,
        connection: update.connection,
        liveEvents: update.connection === 'connected' ? state.liveEvents : [],
        streamError:
          update.connection === 'connected' ? null : state.streamError,
      };
    case 'stream-error':
      return { ...state, streamError: update.message };
    case 'select':
      return { ...state, selectedTask: update.id };
    case 'error':
      return { ...state, error: update.message };
    case 'sending':
      return {
        ...state,
        pending: { ...state.pending, [update.command.key]: update.command },
        error: null,
      };
    case 'ack': {
      const command = state.pending[update.key];
      if (
        !command ||
        update.ack.command_id !== update.key ||
        update.ack.project_id !== state.snapshot?.project.id
      )
        return state;
      return {
        ...state,
        pending: {
          ...state.pending,
          [update.key]: {
            ...command,
            status: update.ack.status === 'pending' ? 'pending' : 'applied',
            acknowledgement: update.ack,
          },
        },
      };
    }
    case 'settled': {
      const pending = { ...state.pending };
      delete pending[update.key];
      return { ...state, pending };
    }
    case 'uncertain': {
      const command = state.pending[update.key];
      return command
        ? {
            ...state,
            pending: {
              ...state.pending,
              [update.key]: { ...command, status: 'uncertain' },
            },
          }
        : state;
    }
  }
}
