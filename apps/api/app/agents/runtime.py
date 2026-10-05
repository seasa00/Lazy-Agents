"""Shared agent runtime with bounded M1.2 retries and call attribution."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from decimal import Decimal
import time
from typing import Any
from uuid import uuid4

from app.agents.contracts import AgentOutput, ContractValidationError, parse_agent_output, ManagerDecision, FinalResult
from app.context.builder import BuiltContext, ContextManifest, ProjectContext, build_context
from app.domain.agents import AgentConfigSnapshot, AgentDefinition, AgentKind
from app.providers.base import (
    Provider,
    ProviderCapabilities,
    ProviderError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderTransientError,
    UsageSnapshot,
)
from app.usage.pricing import CostEstimate, PricingTable
from app.usage.records import LLMCallRecord, UsageCompleteness, UsageProvenance


class InvocationError(RuntimeError):
    """Base class for an invocation that could not produce a valid result."""

    def __init__(self, message: str, *, call_records: tuple[LLMCallRecord, ...] = ()) -> None:
        super().__init__(message)
        self.call_records = call_records


class RuntimeConfigurationError(InvocationError):
    """Raised when the runtime is asked to use an unavailable capability."""


class ContextMismatchError(InvocationError):
    """Raised when a role receives another role's context."""


class UndeclaredToolError(InvocationError):
    """Raised if a provider returns tool calls before tools are implemented."""


class OutputValidationError(InvocationError):
    """Raised when a provider response violates the role output schema."""


class ProviderInvocationError(InvocationError):
    """Raised after the bounded provider retry budget is exhausted."""


@dataclass(frozen=True, slots=True)
class AgentInvocation:
    """Auditable result of exactly one provider request."""

    invocation_id: str
    agent: AgentConfigSnapshot
    context_manifest: ContextManifest
    provider_name: str
    provider_request_id: str
    output: AgentOutput
    usage: UsageSnapshot | None
    call_records: tuple[LLMCallRecord, ...] = ()
    estimated_cost: CostEstimate | None = None

    def to_dict(self) -> dict[str, Any]:
        output = self.output.to_dict()
        return {
            "invocation_id": self.invocation_id,
            "agent": self.agent.to_dict(),
            "context_manifest": self.context_manifest.to_dict(),
            "provider_name": self.provider_name,
            "provider_request_id": self.provider_request_id,
            "output": output,
            "usage": None if self.usage is None else self.usage.to_dict(),
            "call_records": [record.to_dict() for record in self.call_records],
            "estimated_cost": None if self.estimated_cost is None else self.estimated_cost.to_dict(),
        }


class AgentRuntime:
    """Invoke one configured agent with a bounded provider-call budget.

    Defaults retain M1.1's exactly-one-call behavior. M1.2 callers opt into a
    bounded technical retry and repair budget explicitly, which keeps the
    offline harness deterministic while making live use safe to enable.
    """

    _OUTPUT_SCHEMAS = {
        AgentKind.MANAGER: "manager_plan.v1",
        AgentKind.DEVELOPER: "developer_submission.v1",
        AgentKind.REVIEWER: "review_result.v1",
    }

    def __init__(
        self,
        *,
        max_attempts: int = 1,
        max_repairs: int = 0,
        retry_backoff_seconds: tuple[float, ...] = (0.5, 1.0, 2.0),
        sleeper: Any = time.sleep,
        pricing: PricingTable | None = None,
    ) -> None:
        if max_attempts < 1 or max_repairs < 0:
            raise ValueError("max_attempts must be positive and max_repairs must be non-negative")
        if any(delay < 0 for delay in retry_backoff_seconds):
            raise ValueError("retry backoff values must be non-negative")
        self.max_attempts = max_attempts
        self.max_repairs = max_repairs
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleeper = sleeper
        self.pricing = pricing

    def invoke(
        self,
        agent: AgentDefinition,
        project: ProjectContext,
        provider: Provider,
        *,
        source_versions: dict[str, str] | None = None,
        invocation_id: str | None = None,
        max_attempts: int | None = None,
        max_repairs: int | None = None,
        output_schema: str | None = None,
        workflow_context: dict[str, Any] | None = None,
        before_call: Any = None,
    ) -> AgentInvocation:
        """Build context, make bounded calls, and validate one role output."""

        if agent.tools or agent.permissions:
            raise RuntimeConfigurationError(
                "Configured tools or permissions are unavailable until the tools milestone; agent definitions must be tool-free"
            )
        invocation_id = invocation_id or f"inv_{uuid4().hex}"
        snapshot = agent.snapshot()
        built = build_context(agent, project, source_versions=source_versions)
        schema = output_schema or self._OUTPUT_SCHEMAS[agent.kind]
        allowed = {self._OUTPUT_SCHEMAS[agent.kind]}
        if agent.kind is AgentKind.MANAGER:
            allowed.update({'manager_decision.v1', 'final_result.v1'})
        if schema not in allowed:
            raise RuntimeConfigurationError('output schema does not belong to role')
        if workflow_context is not None:
            payload = {**built.payload, 'workflow': workflow_context}
            encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            if len(encoded) > agent.context_policy.max_chars:
                raise RuntimeConfigurationError('workflow context exceeds context budget')
            built = replace(built, payload=payload, manifest=replace(
                built.manifest, selected_sections=(*built.manifest.selected_sections, 'workflow'),
                serialized_chars=len(encoded), context_digest=hashlib.sha256(encoded.encode()).hexdigest()))
        if built.manifest.configuration_digest != snapshot.config_digest:
            raise InvocationError("configuration changed while building invocation context")
        if built.context.kind is not agent.kind:
            raise ContextMismatchError(
                f"agent {agent.kind.value} received context for {built.context.kind.value}"
            )
        request = ProviderRequest(
            invocation_id=invocation_id,
            agent_kind=agent.kind,
            model=snapshot.model,
            system_instructions=snapshot.system_instructions,
            context=built.payload,
            output_schema=schema,
        )
        capabilities = getattr(provider, "capabilities", None)
        self._check_capabilities(capabilities, request)
        provider_name = getattr(provider, "name", provider.__class__.__name__)
        attempts_budget = self.max_attempts if max_attempts is None else max_attempts
        repairs_budget = self.max_repairs if max_repairs is None else max_repairs
        if attempts_budget < 1 or repairs_budget < 0:
            raise ValueError("max_attempts must be positive and max_repairs must be non-negative")

        records: list[LLMCallRecord] = []
        transient_attempts = 0
        repairs = 0
        attempt_number = 0
        current_request = request
        while True:
            if before_call is not None:
                try:
                    before_call()
                except InvocationError as exc:
                    exc.call_records = tuple(records)
                    raise
            attempt_number += 1
            purpose = "initial" if attempt_number == 1 else ("repair" if repairs else "retry")
            call_id = f"{invocation_id}:call:{attempt_number}"
            try:
                response = provider.complete(current_request)
            except ProviderTransientError as exc:
                transient_attempts += 1
                records.append(self._failed_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, exc))
                if transient_attempts >= attempts_budget:
                    raise ProviderInvocationError(
                        f"provider call budget exhausted after {transient_attempts} attempts: {exc}",
                        call_records=tuple(records),
                    ) from exc
                delay = self._retry_delay(transient_attempts, exc)
                self.sleeper(delay)
                continue
            except ProviderError as exc:
                records.append(self._failed_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, exc))
                raise ProviderInvocationError(f"provider call failed: {exc}", call_records=tuple(records)) from exc

            if response.tool_calls:
                records.append(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "failed", "UndeclaredToolError", "provider returned tool calls"))
                names = ", ".join(call.name for call in response.tool_calls)
                raise UndeclaredToolError(f"provider returned undeclared tool calls: {names}", call_records=tuple(records))
            if not response.provider_request_id.strip():
                records.append(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "failed", "InvocationError", "provider response did not include a request id"))
                raise InvocationError("provider response did not include a request id", call_records=tuple(records))
            try:
                if schema == 'manager_decision.v1':
                    output = ManagerDecision.from_dict(response.output)
                elif schema == 'final_result.v1':
                    output = FinalResult.from_dict(response.output)
                else:
                    output = parse_agent_output(agent.kind, response.output)
            except (ContractValidationError, ValueError) as exc:
                message = f"{agent.kind.value} output failed {schema}: {exc}"
                records.append(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "failed", "OutputValidationError", message))
                if repairs < repairs_budget:
                    repairs += 1
                    current_request = ProviderRequest(
                        invocation_id=request.invocation_id,
                        agent_kind=request.agent_kind,
                        model=request.model,
                        system_instructions=(
                            request.system_instructions
                            + "\n\nRepair required: return only valid JSON matching the declared schema. Do not add fields."
                        ),
                        context=request.context,
                        output_schema=request.output_schema,
                    )
                    continue
                raise OutputValidationError(message, call_records=tuple(records)) from exc

            records.append(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "succeeded", None, None))
            total_cost = self._sum_costs(records)
            return AgentInvocation(
                invocation_id=invocation_id,
                agent=snapshot,
                context_manifest=built.manifest,
                provider_name=provider_name,
                provider_request_id=response.provider_request_id,
                output=output,
                usage=response.usage,
                call_records=tuple(records),
                estimated_cost=total_cost,
            )

    @staticmethod
    def _check_capabilities(capabilities: ProviderCapabilities | None, request: ProviderRequest) -> None:
        if capabilities is None:
            return
        if not capabilities.structured_outputs:
            raise RuntimeConfigurationError("provider does not support required structured outputs")
        if not capabilities.supports_model(request.model):
            raise RuntimeConfigurationError(f"provider does not support configured model {request.model!r}")

    def _retry_delay(self, attempt: int, error: ProviderTransientError) -> float:
        if isinstance(error, ProviderRateLimitError) and error.retry_after_seconds is not None:
            return error.retry_after_seconds
        if not self.retry_backoff_seconds:
            return 0.0
        return self.retry_backoff_seconds[min(attempt - 1, len(self.retry_backoff_seconds) - 1)]

    def _failed_record(self, call_id: str, invocation_id: str, attempt: int, purpose: str, provider_name: str, model: str, error: ProviderError) -> LLMCallRecord:
        return LLMCallRecord(
            call_id=call_id,
            invocation_id=invocation_id,
            attempt=attempt,
            purpose=purpose,
            provider_name=provider_name,
            model=model,
            status="failed",
            provider_request_id=None,
            usage=None,
            usage_provenance=UsageProvenance.UNKNOWN,
            usage_completeness=UsageCompleteness.UNKNOWN,
            price_snapshot=None,
            estimated_cost=None,
            error_type=type(error).__name__,
            error_message=str(error),
        )

    def _response_record(self, call_id: str, invocation_id: str, attempt: int, purpose: str, provider_name: str, model: str, response: ProviderResponse, status: str, error_type: str | None, error_message: str | None) -> LLMCallRecord:
        usage = response.usage
        price = self.pricing.price_for(model) if self.pricing is not None else None
        cost = self.pricing.estimate(model, usage) if self.pricing is not None and usage is not None else None
        return LLMCallRecord(
            call_id=call_id,
            invocation_id=invocation_id,
            attempt=attempt,
            purpose=purpose,
            provider_name=provider_name,
            model=model,
            status=status,
            provider_request_id=response.provider_request_id or None,
            usage=usage,
            usage_provenance=UsageProvenance.PROVIDER_REPORTED if usage is not None else UsageProvenance.UNKNOWN,
            usage_completeness=UsageCompleteness.COMPLETE if usage is not None else UsageCompleteness.UNKNOWN,
            price_snapshot=price,
            estimated_cost=cost,
            error_type=error_type,
            error_message=error_message,
        )

    @staticmethod
    def _sum_costs(records: list[LLMCallRecord]) -> CostEstimate | None:
        costs = [record.estimated_cost.amount for record in records if record.estimated_cost is not None]
        if not costs:
            return None
        return CostEstimate(amount=sum(costs, Decimal("0")))


def invoke_agent(
    agent: AgentDefinition,
    project: ProjectContext,
    provider: Provider,
    *,
    source_versions: dict[str, str] | None = None,
    invocation_id: str | None = None,
) -> AgentInvocation:
    """Convenience function for the development harness and small callers."""

    return AgentRuntime().invoke(
        agent,
        project,
        provider,
        source_versions=source_versions,
        invocation_id=invocation_id,
    )
