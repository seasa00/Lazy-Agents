from __future__ import annotations

import json
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from app.agents.contracts import (
    ContractValidationError,
    DeveloperSubmission,
    ManagerPlan,
    Requirement,
    ReviewResult,
    ReviewVerdict,
    TaskBrief,
)
from app.agents.runtime import (
    AgentRuntime,
    OutputValidationError,
    RuntimeConfigurationError,
    UndeclaredToolError,
)
from app.context.builder import ContextBuildError, ProjectContext, build_context
from app.domain.agents import AgentKind, AgentStatus, default_agent_definitions, load_agent_definitions
from app.providers.base import ProviderResponse, ProviderToolCall
from app.providers.mock import DeterministicMockProvider, MockProviderConfig


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
DEFAULT_CONFIG = ROOT / "config" / "agents" / "defaults.json"


def project_fixture() -> ProjectContext:
    requirement = Requirement(
        id="req-1",
        description="The behavior is specified.",
        acceptance_criteria=("The behavior is implemented",),
    )
    task = TaskBrief(
        id="task-1",
        title="Implement the behavior",
        description="A bounded task.",
        acceptance_criteria=("The behavior is implemented",),
        assignee=AgentKind.DEVELOPER,
        dependencies=(),
    )
    from app.agents.contracts import DecisionRecord, FileReference, SubmissionReference, TaskSummary

    return ProjectContext(
        goal="Build a bounded example.",
        requirements=(requirement,),
        task_summaries=(TaskSummary("task-1", task.title, "TODO", AgentKind.DEVELOPER, (), 0),),
        decisions=(DecisionRecord("d-1", "Keep it small", "M1.1 scope"),),
        current_task=task,
        dependencies=(),
        submission=SubmissionReference("submission-1", 1, "Fixture output", (FileReference("README.md", "docs"),), ("fixture",)),
        available_files=("README.md",),
        source_versions={"project": "v1"},
    )


class AgentDefinitionsTests(unittest.TestCase):
    def test_defaults_define_exactly_three_tool_free_kinds(self) -> None:
        definitions = default_agent_definitions()
        self.assertEqual(set(definitions), set(AgentKind))
        self.assertEqual({definition.status for definition in definitions.values()}, {AgentStatus.IDLE})
        self.assertTrue(all(not definition.tools and not definition.permissions for definition in definitions.values()))
        self.assertEqual(definitions[AgentKind.DEVELOPER].role, "Software Developer")

    def test_json_configuration_is_strict_and_matches_defaults(self) -> None:
        loaded = load_agent_definitions(DEFAULT_CONFIG)
        self.assertEqual(set(loaded), set(AgentKind))
        for kind, definition in loaded.items():
            self.assertEqual(definition.snapshot().config_digest, default_agent_definitions()[kind].snapshot().config_digest)

    def test_unknown_definition_field_is_rejected(self) -> None:
        definition = default_agent_definitions()[AgentKind.MANAGER].to_dict()
        definition["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields: unexpected"):
            type(default_agent_definitions()[AgentKind.MANAGER]).from_dict(definition)


class ContextBuilderTests(unittest.TestCase):
    def test_each_role_receives_only_its_allowed_sections(self) -> None:
        project = project_fixture()
        for kind, definition in default_agent_definitions().items():
            built = build_context(definition, project, source_versions={"requirements": "r1"})
            self.assertEqual(built.context.kind, kind)
            self.assertTrue(set(built.payload).issubset(set(definition.context_policy.allowed_sections)))
            self.assertNotIn("conversation_history", built.payload)
            self.assertEqual(built.manifest.configuration_version, 1)
            self.assertEqual(built.manifest.source_versions, (("requirements", "r1"),))
            self.assertEqual(len(built.manifest.context_digest), 64)

    def test_required_context_is_not_silently_omitted(self) -> None:
        project = replace(project_fixture(), current_task=None)
        with self.assertRaisesRegex(ContextBuildError, "current_task"):
            build_context(default_agent_definitions()[AgentKind.DEVELOPER], project)
        with self.assertRaisesRegex(ContextBuildError, "current_task"):
            build_context(default_agent_definitions()[AgentKind.REVIEWER], project)

    def test_context_size_fails_instead_of_truncating(self) -> None:
        definition = replace(
            default_agent_definitions()[AgentKind.MANAGER],
            context_policy=replace(default_agent_definitions()[AgentKind.MANAGER].context_policy, max_chars=256),
        )
        project = replace(project_fixture(), goal="x" * 2_000)
        with self.assertRaisesRegex(ContextBuildError, "not truncated"):
            build_context(definition, project)

    def test_config_snapshot_is_stable_after_replacement(self) -> None:
        definition = default_agent_definitions()[AgentKind.MANAGER]
        before = definition.snapshot()
        replacement = replace(definition, system_instructions="A later configuration")
        self.assertNotEqual(before.config_digest, replacement.snapshot().config_digest)
        self.assertEqual(before.system_instructions, "Orchestrate work through structured plans and decisions; do not perform specialist work.")


class ContractValidationTests(unittest.TestCase):
    def test_manager_plan_rejects_unknown_and_missing_fields(self) -> None:
        valid = {
            "summary": "summary",
            "requirements": [{"id": "r1", "description": "desc", "acceptance_criteria": ["works"], "priority": "normal"}],
            "tasks": [{"id": "t1", "title": "task", "description": "desc", "acceptance_criteria": ["works"], "assignee": "developer", "dependencies": []}],
            "assumptions": [],
            "decisions": [],
        }
        parsed = ManagerPlan.from_dict(valid)
        self.assertEqual(parsed.tasks[0].assignee, AgentKind.DEVELOPER)
        with self.assertRaisesRegex(ContractValidationError, "unknown fields: extra"):
            ManagerPlan.from_dict({**valid, "extra": True})
        missing = dict(valid)
        del missing["tasks"]
        with self.assertRaisesRegex(ContractValidationError, "missing fields: tasks"):
            ManagerPlan.from_dict(missing)

    def test_reviewer_verdict_requires_consistent_findings(self) -> None:
        fail = {
            "review_id": "r-1",
            "submission_id": "s-1",
            "verdict": "FAIL",
            "summary": "failed",
            "assessments": [{"criterion_id": "c1", "passed": False, "evidence": "missing", "notes": "fix"}],
            "findings": [{"id": "f1", "severity": "major", "summary": "missing", "evidence": "missing", "criterion_id": "c1"}],
            "checks_not_performed": [],
        }
        self.assertEqual(ReviewResult.from_dict(fail).verdict, ReviewVerdict.FAIL)
        with self.assertRaisesRegex(ContractValidationError, "FAIL review must contain"):
            ReviewResult.from_dict({**fail, "findings": []})

    def test_developer_submission_rejects_invalid_types(self) -> None:
        invalid = {
            "submission_id": "s-1",
            "task_id": "t-1",
            "output_version": 0,
            "summary": "summary",
            "changed_files": [],
            "tests": [],
            "ready_for_review": True,
            "notes": [],
        }
        with self.assertRaisesRegex(ContractValidationError, "positive integer"):
            DeveloperSubmission.from_dict(invalid)


class RuntimeTests(unittest.TestCase):
    def test_all_three_agents_invoke_with_valid_structured_results(self) -> None:
        definitions = default_agent_definitions()
        for kind, definition in definitions.items():
            provider = DeterministicMockProvider()
            result = AgentRuntime().invoke(definition, project_fixture(), provider, invocation_id=f"{kind.value}-inv")
            self.assertEqual(result.agent.kind, kind)
            self.assertEqual(result.invocation_id, f"{kind.value}-inv")
            self.assertEqual(result.provider_name, "deterministic-mock")
            self.assertIsNotNone(result.usage)
            self.assertEqual(len(provider.requests), 1)
            expected_schema = {
                AgentKind.MANAGER: "manager_plan",
                AgentKind.DEVELOPER: "developer_submission",
                AgentKind.REVIEWER: "review_result",
            }[kind]
            self.assertEqual(provider.requests[0].output_schema.split(".")[0], expected_schema)

    def test_invalid_provider_output_is_actionable_and_has_no_retry(self) -> None:
        provider = DeterministicMockProvider(config=MockProviderConfig(mode="invalid"))
        with self.assertRaisesRegex(OutputValidationError, "manager_plan.v1"):
            AgentRuntime().invoke(default_agent_definitions()[AgentKind.MANAGER], project_fixture(), provider)
        self.assertEqual(len(provider.requests), 1)

    def test_provider_tool_calls_are_rejected_before_execution(self) -> None:
        class ToolCallingProvider(DeterministicMockProvider):
            def complete(self, request):
                response = super().complete(request)
                return ProviderResponse(
                    output=response.output,
                    model=response.model,
                    provider_request_id=response.provider_request_id,
                    tool_calls=(ProviderToolCall("read_file", {"path": "README.md"}),),
                    usage=response.usage,
                )

        with self.assertRaisesRegex(UndeclaredToolError, "read_file"):
            AgentRuntime().invoke(default_agent_definitions()[AgentKind.MANAGER], project_fixture(), ToolCallingProvider())

    def test_nonempty_configured_tools_are_rejected(self) -> None:
        definition = replace(default_agent_definitions()[AgentKind.DEVELOPER], tools=("read_files",))
        with self.assertRaisesRegex(RuntimeConfigurationError, "tools or permissions"):
            AgentRuntime().invoke(definition, project_fixture(), DeterministicMockProvider())


class CliTests(unittest.TestCase):
    def test_cli_valid_and_invalid_modes(self) -> None:
        valid = subprocess.run(
            [sys.executable, "-m", "app.dev.cli", "reviewer"],
            cwd=API_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        payload = json.loads(valid.stdout)
        self.assertEqual(payload["agent"]["kind"], "reviewer")
        self.assertEqual(payload["output"]["verdict"], "PASS")
        self.assertEqual(payload["provider_name"], "deterministic-mock")

        invalid = subprocess.run(
            [sys.executable, "-m", "app.dev.cli", "manager", "--invalid"],
            cwd=API_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("manager_plan.v1", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
