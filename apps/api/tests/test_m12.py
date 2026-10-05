from __future__ import annotations

import json
import os
import unittest
from decimal import Decimal

from app.agents.runtime import AgentRuntime, OutputValidationError, ProviderInvocationError
from app.domain.agents import AgentKind, default_agent_definitions
from app.providers.base import (
    ProviderCapabilities,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderTransientError,
    UsageSnapshot,
)
from app.providers.mock import DeterministicMockProvider, MockProviderConfig
from app.providers.openrouter import OpenRouterProviderConfig, OpenRouterResponsesProvider
from app.usage.pricing import PricingTable

from test_m11 import project_fixture


class M12ProviderTests(unittest.TestCase):
    def test_openrouter_response_normalizes_structured_output_and_usage(self) -> None:
        fixture = DeterministicMockProvider()._default_output(
            ProviderRequest("inv-1", AgentKind.MANAGER, "openai/gpt-4o-mini", "instructions", {}, "manager_plan.v1")
        )
        payload = {
            "id": "resp-1",
            "status": "completed",
            "model": "openai/gpt-4o-mini",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(fixture)}]}],
            "usage": {"input_tokens": 20, "output_tokens": 8, "input_tokens_details": {"cached_tokens": 5}},
        }

        def transport(_request, _timeout):
            return 200, {}, json.dumps(payload).encode()

        provider = OpenRouterResponsesProvider(OpenRouterProviderConfig(api_key="test-secret"), transport=transport)
        response = provider.complete(ProviderRequest("inv-1", AgentKind.MANAGER, "openai/gpt-4o-mini", "instructions", {}, "manager_plan.v1"))
        self.assertEqual(response.provider_request_id, "resp-1")
        self.assertEqual(response.usage, UsageSnapshot(20, 8, 5))
        self.assertEqual(response.output["tasks"][0]["id"], "task-1")

    def test_missing_credentials_are_rejected_before_transport(self) -> None:
        old = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with self.assertRaisesRegex(ProviderConfigurationError, "OPENROUTER_API_KEY"):
                OpenRouterResponsesProvider(OpenRouterProviderConfig()).complete(
                    ProviderRequest("inv-1", AgentKind.MANAGER, "openai/gpt-4o-mini", "instructions", {}, "manager_plan.v1")
                )
        finally:
            if old is not None:
                os.environ["OPENROUTER_API_KEY"] = old

    def test_invalid_model_slug_fails_clearly(self) -> None:
        provider = OpenRouterResponsesProvider(OpenRouterProviderConfig(api_key="test-secret"), transport=lambda *_: (_ for _ in ()).throw(AssertionError("network")))
        with self.assertRaisesRegex(ProviderCapabilityError, "model slug"):
            provider.complete(ProviderRequest("inv-1", AgentKind.MANAGER, "", "instructions", {}, "manager_plan.v1"))

    def test_provider_config_repr_does_not_expose_secret(self) -> None:
        config = OpenRouterProviderConfig(api_key="do-not-log-this")
        self.assertNotIn("do-not-log-this", repr(config))

    def test_openrouter_request_uses_slug_and_requires_compatible_route(self) -> None:
        captured = {}
        # The provider itself remains model-agnostic; use the deterministic
        # fixture only to inspect the request shape without network traffic.
        valid = DeterministicMockProvider()._default_output(
            ProviderRequest("inv-1", AgentKind.MANAGER, "anthropic/claude-sonnet-4.5", "instructions", {}, "manager_plan.v1")
        )
        payload = {
            "id": "resp-2",
            "status": "completed",
            "model": "anthropic/claude-sonnet-4.5",
            "output_text": json.dumps(valid),
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

        def anthropic_transport(request, _timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode())
            return 200, {}, json.dumps(payload).encode()

        provider = OpenRouterResponsesProvider(OpenRouterProviderConfig(api_key="test-secret"), transport=anthropic_transport)
        provider.complete(ProviderRequest("inv-1", AgentKind.MANAGER, "anthropic/claude-sonnet-4.5", "instructions", {}, "manager_plan.v1"))
        self.assertEqual(captured["url"], "https://openrouter.ai/api/v1/responses")
        self.assertEqual(captured["body"]["model"], "anthropic/claude-sonnet-4.5")
        self.assertEqual(captured["body"]["provider"], {"require_parameters": True})
        self.assertEqual(captured["body"]["text"]["format"]["type"], "json_schema")
        self.assertIn("Bearer", captured["headers"]["Authorization"])

    def test_openrouter_rate_limit_preserves_retry_after(self) -> None:
        provider = OpenRouterResponsesProvider(
            OpenRouterProviderConfig(api_key="test-secret"),
            transport=lambda *_: (429, {"Retry-After": "2.5"}, b"{}"),
        )
        with self.assertRaises(ProviderRateLimitError) as context:
            provider.complete(ProviderRequest("inv-1", AgentKind.MANAGER, "google/gemini-2.5-flash", "instructions", {}, "manager_plan.v1"))
        self.assertEqual(context.exception.retry_after_seconds, 2.5)

    def test_openrouter_timeout_is_typed(self) -> None:
        provider = OpenRouterResponsesProvider(
            OpenRouterProviderConfig(api_key="test-secret"),
            transport=lambda *_: (_ for _ in ()).throw(TimeoutError()),
        )
        with self.assertRaisesRegex(ProviderTimeoutError, "OpenRouter request timed out"):
            provider.complete(ProviderRequest("inv-1", AgentKind.MANAGER, "meta/llama-3.1-8b-instruct", "instructions", {}, "manager_plan.v1"))


class M12RuntimeTests(unittest.TestCase):
    def test_transient_retries_are_bounded_and_each_attempt_is_recorded(self) -> None:
        class FlakyProvider:
            name = "flaky"
            capabilities = ProviderCapabilities(structured_outputs=True, usage=True)

            def __init__(self) -> None:
                self.calls = 0
                self.delegate = DeterministicMockProvider()

            def complete(self, request):
                self.calls += 1
                if self.calls < 3:
                    raise ProviderRateLimitError("rate limited", retry_after_seconds=0)
                return self.delegate.complete(request)

        provider = FlakyProvider()
        delays: list[float] = []
        result = AgentRuntime(max_attempts=3, sleeper=delays.append).invoke(
            default_agent_definitions()[AgentKind.MANAGER], project_fixture(), provider, invocation_id="retry-inv"
        )
        self.assertEqual(provider.calls, 3)
        self.assertEqual([record.status for record in result.call_records], ["failed", "failed", "succeeded"])
        self.assertEqual([record.attempt for record in result.call_records], [1, 2, 3])
        self.assertEqual(delays, [0, 0])

    def test_retry_exhaustion_exposes_all_attempt_records(self) -> None:
        class AlwaysTransient:
            name = "always-transient"
            capabilities = ProviderCapabilities(structured_outputs=True)

            def complete(self, _request):
                raise ProviderTransientError("temporary failure")

        with self.assertRaises(ProviderInvocationError) as context:
            AgentRuntime(max_attempts=2, sleeper=lambda _delay: None).invoke(
                default_agent_definitions()[AgentKind.MANAGER], project_fixture(), AlwaysTransient(), invocation_id="failed-inv"
            )
        self.assertEqual(len(context.exception.call_records), 2)
        self.assertTrue(all(record.usage_provenance.value == "unknown" for record in context.exception.call_records))

    def test_invalid_structured_output_gets_one_bounded_repair(self) -> None:
        class RepairProvider:
            name = "repair-fixture"
            capabilities = ProviderCapabilities(structured_outputs=True, usage=True)

            def __init__(self) -> None:
                self.calls = 0
                self.delegate = DeterministicMockProvider()

            def complete(self, request):
                self.calls += 1
                if self.calls == 1:
                    return ProviderResponse({"invalid": True}, request.model, "bad-1", usage=UsageSnapshot(4, 2))
                return self.delegate.complete(request)

        provider = RepairProvider()
        result = AgentRuntime(max_repairs=1).invoke(
            default_agent_definitions()[AgentKind.MANAGER], project_fixture(), provider, invocation_id="repair-inv"
        )
        self.assertEqual(provider.calls, 2)
        self.assertEqual([record.purpose for record in result.call_records], ["initial", "repair"])

    def test_repair_budget_is_bounded(self) -> None:
        provider = DeterministicMockProvider(config=MockProviderConfig(mode="invalid"))
        with self.assertRaises(OutputValidationError) as context:
            AgentRuntime(max_repairs=1).invoke(
                default_agent_definitions()[AgentKind.MANAGER], project_fixture(), provider, invocation_id="bad-inv"
            )
        self.assertEqual(len(context.exception.call_records), 2)


class M12PricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pricing = PricingTable.from_dict(
            {
                "version": "test-1",
                "source": "test",
                "currency": "USD",
                "models": {
                    "test-model": {
                        "input_usd_per_million": "1.00",
                        "cached_input_usd_per_million": "0.25",
                        "output_usd_per_million": "2.00",
                    }
                },
            }
        )

    def test_cached_tokens_are_not_double_counted(self) -> None:
        cost = self.pricing.estimate("test-model", UsageSnapshot(100, 50, 40))
        self.assertIsNotNone(cost)
        self.assertEqual(cost.amount, Decimal("0.00017000"))

    def test_unknown_pricing_is_labeled_as_unknown(self) -> None:
        self.assertIsNone(self.pricing.estimate("not-configured", UsageSnapshot(1, 1)))


if __name__ == "__main__":
    unittest.main()
