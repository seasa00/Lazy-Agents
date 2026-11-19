import type { DomainEvent } from '@/lib/api/types';
const labels: Record<string, string> = {
  'project.created': 'Project created',
  'plan.proposed': 'Manager created plan',
  'plan.approved': 'Plan approved',
  'task.assigned': 'Task assigned',
  'submission.admitted': 'Submission created',
  'review.completed': 'Review completed',
  'revision.requested': 'Revision requested',
  'task.accepted': 'Task completed',
  'run.pause_requested': 'Pause requested',
  'run.paused': 'Run paused',
  'run.resumed': 'Run resumed',
  'run.completed': 'Run completed',
  'run.canceled': 'Run canceled',
  'run.blocked': 'Run blocked',
  'command.permission_requested': 'Permission required',
  'command.permission_decided': 'Permission decision recorded',
  'command.launch': 'Command started',
  'command.completed': 'Command finished',
  'file.operation': 'File tool completed',
  'tool.audit': 'Tool activity recorded',
  'recovery.resumed': 'Recovery resumed',
};
export function eventLabel(event: DomainEvent) {
  if (event.type === 'operation.started')
    return event.payload.phase === 'develop'
      ? 'Developer started'
      : event.payload.phase === 'review'
        ? 'Reviewer started'
        : 'Manager started';
  return labels[event.type] || event.type;
}
export function ActivityFeed({ events }: { events: DomainEvent[] }) {
  return (
    <section className="panel" id="activity">
      <h2>Activity</h2>
      <p className="muted">
        Committed events since this view opened. Latest 250 entries.
      </p>
      {events.length === 0 && <p>No new committed activity yet.</p>}
      <ol className="activity" aria-label="Committed activity">
        {[...events].reverse().map((event) => (
          <li
            key={event.sequence}
            id={`event-${event.sequence}`}
            tabIndex={-1}
            data-event-id={event.sequence}
          >
            <strong>{eventLabel(event)}</strong>
            <span className="muted">
              #{event.sequence}
              {event.task_id ? ` · ${event.task_id}` : ''}
            </span>
            {event.occurred_at && (
              <time dateTime={event.occurred_at}>
                {new Date(event.occurred_at).toLocaleTimeString()}
              </time>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
