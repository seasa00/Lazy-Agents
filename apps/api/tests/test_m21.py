from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from app.agents.contracts import DecisionRecord, ManagerPlan, Requirement, TaskSpec
from app.domain.projects import ProjectState, RunStatus
from app.domain.tasks import TaskStatus
from app.orchestration.planning import PlanValidationError, ready_tasks, validate_manager_plan
from app.orchestration.transitions import TransitionError
from app.persistence.memory import InMemoryStateStore
from app.persistence.store import ActiveRunError, ExecutionNotApprovedError
from app.domain.agents import AgentKind


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"


def plan_with(*tasks: TaskSpec) -> ManagerPlan:
    return ManagerPlan(
        summary="A valid bounded plan",
        requirements=(Requirement("req-1", "The behavior is defined.", ("It works",)),),
        tasks=tuple(tasks),
        assumptions=(),
        decisions=(DecisionRecord("decision-1", "Keep the plan small", "M2.1 scope"),),
    )


def two_task_plan() -> ManagerPlan:
    return plan_with(
        TaskSpec("task-a", "Foundation", "Prepare the foundation.", ("Foundation exists",), AgentKind.DEVELOPER, ()),
        TaskSpec("task-b", "Follow-up", "Use the foundation.", ("Follow-up works",), AgentKind.DEVELOPER, ("task-a",)),
    )


def store_with_plan(plan: ManagerPlan | None = None) -> tuple[InMemoryStateStore, str, str]:
    store = InMemoryStateStore()
    store.create_project(ProjectState("project-1", "Test project", "Test dependency-aware planning."))
    run = store.create_run("project-1", run_id="run-1")
    if plan is not None:
        store.propose_plan("project-1", run.id, plan)
    return store, "project-1", run.id


class PlanningValidationTests(unittest.TestCase):
    def test_valid_manager_plan_is_validated_and_materialized(self) -> None:
        plan = validate_manager_plan(two_task_plan())
        self.assertEqual([task.id for task in plan.tasks], ["task-a", "task-b"])
        self.assertEqual(plan.tasks[1].dependencies, ("task-a",))

    def test_invalid_plan_structure_is_rejected(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, "missing fields: tasks"):
            validate_manager_plan({
                "summary": "broken",
                "requirements": [],
                "assumptions": [],
                "decisions": [],
            })

    def test_missing_dependency_is_rejected(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, "missing dependencies"):
            validate_manager_plan(plan_with(TaskSpec("task-a", "A", "A", ("A",), AgentKind.DEVELOPER, ("missing",))))

    def test_self_dependency_is_rejected(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, "cannot depend on itself"):
            validate_manager_plan(plan_with(TaskSpec("task-a", "A", "A", ("A",), AgentKind.DEVELOPER, ("task-a",))))

    def test_dependency_cycle_is_rejected(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, "cycle"):
            validate_manager_plan(
                plan_with(
                    TaskSpec("task-a", "A", "A", ("A",), AgentKind.DEVELOPER, ("task-b",)),
                    TaskSpec("task-b", "B", "B", ("B",), AgentKind.DEVELOPER, ("task-a",)),
                )
            )


class StateStoreTests(unittest.TestCase):
    def test_plan_approval_starts_run_and_marks_only_root_task_ready(self) -> None:
        store, project_id, run_id = store_with_plan(two_task_plan())
        self.assertEqual(store.get_project(project_id).run(run_id).status, RunStatus.AWAITING_APPROVAL)
        approved = store.approve_plan(project_id, run_id)
        self.assertEqual(approved.status, RunStatus.RUNNING)
        project = store.get_project(project_id)
        self.assertEqual([item.id for item in project.requirements], ["req-1"])
        self.assertEqual([item.id for item in project.decisions], ["decision-1"])
        self.assertEqual(project.requirement_version, 2)
        self.assertEqual(project.task("task-a").status, TaskStatus.TODO)
        self.assertEqual(project.task("task-b").status, TaskStatus.BACKLOG)

    def test_execution_before_approval_is_rejected(self) -> None:
        store, project_id, run_id = store_with_plan(two_task_plan())
        with self.assertRaises(ExecutionNotApprovedError):
            store.start_next_task(project_id, run_id)

    def test_dependency_readiness_advances_only_after_active_prerequisite_completes(self) -> None:
        store, project_id, run_id = store_with_plan(two_task_plan())
        store.approve_plan(project_id, run_id)
        first = store.start_next_task(project_id, run_id)
        self.assertEqual(first.id, "task-a")
        self.assertEqual(ready_tasks(store.get_project(project_id).tasks), ())
        with self.assertRaisesRegex(TransitionError, "not ready"):
            store.transition_task(project_id, run_id, "task-b", TaskStatus.TODO)
        store.transition_task(project_id, run_id, "task-a", TaskStatus.REVIEW)
        store.transition_task(project_id, run_id, "task-a", TaskStatus.DONE)
        project = store.get_project(project_id)
        self.assertEqual(project.task("task-b").status, TaskStatus.TODO)
        self.assertEqual(store.start_next_task(project_id, run_id).id, "task-b")

    def test_invalid_state_transition_is_rejected(self) -> None:
        store, project_id, run_id = store_with_plan(two_task_plan())
        store.approve_plan(project_id, run_id)
        with self.assertRaises(TransitionError):
            store.transition_task(project_id, run_id, "task-a", TaskStatus.DONE)

    def test_second_active_run_is_rejected(self) -> None:
        store, project_id, _ = store_with_plan()
        with self.assertRaises(ActiveRunError):
            store.create_run(project_id, run_id="run-2")

    def test_canceled_task_is_not_counted_as_completed(self) -> None:
        store, project_id, run_id = store_with_plan(two_task_plan())
        store.approve_plan(project_id, run_id)
        canceled = store.cancel_task(project_id, run_id, "task-a")
        project = store.get_project(project_id)
        self.assertTrue(canceled.is_canceled)
        self.assertFalse(canceled.is_completed)
        self.assertEqual(project.completed_task_ids, ())
        self.assertEqual(ready_tasks(project.tasks), ())

    def test_state_and_events_update_together(self) -> None:
        store, project_id, run_id = store_with_plan(two_task_plan())
        store.approve_plan(project_id, run_id)
        started = store.start_next_task(project_id, run_id)
        project = store.get_project(project_id)
        events = store.events(project_id)
        self.assertEqual([event.sequence for event in events], list(range(1, len(events) + 1)))
        task_event = next(event for event in events if event.type == "task.started")
        self.assertEqual(task_event.task_id, started.id)
        self.assertEqual(task_event.payload["task_version"], project.task(started.id).version)
        self.assertEqual(project.run(run_id).current_task_id, started.id)

    def test_invalid_plan_does_not_commit_state_or_events(self) -> None:
        store, project_id, run_id = store_with_plan()
        before = store.get_project(project_id)
        before_events = store.events(project_id)
        invalid = plan_with(
            TaskSpec("task-a", "A", "A", ("A",), AgentKind.DEVELOPER, ("task-b",)),
            TaskSpec("task-b", "B", "B", ("B",), AgentKind.DEVELOPER, ("task-a",)),
        )
        with self.assertRaises(PlanValidationError):
            store.propose_plan(project_id, run_id, invalid)
        self.assertEqual(store.get_project(project_id), before)
        self.assertEqual(store.events(project_id), before_events)


class M21CliTests(unittest.TestCase):
    def test_state_demo_shows_approval_readiness_and_cycle_rejection(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app.dev.cli", "state-demo"],
            cwd=API_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated plan:", result.stdout)
        self.assertIn("Ready task: task-foundation", result.stdout)
        self.assertIn("Cyclic plan rejected:", result.stdout)
        self.assertIn("Second active run rejected:", result.stdout)


if __name__ == "__main__":
    unittest.main()
