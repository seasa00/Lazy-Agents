"""Per-attempt call records with explicit usage provenance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.providers.base import UsageSnapshot
from app.usage.pricing import CostEstimate, PriceSnapshot


class UsageProvenance(StrEnum):
    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class UsageCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LLMCallRecord:
    """One submitted provider request, including failed and retry attempts."""

    call_id: str
    invocation_id: str
    attempt: int
    purpose: str
    provider_name: str
    model: str
    status: str
    provider_request_id: str | None
    usage: UsageSnapshot | None
    usage_provenance: UsageProvenance
    usage_completeness: UsageCompleteness
    price_snapshot: PriceSnapshot | None
    estimated_cost: CostEstimate | None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def request_id(self) -> str:
        """Stable local request identifier; provider_request_id may be absent on failure."""

        return self.call_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "request_id": self.request_id,
            "invocation_id": self.invocation_id,
            "attempt": self.attempt,
            "purpose": self.purpose,
            "provider_name": self.provider_name,
            "model": self.model,
            "status": self.status,
            "provider_request_id": self.provider_request_id,
            "usage": None if self.usage is None else self.usage.to_dict(),
            "usage_provenance": self.usage_provenance.value,
            "usage_completeness": self.usage_completeness.value,
            "price_snapshot": None if self.price_snapshot is None else self.price_snapshot.to_dict(),
            "estimated_cost": None if self.estimated_cost is None else self.estimated_cost.to_dict(),
            "error_type": self.error_type,
            "error_message": self.error_message,
        }
