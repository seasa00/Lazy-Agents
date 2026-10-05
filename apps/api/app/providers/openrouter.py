"""Standard-library adapter for OpenRouter's OpenResponses endpoint.

OpenRouter exposes an OpenAI-compatible Responses API while routing model
slugs across multiple underlying providers. This module owns only that HTTP
and response-normalization detail; the runtime depends on ``Provider`` and
``ProviderResponse`` from the provider-neutral boundary.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.providers.base import (
    ProviderCapabilities,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderToolCall,
    ProviderTransientError,
    UsageSnapshot,
)
from app.providers.schemas import schema_for_output


Transport = Callable[[Request, float], tuple[int, Mapping[str, str], bytes]]


def _default_transport(request: Request, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - URL is configured explicitly.
            return int(response.status), dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return int(exc.code), dict(exc.headers.items()), exc.read()


@dataclass(frozen=True, slots=True)
class OpenRouterProviderConfig:
    """Backend-only OpenRouter settings.

    The model is deliberately absent here: model slugs belong to agent
    configuration/CLI selection so changing from OpenAI to Anthropic, Google,
    or another OpenRouter model does not change runtime code.
    """

    api_key: str | None = field(default=None, repr=False)
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 30.0
    require_parameters: bool = True
    http_referer: str | None = None
    app_title: str | None = None

    def resolved_api_key(self) -> str:
        value = self.api_key or os.getenv("OPENROUTER_API_KEY")
        if not value or not value.strip():
            raise ProviderConfigurationError("OPENROUTER_API_KEY is required for the openrouter provider")
        return value.strip()

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("https://", "http://")):
            raise ProviderConfigurationError("OpenRouter base_url must be an http(s) URL")
        if self.timeout_seconds <= 0:
            raise ProviderConfigurationError("OpenRouter timeout_seconds must be positive")


class OpenRouterResponsesProvider:
    """OpenRouter Responses adapter with provider-neutral normalization."""

    name = "openrouter-responses"
    capabilities = ProviderCapabilities(
        structured_outputs=True,
        tools=False,
        usage=True,
        # OpenRouter model slugs are intentionally not hard-coded. Endpoint
        # compatibility is enforced by provider.require_parameters and the
        # final application-level schema validation.
        supported_models=(),
    )

    def __init__(self, config: OpenRouterProviderConfig | None = None, *, transport: Transport | None = None) -> None:
        self.config = config or OpenRouterProviderConfig()
        self._transport = transport or _default_transport

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self._validate_model_slug(request.model)
        schema = schema_for_output(request.output_schema)
        payload = {
            "model": request.model,
            "instructions": request.system_instructions,
            "input": json.dumps(request.context, sort_keys=True, separators=(",", ":")),
            "store": False,
            "provider": {"require_parameters": self.config.require_parameters},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.output_schema.replace(".", "_"),
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.resolved_api_key()}",
            "Content-Type": "application/json",
            "X-Client-Request-Id": request.invocation_id,
        }
        if self.config.http_referer:
            headers["HTTP-Referer"] = self.config.http_referer
        if self.config.app_title:
            headers["X-OpenRouter-Title"] = self.config.app_title
        http_request = Request(
            url=f"{self.config.base_url.rstrip('/')}/responses",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            status, response_headers, raw = self._transport(http_request, self.config.timeout_seconds)
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderTimeoutError("OpenRouter request timed out") from exc
        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise ProviderTimeoutError("OpenRouter request timed out") from exc
            raise ProviderResponseError("OpenRouter request could not be sent") from exc
        if status == 429:
            raise ProviderRateLimitError(
                "OpenRouter rate limit response",
                retry_after_seconds=_retry_after(response_headers.get("Retry-After")),
            )
        if status in {408, 409} or status >= 500:
            raise ProviderTransientError(f"OpenRouter transient HTTP response {status}")
        if status in {401, 402, 403}:
            raise ProviderConfigurationError("OpenRouter authentication, billing, or permission failed")
        if status < 200 or status >= 300:
            raise ProviderResponseError(f"OpenRouter request failed with HTTP {status}")
        return self._normalize_response(raw, request)

    @staticmethod
    def _validate_model_slug(model: str) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ProviderCapabilityError("OpenRouter requires a non-empty model slug")

    def _normalize_response(self, raw: bytes, request: ProviderRequest) -> ProviderResponse:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("OpenRouter returned non-JSON data") from exc
        if not isinstance(payload, Mapping):
            raise ProviderResponseError("OpenRouter response must be an object")
        response_id = payload.get("id")
        if not isinstance(response_id, str) or not response_id.strip():
            raise ProviderResponseError("OpenRouter response did not include an id")
        status = payload.get("status")
        if status != "completed":
            raise ProviderResponseError(f"OpenRouter response was not completed: {status!r}")
        tool_calls = _tool_calls(payload.get("output"))
        output_text = _output_text(payload)
        if output_text is None:
            if tool_calls:
                output: Any = {}
            else:
                raise ProviderResponseError("OpenRouter response contained no output text")
        else:
            try:
                output = json.loads(output_text)
            except json.JSONDecodeError as exc:
                raise ProviderResponseError("OpenRouter structured output was not valid JSON") from exc
        return ProviderResponse(
            output=output,
            model=str(payload.get("model") or request.model),
            provider_request_id=response_id,
            tool_calls=tool_calls,
            usage=_usage(payload.get("usage")),
        )


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _usage(value: object) -> UsageSnapshot | None:
    if not isinstance(value, Mapping):
        return None
    input_tokens = value.get("input_tokens", value.get("prompt_tokens"))
    output_tokens = value.get("output_tokens", value.get("completion_tokens"))
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return None
    details = value.get("input_tokens_details", value.get("prompt_tokens_details"))
    cached = details.get("cached_tokens", 0) if isinstance(details, Mapping) else 0
    if not isinstance(cached, int):
        cached = 0
    try:
        return UsageSnapshot(input_tokens=input_tokens, output_tokens=output_tokens, cached_input_tokens=cached)
    except ValueError as exc:
        raise ProviderResponseError("OpenRouter returned invalid token usage") from exc


def _output_text(payload: Mapping[str, Any]) -> str | None:
    direct = payload.get("output_text")
    if isinstance(direct, str):
        return direct
    output = payload.get("output")
    if not isinstance(output, list):
        return None
    parts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, Mapping) and block.get("type") == "output_text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "".join(parts) or None


def _tool_calls(value: object) -> tuple[ProviderToolCall, ...]:
    if not isinstance(value, list):
        return ()
    calls: list[ProviderToolCall] = []
    for item in value:
        if not isinstance(item, Mapping) or item.get("type") != "function_call":
            continue
        name = item.get("name")
        arguments = item.get("arguments", "{}")
        if not isinstance(name, str):
            raise ProviderResponseError("OpenRouter returned a tool call without a name")
        try:
            parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError as exc:
            raise ProviderResponseError("OpenRouter returned invalid tool arguments") from exc
        if not isinstance(parsed, Mapping):
            raise ProviderResponseError("OpenRouter tool arguments must be an object")
        calls.append(ProviderToolCall(name=name, arguments=parsed))
    return tuple(calls)


# Short aliases keep the adapter easy to discover without changing the
# provider-neutral interface used by the runtime.
OpenRouterConfig = OpenRouterProviderConfig
OpenRouterProvider = OpenRouterResponsesProvider
