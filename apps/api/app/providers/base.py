"""Provider-neutral contracts for the isolated agent runtime.

The contracts in this module intentionally do not mention a vendor SDK.  A
provider adapter normalizes its response into these types before the runtime
validates the role-specific output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.domain.agents import AgentKind


class ProviderError(RuntimeError):
    """Base class for provider failures; retry behavior is runtime-controlled."""


class ProviderConfigurationError(ProviderError):
    """Raised when a provider cannot satisfy an invocation request."""


class ProviderCapabilityError(ProviderError):
    """Raised when a provider or model lacks a required capability."""


class ProviderTransientError(ProviderError):
    """A bounded-retry candidate such as a rate limit or server failure."""


class ProviderRateLimitError(ProviderTransientError):
    """The provider rejected the request because a rate limit was reached."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderTimeoutError(ProviderTransientError):
    """The provider did not respond within the configured timeout."""


class ProviderResponseError(ProviderError):
    """The provider returned an unusable response or a non-retryable error."""


@dataclass(frozen=True, slots=True)
class ProviderToolCall:
    """A normalized tool request; the runtime rejects calls until tools ship."""

    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """Normalized token usage.

    ``input_tokens`` is the total input count reported by the provider and
    ``cached_input_tokens`` is a subset of it.  Cost calculation applies the
    uncached rate to the remainder, so cached tokens are never double-counted.
    """

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0 or self.cached_input_tokens < 0:
            raise ValueError("token counts must be non-negative")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")

    @property
    def uncached_input_tokens(self) -> int:
        return self.input_tokens - self.cached_input_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Capabilities declared by an adapter before a request is submitted."""

    structured_outputs: bool = False
    tools: bool = False
    usage: bool = False
    supported_models: tuple[str, ...] = ()

    def supports_model(self, model: str) -> bool:
        return not self.supported_models or model in self.supported_models


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    invocation_id: str
    agent_kind: AgentKind
    model: str
    system_instructions: str
    context: Mapping[str, Any]
    output_schema: str


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    output: Any
    model: str
    provider_request_id: str
    tool_calls: tuple[ProviderToolCall, ...] = ()
    usage: UsageSnapshot | None = None


class Provider(Protocol):
    """Minimal provider interface used by the shared runtime."""

    name: str
    capabilities: ProviderCapabilities

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return one structured response for one invocation."""
