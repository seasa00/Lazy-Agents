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
from app.agents.langchain_layer import ApprovalRequired
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


class AgentExecutionSuspended(InvocationError):
    """A tool requested human approval; carries only normalized continuation data."""
    def __init__(self, message, *, approval_id, tool_request_id, request, tool_call,
                 context, provider_request_id, provider_calls, tool_calls, retry_attempts,
                 call_records=()):
        super().__init__(message, call_records=call_records)
        self.approval_id = approval_id
        self.tool_request_id = tool_request_id
        self.command_request = request
        self.tool_call = tool_call
        self.context = context
        self.provider_request_id = provider_request_id
        self.provider_calls = provider_calls
        self.tool_calls = tool_calls
        self.retry_attempts = retry_attempts


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
        on_call_started: Any = None,
        on_call_finished: Any = None,
        langchain_tools: tuple[Any, ...] = (),
        max_tool_calls: int = 8,
        initial_context: dict[str, Any] | None = None,
        call_number_offset: int = 0,
        tool_call_offset: int = 0,
        on_tool_call: Any = None,
        on_tool_result: Any = None,
    ) -> AgentInvocation:
        """Build context, make bounded calls, and validate one role output."""

        if agent.tools or agent.permissions:
            raise RuntimeConfigurationError(
                "Configured tools or permissions are unavailable until the tools milestone; agent definitions must be tool-free"
            )
        if langchain_tools and agent.kind.value != "developer":
            raise RuntimeConfigurationError("LangChain tools are available only to Developer")
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be positive")
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
            tools=tuple({"type": "function", "name": item.name, "description": item.description,
                         "parameters": item.args_schema.model_json_schema(), "strict": True}
                        for item in langchain_tools),
        )
        capabilities = getattr(provider, "capabilities", None)
        self._check_capabilities(capabilities, request)
        provider_name = getattr(provider, "name", provider.__class__.__name__)
        attempts_budget = self.max_attempts if max_attempts is None else max_attempts
        repairs_budget = self.max_repairs if max_repairs is None else max_repairs
        if attempts_budget < 1 or repairs_budget < 0:
            raise ValueError("max_attempts must be positive and max_repairs must be non-negative")

        records: list[LLMCallRecord] = []
        def retain(record, output=None):
            if on_call_finished is not None:
                on_call_finished(record, output)
            records.append(record)

        transient_attempts = 0
        repairs = 0
        attempt_number = call_number_offset
        tool_calls_used = tool_call_offset
        current_request = request
        if initial_context is not None:
            current_request = replace(request, context=initial_context)
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
            if on_call_started is not None:
                reserved_call = LLMCallRecord(call_id, invocation_id, attempt_number, purpose,
                    provider_name, snapshot.model, 'submitted', None, None,
                    UsageProvenance.UNKNOWN, UsageCompleteness.UNKNOWN,
                    self.pricing.price_for(snapshot.model) if self.pricing else None, None)
                on_call_started(reserved_call)
            try:
                response = provider.complete(current_request)
            except ProviderTransientError as exc:
                transient_attempts += 1
                retain(self._failed_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, exc))
                if transient_attempts >= attempts_budget:
                    raise ProviderInvocationError(
                        f"provider call budget exhausted after {transient_attempts} attempts: {exc}",
                        call_records=tuple(records),
                    ) from exc
                delay = self._retry_delay(transient_attempts, exc)
                self.sleeper(delay)
                continue
            except ProviderError as exc:
                retain(self._failed_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, exc))
                raise ProviderInvocationError(f"provider call failed: {exc}", call_records=tuple(records)) from exc

            if response.tool_calls:
                if langchain_tools and agent.kind.value == "developer":
                    if (any(call.name == 'run_approved_command' for call in response.tool_calls)
                            and len(response.tool_calls) != 1):
                        retain(self._response_record(call_id, invocation_id, attempt_number, purpose,
                            provider_name, snapshot.model, response, "failed", "ToolBatchUnsupported",
                            "approval tools must be the sole call in a provider response"))
                        raise UndeclaredToolError("approval tools must be requested one at a time",
                                                  call_records=tuple(records))
                    by_name = {item.name: item for item in langchain_tools}
                    results = []
                    for tool_call in response.tool_calls:
                        if tool_calls_used >= max_tool_calls:
                            retain(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "failed", "ToolBudgetExceeded", "Developer tool-call limit reached"))
                            raise UndeclaredToolError("Developer tool-call limit reached", call_records=tuple(records))
                        target = by_name.get(tool_call.name)
                        if target is None:
                            retain(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "failed", "UndeclaredToolError", "provider returned undeclared tool calls"))
                            raise UndeclaredToolError(f"provider returned undeclared tool call: {tool_call.name}", call_records=tuple(records))
                        try:
                            if on_tool_call is not None:
                                on_tool_call(tool_call.name, dict(tool_call.arguments), tool_calls_used + 1,
                                             dict(current_request.context), response.provider_request_id,
                                             attempt_number, transient_attempts)
                            result = target.invoke(dict(tool_call.arguments))
                        except ApprovalRequired as exc:
                            retain(self._response_record(call_id, invocation_id, attempt_number, purpose,
                                provider_name, snapshot.model, response, "succeeded", None, None))
                            raise AgentExecutionSuspended(
                                'WAITING_FOR_APPROVAL', approval_id=exc.approval_id,
                                tool_request_id=exc.tool_request_id, request=exc.request,
                                tool_call={'name': tool_call.name, 'arguments': dict(tool_call.arguments)},
                                context=dict(current_request.context),
                                provider_request_id=response.provider_request_id,
                                provider_calls=attempt_number, tool_calls=tool_calls_used + 1,
                                retry_attempts=transient_attempts,
                                call_records=tuple(records)) from exc
                        except InvocationError as exc:
                            retain(self._response_record(call_id, invocation_id, attempt_number, purpose,
                                provider_name, snapshot.model, response, "succeeded", None, None))
                            exc.call_records = tuple(records)
                            raise
                        except Exception as exc:
                            retain(self._response_record(call_id, invocation_id, attempt_number, purpose,
                                provider_name, snapshot.model, response, "failed", type(exc).__name__,
                                f"LangChain tool {tool_call.name} failed"))
                            raise InvocationError(
                                f"Developer tool {tool_call.name} failed: {type(exc).__name__}",
                                call_records=tuple(records),
                            ) from exc
                        results.append({"tool_call_id": tool_call.name, "result": result})
                        tool_calls_used += 1
                        if on_tool_result is not None:
                            progress_context = {**dict(current_request.context), "tool_results": list(results)}
                            on_tool_result(progress_context)
                    retain(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "succeeded", None, None))
                    next_context = {**dict(current_request.context), "tool_results": results}
                    if len(json.dumps(next_context, ensure_ascii=False, separators=(",", ":"))) > agent.context_policy.max_chars:
                        raise RuntimeConfigurationError("LangChain tool results exceed the configured context budget",
                                                         call_records=tuple(records))
                    current_request = ProviderRequest(
                        invocation_id=request.invocation_id, agent_kind=request.agent_kind,
                        model=request.model, system_instructions=request.system_instructions,
                        context=next_context,
                        output_schema=request.output_schema,
                        tools=request.tools,
                    )
                    continue
                retain(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "failed", "UndeclaredToolError", "provider returned tool calls"))
                names = ", ".join(call.name for call in response.tool_calls)
                raise UndeclaredToolError(f"provider returned undeclared tool calls: {names}", call_records=tuple(records))
            if not response.provider_request_id.strip():
                retain(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "failed", "InvocationError", "provider response did not include a request id"))
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
                retain(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "failed", "OutputValidationError", message))
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
                        tools=request.tools,
                    )
                    continue
                raise OutputValidationError(message, call_records=tuple(records)) from exc

            retain(self._response_record(call_id, invocation_id, attempt_number, purpose, provider_name, snapshot.model, response, "succeeded", None, None), output)
            total_cost = self._sum_costs(records)
            return AgentInvocation(
                invocation_id=invocation_id,
                agent=snapshot,
                context_manifest=built.manifest,
                provider_name=provider_name,
                provider_request_id=response.provider_request_id,
                output=output,
                usage=self._sum_usage(records),
                call_records=tuple(records),
                estimated_cost=total_cost,
            )

    @staticmethod
    def _check_capabilities(capabilities: ProviderCapabilities | None, request: ProviderRequest) -> None:
        if capabilities is None:
            return
        if not capabilities.structured_outputs:
            raise RuntimeConfigurationError("provider does not support required structured outputs")
        if request.tools and not capabilities.tools:
            raise RuntimeConfigurationError("provider does not support declared tools")
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

    @staticmethod
    def _sum_usage(records: list[LLMCallRecord]) -> UsageSnapshot | None:
        """Return complete invocation usage only when every submitted call is known."""
        if not records or any(record.usage is None for record in records):
            return None
        return UsageSnapshot(
            input_tokens=sum(record.usage.input_tokens for record in records),
            output_tokens=sum(record.usage.output_tokens for record in records),
            cached_input_tokens=sum(record.usage.cached_input_tokens for record in records),
        )


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
