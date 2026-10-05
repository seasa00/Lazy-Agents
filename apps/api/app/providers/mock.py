"""Deterministic, development-only provider double for M1.1.

This module never performs network requests. It returns stable structured
fixtures unless a test or CLI caller supplies an intentionally malformed
response.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from app.domain.agents import AgentKind
from app.providers.base import ProviderCapabilities, ProviderConfigurationError, ProviderRequest, ProviderResponse, UsageSnapshot


@dataclass(frozen=True, slots=True)
class MockProviderConfig:
    """Controls the deterministic response mode."""

    mode: str = "valid"


class DeterministicMockProvider:
    """A visible offline provider double with inspectable requests."""

    name = "deterministic-mock"
    capabilities = ProviderCapabilities(structured_outputs=True, tools=False, usage=True)

    def __init__(
        self,
        *,
        config: MockProviderConfig | None = None,
        responses: Mapping[AgentKind, Any] | None = None,
    ) -> None:
        self.config = config or MockProviderConfig()
        if self.config.mode not in {"valid", "invalid"}:
            raise ValueError("mock provider mode must be 'valid' or 'invalid'")
        self._responses = {kind: deepcopy(value) for kind, value in (responses or {}).items()}
        self.requests: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if self.config.mode == "invalid":
            output: Any = {"unexpected": "malformed mock output"}
        elif request.agent_kind in self._responses:
            output = deepcopy(self._responses[request.agent_kind])
        else:
            output = self._default_output(request)
        return ProviderResponse(
            output=output,
            model=request.model,
            provider_request_id=f"mock-{request.invocation_id}",
            usage=UsageSnapshot(input_tokens=len(str(request.context)), output_tokens=len(str(output))),
        )

    def _default_output(self, request: ProviderRequest) -> dict[str, Any]:
        context = request.context
        if request.agent_kind is AgentKind.MANAGER:
            requirements = deepcopy(context.get("requirements", []))
            return {
                "summary": f"Plan for {context.get('goal', 'the project')}",
                "requirements": requirements,
                "tasks": [
                    {
                        "id": "task-1",
                        "title": "Complete the initial project task",
                        "description": "Implement the first bounded slice of the stated goal.",
                        "acceptance_criteria": ["The requested behavior is implemented"],
                        "assignee": "developer",
                        "dependencies": [],
                    }
                ],
                "assumptions": ["The project scope is limited to the supplied requirements."],
                "decisions": [],
            }
        if request.agent_kind is AgentKind.DEVELOPER:
            task = context.get("current_task") or {}
            task_id = task.get("id", "task-1") if isinstance(task, Mapping) else "task-1"
            return {
                "submission_id": "submission-1",
                "task_id": task_id,
                "output_version": 1,
                "summary": "Prepared a structured implementation submission for review.",
                "changed_files": [],
                "tests": [],
                "ready_for_review": True,
                "notes": ["No real tools are available until the later tools milestone."],
            }
        if request.agent_kind is AgentKind.REVIEWER:
            task = context.get("current_task") or {}
            criteria = task.get("acceptance_criteria", []) if isinstance(task, Mapping) else []
            submission = context.get("submission") or {}
            submission_id = submission.get("id", "submission-1") if isinstance(submission, Mapping) else "submission-1"
            assessments = [
                {
                    "criterion_id": f"criterion-{index}",
                    "passed": True,
                    "evidence": "The deterministic fixture marks this criterion as satisfied.",
                    "notes": "Fixture evidence only.",
                }
                for index, _criterion in enumerate(criteria, start=1)
            ]
            return {
                "review_id": "review-1",
                "submission_id": submission_id,
                "verdict": "PASS",
                "summary": "The deterministic fixture accepted the submitted version.",
                "assessments": assessments,
                "findings": [],
                "checks_not_performed": ["No real files or commands were inspected in M1.1."],
            }
        raise ProviderConfigurationError(f"unsupported mock agent kind {request.agent_kind!r}")
