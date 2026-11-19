'use client';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  APIError,
  getPermissions,
  getSnapshot,
  sendCommand,
} from '../api/client';
import type { Action, Command, Permission, Snapshot } from '../api/types';
import { connect } from '../events/stream';
import { initialState, reducer, type State } from './reducer';
interface Controller {
  state: State;
  permissions: Permission[];
  command: (action: Action, extra?: Partial<Command>) => Promise<void>;
  retry: () => Promise<void>;
  refresh: () => Promise<void>;
  select: (id: string | null) => void;
}
const Context = createContext<Controller | null>(null);
export function ProjectProvider({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const current = useRef<Snapshot | null>(null);
  const cursor = useRef(0);
  const animationBoundary = useRef(0);
  const alive = useRef(false);
  const loading = useRef<Promise<void> | null>(null);
  const dirty = useRef(false);
  const uncertain = useRef<{
    action: Action;
    body: Command;
    key: string;
    runId?: string;
  } | null>(null);
  const busy = useRef(false);
  const refresh = useCallback(async () => {
    dirty.current = true;
    if (loading.current) return loading.current;
    loading.current = (async () => {
      while (dirty.current && alive.current) {
        dirty.current = false;
        const snapshot = await getSnapshot(id);
        if (!alive.current) return;
        if (
          !current.current ||
          (snapshot.project.version >= current.current.project.version &&
            snapshot.event_cursor >= current.current.event_cursor)
        ) {
          current.current = snapshot;
          dispatch({ type: 'snapshot', snapshot });
          const run =
            snapshot.project.runs.find(
              (r) => r.id === snapshot.project.active_run_id,
            ) || snapshot.project.runs.at(-1);
          if (run) {
            const decisions = await getPermissions(id, run.id);
            if (alive.current) setPermissions(decisions);
          } else setPermissions([]);
        }
      }
    })().finally(() => {
      loading.current = null;
    });
    return loading.current;
  }, [id]);
  useEffect(() => {
    alive.current = true;
    const abort = new AbortController();
    void (async () => {
      // Initial errors are retried with a visible state; no mutation is retried automatically.
      await connect({
        projectId: id,
        cursor: () => cursor.current,
        signal: abort.signal,
        status: (connection) => {
          if (alive.current) dispatch({ type: 'connection', connection });
        },
        error: (message) => {
          if (alive.current) dispatch({ type: 'stream-error', message });
        },
        reset: async () => {
          await loading.current;
          const snapshot = await getSnapshot(id);
          if (!alive.current) return;
          current.current = snapshot;
          cursor.current = snapshot.event_cursor;
          dispatch({ type: 'snapshot', snapshot, reset: true });
          await refresh();
        },
        fetcher: async (input, init) => {
          const initial = !current.current;
          // Sample a fresh committed cursor before EVERY connection. Replay still
          // reaches the feed, but only events committed after this sample animate.
          await refresh();
          animationBoundary.current = current.current!.event_cursor;
          if (initial) {
            cursor.current = current.current!.event_cursor;
            return fetch(
              `/api/backend/projects/${encodeURIComponent(id)}/events?after=${cursor.current}`,
              init,
            );
          }
          return fetch(input, init);
        },
        event: (event) => {
          if (!alive.current || event.sequence <= cursor.current) return;
          cursor.current = event.sequence;
          dispatch({
            type: 'event',
            event,
            live: event.sequence > animationBoundary.current,
          });
          void refresh().catch((error) => {
            if (alive.current)
              dispatch({ type: 'error', message: error.message });
          });
        },
      });
    })();
    return () => {
      alive.current = false;
      abort.abort();
    };
  }, [id, refresh]);
  useEffect(() => {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const run =
      snapshot.project.runs.find(
        (r) => r.id === snapshot.project.active_run_id,
      ) || snapshot.project.runs.at(-1);
    for (const command of Object.values(state.pending)) {
      if (command.status === 'sending' || command.status === 'uncertain')
        continue;
      const ack = command.acknowledgement;
      if (
        !ack ||
        snapshot.project.version < (ack.project_version ?? command.baseline)
      )
        continue;
      const settled =
        command.status === 'applied' ||
        !run ||
        (command.action === 'pause' &&
          [
            'paused',
            'canceled',
            'completed',
            'failed',
            'waiting_for_user',
          ].includes(run.status)) ||
        (command.action === 'plan' &&
          [
            'awaiting_approval',
            'waiting_for_user',
            'failed',
            'canceled',
          ].includes(run.status)) ||
        (['start', 'resume'].includes(command.action) &&
          (Boolean(run.workflow?.pending) ||
            Boolean(run.workflow?.pending_permissions.length) ||
            [
              'paused',
              'completed',
              'failed',
              'canceled',
              'waiting_for_user',
            ].includes(run.status)));
      if (settled) dispatch({ type: 'settled', key: command.key });
    }
  }, [state.snapshot, state.pending]);
  const execute = useCallback(
    async (job: NonNullable<typeof uncertain.current>) => {
      if (busy.current) return;
      busy.current = true;
      dispatch({
        type: 'sending',
        command: {
          key: job.key,
          action: job.action,
          status: 'sending',
          baseline: job.body.expected_version,
        },
      });
      try {
        const ack = await sendCommand(
          id,
          job.runId,
          job.action,
          job.body,
          job.key,
        );
        uncertain.current = null;
        await refresh();
        // Keep sending visible until the owned refresh finishes; otherwise a new
        // button click can race busy.current and be silently ignored.
        dispatch({ type: 'ack', key: job.key, ack });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Backend request failed.';
        if (error instanceof APIError && error.uncertain) {
          uncertain.current = job;
          dispatch({ type: 'uncertain', key: job.key });
        } else {
          uncertain.current = null;
          dispatch({ type: 'settled', key: job.key });
        }
        try {
          await refresh();
        } catch {
          /* Retain the original actionable command error. */
        }
        dispatch({ type: 'error', message });
      } finally {
        busy.current = false;
      }
    },
    [id, refresh],
  );
  const command = useCallback(
    async (action: Action, extra: Partial<Command> = {}) => {
      if (!current.current || uncertain.current) return;
      const project = current.current.project;
      const run =
        project.runs.find((r) => r.id === project.active_run_id) ||
        project.runs.at(-1);
      await execute({
        action,
        runId: run?.id,
        body: {
          reason: '',
          quiescent: false,
          ...extra,
          expected_version: project.version,
        },
        key: crypto.randomUUID(),
      });
    },
    [execute],
  );
  return (
    <Context.Provider
      value={{
        state,
        permissions,
        command,
        refresh: async () => {
          try {
            await refresh();
            dispatch({ type: 'error', message: null });
          } catch (error) {
            dispatch({
              type: 'error',
              message:
                error instanceof Error
                  ? error.message
                  : 'Cannot refresh authoritative state.',
            });
          }
        },
        retry: async () => {
          if (uncertain.current) await execute(uncertain.current);
        },
        select: (id) => dispatch({ type: 'select', id }),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useProject() {
  const value = useContext(Context);
  if (!value) throw new Error('ProjectProvider required');
  return value;
}
