"""Atomic in-memory StateStore for M2.1."""

from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
from threading import RLock
from typing import Mapping
from uuid import uuid4

from app.agents.contracts import ManagerPlan
from app.domain.events import ActorKind, DomainEvent, EventActor
from app.domain.projects import ACTIVE_RUN_STATUSES, ProjectState, RunState, RunStatus, TERMINAL_RUN_STATUSES, _snapshot_items
from app.domain.tasks import Task, TaskDisposition, TaskStatus
from app.orchestration.planning import materialize_tasks, ready_tasks, validate_manager_plan
from app.orchestration.transitions import TransitionError, assert_run_transition, assert_task_transition
from app.persistence.store import (
    ActiveRunError,
    ExecutionNotApprovedError,
    NoReadyTaskError,
    NotFoundError,
    PlanApprovalError,
    StateStore,
    StoreError,
    VersionConflictError,
)


class InMemoryStateStore(StateStore):
    """Thread-safe, copy-on-write state plus append-only committed events."""

    def __init__(self) -> None:
        self._projects: dict[str, ProjectState] = {}
        self._events: dict[str, list[DomainEvent]] = {}
        self._lock = RLock()

    def create_project(self, project: ProjectState) -> ProjectState:
        with self._lock:
            if project.id in self._projects:
                raise StoreError(f"project already exists: {project.id}")
            self._projects[project.id] = project
            self._events[project.id] = []
            self._append_event(project.id, DomainEvent(project.id, "project.created", {"project_version": project.version}))
            return project

    def get_project(self, project_id: str) -> ProjectState:
        with self._lock:
            return deepcopy(self._project(project_id))

    def atomic_update(self, project_id, change, *, expected_version=None):
        """Trusted deterministic reducer; never pass a provider/model callback here."""
        with self._lock:
            before = self._project(project_id)
            if expected_version is not None and before.version != expected_version:
                raise VersionConflictError('project version changed')
            after, events = change(deepcopy(before))
            if after.id != before.id or not events:
                raise StoreError('atomic update requires matching identity and events')
            after = replace(after, version=before.version + 1)
            if sum(p.active_run is not None for key, p in self._projects.items() if key != project_id) + (after.active_run is not None) > 1:
                raise ActiveRunError('only one active run is allowed across the application')
            self._commit(before, deepcopy(after), deepcopy(list(events)))
            return deepcopy(after)

    def create_run(self, project_id: str, *, config_snapshot: Mapping[str, str] | None = None, run_id: str | None = None) -> RunState:
        with self._lock:
            project = self._project(project_id)
            if any(p.active_run is not None or any(r.workflow and r.workflow.pending for r in p.runs) for p in self._projects.values()):
                raise ActiveRunError('application already has an active run')
            run = RunState(
                id=run_id or f"run_{uuid4().hex}",
                project_id=project_id,
                config_snapshot=_snapshot_items(config_snapshot or {}),
            )
            updated = replace(
                project,
                runs=(*project.runs, run),
                active_run_id=run.id,
                version=project.version + 1,
            )
            self._commit(project, updated, [DomainEvent(project_id, "run.created", {"run_version": run.version}, run_id=run.id)])
            return run

    def begin_planning(self, project_id: str, run_id: str) -> RunState:
        with self._lock:
            project, run = self._project_run(project_id, run_id)
            self._require_legacy(run)
            assert_run_transition(run.status, RunStatus.PLANNING)
            updated_run = replace(run, status=RunStatus.PLANNING, phase="planning", version=run.version + 1)
            updated = self._replace_run(project, updated_run)
            self._commit(project, updated, [DomainEvent(project_id, "run.planning_started", {"run_version": updated_run.version}, run_id=run.id)])
            return updated_run

    def propose_plan(self, project_id: str, run_id: str, plan: ManagerPlan) -> RunState:
        """Validate a Manager proposal, then commit tasks and events atomically."""

        validated = validate_manager_plan(plan)
        tasks = materialize_tasks(validated)
        with self._lock:
            project, run = self._project_run(project_id, run_id)
            if run.status not in {RunStatus.DRAFT, RunStatus.PLANNING}:
                raise PlanApprovalError(f"cannot propose a plan while run is {run.status.value}")
            self._require_legacy(run)
            if run.status is RunStatus.DRAFT:
                planning_run = replace(run, status=RunStatus.PLANNING, phase="planning", version=run.version + 1)
            else:
                planning_run = run
            existing_ids = {task.id for task in project.tasks}
            overlap = sorted(existing_ids.intersection(task.id for task in tasks))
            if overlap:
                raise PlanApprovalError(f"plan task ids already exist: {', '.join(overlap)}")
            requirements = list(project.requirements)
            requirements_by_id = {item.id: item for item in requirements}
            for requirement in validated.requirements:
                existing = requirements_by_id.get(requirement.id)
                if existing is not None and existing != requirement:
                    raise PlanApprovalError(f"plan changes existing requirement: {requirement.id}")
                if existing is None:
                    requirements.append(requirement)
                    requirements_by_id[requirement.id] = requirement
            decisions = list(project.decisions)
            decisions_by_id = {item.id: item for item in decisions}
            for decision in validated.decisions:
                existing = decisions_by_id.get(decision.id)
                if existing is not None and existing != decision:
                    raise PlanApprovalError(f"plan changes existing decision: {decision.id}")
                if existing is None:
                    decisions.append(decision)
                    decisions_by_id[decision.id] = decision
            committed_run = replace(
                planning_run,
                status=RunStatus.AWAITING_APPROVAL,
                phase="awaiting_approval",
                plan=validated,
                task_ids=tuple(task.id for task in tasks),
                version=planning_run.version + 1,
            )
            updated = self._replace_run(
                replace(
                    project,
                    requirements=tuple(requirements),
                    requirement_version=project.requirement_version + (1 if tuple(requirements) != project.requirements else 0),
                    decisions=tuple(decisions),
                    tasks=(*project.tasks, *tasks),
                ),
                committed_run,
            )
            events = [
                DomainEvent(project_id, "run.planning_started", {"run_version": planning_run.version}, run_id=run.id)
            ] if run.status is RunStatus.DRAFT else []
            events.append(DomainEvent(project_id, "plan.proposed", {"task_ids": list(committed_run.task_ids), "run_version": committed_run.version}, run_id=run.id, actor=EventActor(ActorKind.MANAGER, "manager")))
            events.extend(
                DomainEvent(project_id, "task.created", {"task_version": task.version, "dependencies": list(task.dependencies)}, run_id=run.id, task_id=task.id)
                for task in tasks
            )
            events.extend(
                DomainEvent(project_id, "requirement.recorded", {"requirement_version": updated.requirement_version}, run_id=run.id)
                for requirement in validated.requirements
                if requirement.id not in {item.id for item in project.requirements}
            )
            events.extend(
                DomainEvent(project_id, "decision.recorded", {"decision_id": decision.id}, run_id=run.id, actor=EventActor(ActorKind.MANAGER, "manager"))
                for decision in validated.decisions
                if decision.id not in {item.id for item in project.decisions}
            )
            self._commit(project, updated, events)
            return committed_run

    def approve_plan(self, project_id: str, run_id: str) -> RunState:
        with self._lock:
            project, run = self._project_run(project_id, run_id)
            if run.status is not RunStatus.AWAITING_APPROVAL or run.plan is None:
                raise PlanApprovalError("only a proposed plan can be approved")
            approved_ids = {task.id for task in project.tasks if task.id in run.task_ids}
            updated_tasks: list[Task] = []
            events: list[DomainEvent] = [DomainEvent(project_id, "plan.approved", {"run_version": run.version}, run_id=run.id, actor=EventActor(ActorKind.USER, "user"))]
            for task in project.tasks:
                if task.id not in approved_ids or task.status is not TaskStatus.BACKLOG:
                    updated_tasks.append(task)
                    continue
                if not task.dependencies:
                    ready = replace(task, status=TaskStatus.TODO, version=task.version + 1)
                    updated_tasks.append(ready)
                    events.append(DomainEvent(project_id, "task.ready", {"task_version": ready.version}, run_id=run.id, task_id=task.id))
                else:
                    updated_tasks.append(task)
            committed_run = replace(run, status=RunStatus.RUNNING, phase="execution", plan_approved=True, version=run.version + 1)
            updated = self._replace_run(replace(project, tasks=tuple(updated_tasks)), committed_run)
            events.append(DomainEvent(project_id, "run.started", {"run_version": committed_run.version}, run_id=run.id))
            self._commit(project, updated, events)
            return committed_run

    def start_next_task(self, project_id: str, run_id: str) -> Task:
        with self._lock:
            project, run = self._project_run(project_id, run_id)
            self._require_legacy(run)
            if not run.approved:
                raise ExecutionNotApprovedError("cannot execute tasks before the Manager plan is approved")
            if run.status is not RunStatus.RUNNING:
                raise StoreError(f"cannot start a task while run is {run.status.value}")
            if run.current_task_id is not None:
                raise StoreError(f"run already has active task {run.current_task_id}")
            candidates = ready_tasks(task for task in project.tasks if task.id in run.task_ids)
            candidate = next((task for task in candidates if task.status is TaskStatus.TODO), None)
            if candidate is None:
                raise NoReadyTaskError("approved run has no ready task")
            started = replace(candidate, status=TaskStatus.IN_PROGRESS, version=candidate.version + 1)
            updated = self._replace_task(project, started)
            updated_run = replace(run, current_task_id=started.id, phase="task_execution", version=run.version + 1)
            updated = self._replace_run(updated, updated_run)
            self._commit(project, updated, [DomainEvent(project_id, "task.started", {"task_version": started.version}, run_id=run.id, task_id=started.id)])
            return started

    def transition_task(self, project_id: str, run_id: str, task_id: str, target: TaskStatus) -> Task:
        with self._lock:
            project, run = self._project_run(project_id, run_id)
            self._require_legacy(run)
            task = self._task_for_run(project, run, task_id)
            assert_task_transition(task.status, target, disposition=task.disposition)
            if target is TaskStatus.TODO and any(not project.task(dependency).is_completed for dependency in task.dependencies):
                raise TransitionError(f"task {task.id} is not ready; prerequisites are incomplete")
            updated_task = replace(
                task,
                status=target,
                blocked_reason=None if target is not TaskStatus.BLOCKED else task.blocked_reason,
                revision=task.revision + (1 if target is TaskStatus.TODO and task.status is TaskStatus.DONE else 0),
                version=task.version + 1,
            )
            updated = self._replace_task(project, updated_task)
            updated_run = run
            events: list[DomainEvent] = [DomainEvent(project_id, f"task.{target.value}", {"task_version": updated_task.version}, run_id=run.id, task_id=task_id)]
            if target is TaskStatus.DONE:
                promoted: list[Task] = []
                for candidate in updated.tasks:
                    if candidate.id == updated_task.id or candidate.id not in run.task_ids or candidate.status is not TaskStatus.BACKLOG or candidate.is_canceled:
                        promoted.append(candidate)
                        continue
                    if all(updated.task(dependency).is_completed for dependency in candidate.dependencies):
                        ready = replace(candidate, status=TaskStatus.TODO, version=candidate.version + 1)
                        promoted.append(ready)
                        events.append(DomainEvent(project_id, "task.ready", {"task_version": ready.version}, run_id=run.id, task_id=ready.id))
                    else:
                        promoted.append(candidate)
                promoted_tasks = tuple(promoted)
                if promoted_tasks != updated.tasks:
                    updated = replace(updated, tasks=promoted_tasks, version=updated.version + 1)
            if run.current_task_id == task_id and target in {TaskStatus.REVIEW, TaskStatus.BLOCKED, TaskStatus.DONE}:
                updated_run = replace(run, current_task_id=None, phase="execution", version=run.version + 1)
                updated = self._replace_run(updated, updated_run)
            self._commit(project, updated, events)
            return updated_task

    def cancel_task(self, project_id: str, run_id: str, task_id: str) -> Task:
        with self._lock:
            project, run = self._project_run(project_id, run_id)
            self._require_legacy(run)
            task = self._task_for_run(project, run, task_id)
            if task.is_canceled or task.is_completed:
                raise TransitionError("completed or already canceled tasks cannot be canceled")
            canceled = replace(task, disposition=TaskDisposition.CANCELED, version=task.version + 1)
            updated = self._replace_task(project, canceled)
            updated_run = run
            if run.current_task_id == task_id:
                updated_run = replace(run, current_task_id=None, phase="execution", version=run.version + 1)
                updated = self._replace_run(updated, updated_run)
            self._commit(project, updated, [DomainEvent(project_id, "task.canceled", {"task_version": canceled.version}, run_id=run.id, task_id=task_id)])
            return canceled

    def transition_run(self, project_id: str, run_id: str, target: RunStatus) -> RunState:
        with self._lock:
            project, run = self._project_run(project_id, run_id)
            self._require_legacy(run)
            if target is RunStatus.RUNNING and not run.approved:
                raise ExecutionNotApprovedError('use approve_plan before execution')
            assert_run_transition(run.status, target)
            updated_run = replace(run, status=target, phase=target.value, version=run.version + 1)
            updated = self._replace_run(project, updated_run)
            if target in TERMINAL_RUN_STATUSES:
                updated = replace(updated, active_run_id=None, version=updated.version + 1)
            self._commit(project, updated, [DomainEvent(project_id, f"run.{target.value}", {"run_version": updated_run.version}, run_id=run.id)])
            return updated_run

    def events(self, project_id: str, *, after_sequence: int = 0) -> tuple[DomainEvent, ...]:
        with self._lock:
            self._project(project_id)
            if after_sequence < 0:
                raise ValueError("after_sequence must be non-negative")
            return deepcopy(tuple(event for event in self._events[project_id] if event.sequence > after_sequence))

    @staticmethod
    def _require_legacy(run):
        if run.workflow is not None:
            raise StoreError('managed workflows require validated orchestration commands')

    def _project(self, project_id: str) -> ProjectState:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise NotFoundError(f"project not found: {project_id}") from exc

    def _project_run(self, project_id: str, run_id: str) -> tuple[ProjectState, RunState]:
        project = self._project(project_id)
        try:
            return project, project.run(run_id)
        except KeyError as exc:
            raise NotFoundError(f"run not found: {run_id}") from exc

    @staticmethod
    def _task_for_run(project: ProjectState, run: RunState, task_id: str) -> Task:
        if task_id not in run.task_ids:
            raise NotFoundError(f"task {task_id} is not part of run {run.id}")
        try:
            return project.task(task_id)
        except KeyError as exc:
            raise NotFoundError(f"task not found: {task_id}") from exc

    @staticmethod
    def _replace_run(project: ProjectState, run: RunState) -> ProjectState:
        runs = tuple(run if item.id == run.id else item for item in project.runs)
        return replace(project, runs=runs, active_run_id=next((r.id for r in runs if r.active), None), version=project.version + 1)

    @staticmethod
    def _replace_task(project: ProjectState, task: Task) -> ProjectState:
        return replace(project, tasks=tuple(task if item.id == task.id else item for item in project.tasks), version=project.version + 1)

    def _commit(self, before: ProjectState, after: ProjectState, events: list[DomainEvent]) -> None:
        # All callers hold the lock. State is swapped only after all validation.
        sequence = len(self._events[before.id])
        committed = [event.with_sequence(sequence + offset) for offset, event in enumerate(events, start=1)]
        self._projects[before.id] = after
        self._events[before.id].extend(committed)

    def _append_event(self, project_id: str, event: DomainEvent) -> None:
        self._events[project_id].append(event.with_sequence(len(self._events[project_id]) + 1))
