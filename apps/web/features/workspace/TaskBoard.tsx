import type { Review, Task, TaskStatus } from '@/lib/api/types';
const columns: TaskStatus[] = [
  'backlog',
  'todo',
  'in_progress',
  'review',
  'done',
  'blocked',
];
export function TaskBoard({
  tasks,
  reviews,
  selected,
  onSelect,
}: {
  tasks: Task[];
  reviews: Review[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="panel task-board" id="tasks">
      <h2>Task board</h2>
      <div className="board">
        {columns.map((status) => (
          <section
            key={status}
            className="column"
            data-task-status={status}
            aria-label={`${status.toUpperCase()} tasks`}
          >
            <h3>
              {status.toUpperCase().replaceAll('_', ' ')}{' '}
              <span className="count">
                {tasks.filter((t) => t.status === status).length}
              </span>
            </h3>
            {tasks
              .filter((t) => t.status === status)
              .map((task) => (
                <button
                  type="button"
                  aria-pressed={selected === task.id}
                  className="task-card"
                  key={task.id}
                  onClick={() => onSelect(task.id)}
                  data-testid={`task-${task.id}`}
                >
                  <span className="mono">{task.id}</span>
                  <strong>{task.title}</strong>
                  <span>{task.assignee}</span>
                  <span className="badge">{task.status.toUpperCase()}</span>
                  {task.disposition === 'canceled' && (
                    <span className="warning">Canceled disposition</span>
                  )}
                  <span>
                    Dependencies: {task.dependencies.join(', ') || 'None'}
                  </span>
                  <span>
                    Reviews:{' '}
                    {reviews.filter((r) => r.task_id === task.id).length}
                  </span>
                  {task.blocked_reason && <span>{task.blocked_reason}</span>}
                </button>
              ))}
          </section>
        ))}
      </div>
      {tasks.length === 0 && (
        <p className="muted">Tasks appear when the Manager commits a plan.</p>
      )}
      {selected && tasks.find((t) => t.id === selected) && (
        <aside className="task-detail">
          <h3>Selected task: {selected}</h3>
          <p>{tasks.find((t) => t.id === selected)!.description}</p>
          <ul>
            {tasks
              .find((t) => t.id === selected)!
              .acceptance_criteria.map((c) => (
                <li key={c}>{c}</li>
              ))}
          </ul>
        </aside>
      )}
    </section>
  );
}
