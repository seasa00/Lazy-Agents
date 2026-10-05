"""Development harness for deterministic and explicitly live M1.2 calls.

Run from ``apps/api`` with, for example::

    python -m app.dev.cli manager

The default remains :class:`DeterministicMockProvider`. The OpenRouter
provider is opt-in and requires ``OPENROUTER_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from app.agents.runtime import AgentRuntime, InvocationError
from app.context.builder import ProjectContext
from app.domain.agents import AgentKind, default_agent_definitions, load_agent_definitions
from app.agents.contracts import (
    DecisionRecord,
    FileReference,
    ManagerPlan,
    Requirement,
    SubmissionReference,
    TaskBrief,
    TaskSummary,
    TaskSpec,
)
from app.providers.mock import DeterministicMockProvider, MockProviderConfig
from app.providers.openrouter import OpenRouterProviderConfig, OpenRouterResponsesProvider
from app.usage.pricing import PricingTable
from app.domain.projects import ProjectState
from app.persistence.memory import InMemoryStateStore
from app.persistence.store import ActiveRunError
from app.orchestration.planning import PlanValidationError, ready_tasks, validate_manager_plan


def _default_config_path() -> Path:
    # cli.py -> dev -> app -> api -> apps -> repository root
    return Path(__file__).resolve().parents[4] / "config" / "agents" / "defaults.json"


def _default_pricing_path() -> Path:
    return Path(__file__).resolve().parents[4] / "config" / "model-pricing" / "openrouter.json"


def _fixture() -> ProjectContext:
    requirement = Requirement(
        id="req-1",
        description="The initial bounded behavior is clearly specified.",
        acceptance_criteria=("The requested behavior is implemented",),
    )
    task = TaskBrief(
        id="task-1",
        title="Complete the initial project task",
        description="Implement the first bounded slice of the stated goal.",
        acceptance_criteria=("The requested behavior is implemented",),
        assignee=AgentKind.DEVELOPER,
        dependencies=(),
    )
    return ProjectContext(
        goal="Demonstrate an independently invokable AI Office agent.",
        requirements=(requirement,),
        task_summaries=(TaskSummary("task-1", task.title, "TODO", AgentKind.DEVELOPER, (), 0),),
        decisions=(DecisionRecord("decision-1", "Keep the first slice bounded", "Tools and orchestration are deferred to later milestones."),),
        current_task=task,
        dependencies=(),
        submission=SubmissionReference(
            id="submission-1",
            version=1,
            summary="A deterministic fixture submission.",
            changed_files=(FileReference("README.md", "Fixture documentation"),),
            test_evidence=("offline-fixture",),
        ),
        available_files=("README.md",),
        source_versions={"project": "fixture-v1", "requirements": "requirements-v1"},
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one AI Office agent with a bounded provider call budget.")
    parser.add_argument("agent", choices=[kind.value for kind in AgentKind] + ["state-demo"])
    parser.add_argument("--invalid", action="store_true", help="Return a malformed provider fixture to demonstrate validation.")
    parser.add_argument("--config", type=Path, default=_default_config_path(), help="Agent definition JSON file.")
    parser.add_argument("--provider", choices=("deterministic-mock", "openrouter"), default="deterministic-mock")
    parser.add_argument("--model", default=None, help="OpenRouter model slug (default: openai/gpt-4o-mini).")
    parser.add_argument("--max-attempts", type=int, default=1, help="Maximum transient provider attempts, including the first call.")
    parser.add_argument("--max-repairs", type=int, default=0, help="Maximum structured-output repair calls.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Live provider request timeout in seconds.")
    parser.add_argument("--pricing", type=Path, default=_default_pricing_path(), help="Model pricing JSON file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.agent == "state-demo":
        return _state_demo()
    try:
        definitions = load_agent_definitions(args.config) if args.config.exists() else default_agent_definitions()
        kind = AgentKind(args.agent)
        if args.provider == "openrouter":
            if args.invalid:
                raise ValueError("--invalid is only available with --provider deterministic-mock")
            model = args.model or "openai/gpt-4o-mini"
            definitions[kind] = replace(definitions[kind], model=model)
            provider = OpenRouterResponsesProvider(OpenRouterProviderConfig(timeout_seconds=args.timeout))
            pricing = PricingTable.from_json(args.pricing)
        else:
            provider = DeterministicMockProvider(config=MockProviderConfig(mode="invalid" if args.invalid else "valid"))
            pricing = None
        invocation = AgentRuntime(
            max_attempts=args.max_attempts,
            max_repairs=args.max_repairs,
            pricing=pricing,
        ).invoke(definitions[kind], _fixture(), provider, source_versions={"fixture": "v1"})
    except (InvocationError, KeyError, ValueError) as exc:
        print(f"agent invocation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(invocation.to_dict(), indent=2, sort_keys=True))
    return 0


def _state_demo() -> int:
    """Demonstrate proposal validation, approval, readiness, and cycle rejection."""

    plan = ManagerPlan(
        summary="Build the bounded M2.1 demonstration",
        requirements=(Requirement("req-1", "The plan is dependency aware.", ("Dependencies are valid",)),),
        tasks=(
            TaskSpec("task-foundation", "Prepare foundation", "Prepare the first bounded task.", ("Foundation is ready",), AgentKind.DEVELOPER, ()),
            TaskSpec("task-followup", "Use foundation", "Run after the foundation task.", ("Follow-up is ready",), AgentKind.DEVELOPER, ("task-foundation",)),
        ),
        assumptions=("Execution is intentionally not implemented in M2.1.",),
        decisions=(DecisionRecord("decision-1", "Keep the store in memory", "SQLite is deferred."),),
    )
    store = InMemoryStateStore()
    store.create_project(ProjectState("project-demo", "M2.1 demo", "Demonstrate shared state and legal transitions."))
    run = store.create_run("project-demo", run_id="run-demo")
    print("Proposed tasks:")
    for task in plan.tasks:
        print(f"- {task.id}: depends on {', '.join(task.dependencies) or '(none)'}")
    validated = validate_manager_plan(plan)
    print(f"Validated plan: {validated.summary}")
    store.propose_plan("project-demo", run.id, validated)
    store.approve_plan("project-demo", run.id)
    project = store.get_project("project-demo")
    ready = ready_tasks(project.task(task_id) for task_id in project.run(run.id).task_ids)
    print(f"Ready task: {ready[0].id if ready else '(none)'}")
    cyclic = ManagerPlan(
        summary="invalid cycle",
        requirements=plan.requirements,
        tasks=(
            TaskSpec("cycle-a", "A", "A", ("A",), AgentKind.DEVELOPER, ("cycle-b",)),
            TaskSpec("cycle-b", "B", "B", ("B",), AgentKind.DEVELOPER, ("cycle-a",)),
        ),
        assumptions=(),
        decisions=(),
    )
    try:
        validate_manager_plan(cyclic)
    except PlanValidationError as exc:
        print(f"Cyclic plan rejected: {exc}")
    try:
        store.create_run("project-demo", run_id="run-second")
    except ActiveRunError as exc:
        print(f"Second active run rejected: {exc}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by manual verification
    raise SystemExit(main())
