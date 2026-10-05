"""Decimal model pricing and cost estimation.

Rates are configuration snapshots, expressed as USD per one million tokens.
Unknown pricing is represented by ``None`` rather than a fabricated zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping

from app.providers.base import UsageSnapshot


class PricingConfigurationError(ValueError):
    """Raised when a pricing configuration is malformed."""


def _decimal(value: object, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception as exc:  # Decimal raises several concrete exceptions.
        raise PricingConfigurationError(f"{field} must be a decimal number") from exc
    if number < 0:
        raise PricingConfigurationError(f"{field} must be non-negative")
    return number


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    model: str
    currency: str
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    source: str
    version: str

    def __post_init__(self) -> None:
        if not self.model.strip() or self.currency != "USD" or not self.source.strip() or not self.version.strip():
            raise PricingConfigurationError("price snapshot has invalid identity fields")
        for value in (
            self.input_usd_per_million,
            self.cached_input_usd_per_million,
            self.output_usd_per_million,
        ):
            if value < 0:
                raise PricingConfigurationError("pricing rates must be non-negative")

    def to_dict(self) -> dict[str, str]:
        return {
            "model": self.model,
            "currency": self.currency,
            "input_usd_per_million": str(self.input_usd_per_million),
            "cached_input_usd_per_million": str(self.cached_input_usd_per_million),
            "output_usd_per_million": str(self.output_usd_per_million),
            "source": self.source,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class CostEstimate:
    amount: Decimal
    currency: str = "USD"

    def to_dict(self) -> dict[str, str]:
        return {"amount": str(self.amount), "currency": self.currency}


class PricingTable:
    """Immutable lookup table for model price snapshots."""

    def __init__(self, prices: Mapping[str, PriceSnapshot]) -> None:
        self._prices = dict(prices)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PricingTable":
        if set(data) != {"version", "source", "currency", "models"}:
            missing = {"version", "source", "currency", "models"} - set(data)
            extra = set(data) - {"version", "source", "currency", "models"}
            details = []
            if missing:
                details.append(f"missing fields: {', '.join(sorted(missing))}")
            if extra:
                details.append(f"unknown fields: {', '.join(sorted(extra))}")
            raise PricingConfigurationError("invalid pricing table: " + "; ".join(details))
        if not isinstance(data["models"], Mapping):
            raise PricingConfigurationError("models must be an object")
        version = str(data["version"])
        source = str(data["source"])
        currency = str(data["currency"]).upper()
        prices: dict[str, PriceSnapshot] = {}
        for model, raw in data["models"].items():
            if not isinstance(model, str) or not isinstance(raw, Mapping):
                raise PricingConfigurationError("each model price must be an object")
            required = {"input_usd_per_million", "cached_input_usd_per_million", "output_usd_per_million"}
            if set(raw) != required:
                raise PricingConfigurationError(f"invalid pricing fields for {model}")
            prices[model] = PriceSnapshot(
                model=model,
                currency=currency,
                input_usd_per_million=_decimal(raw["input_usd_per_million"], f"{model}.input"),
                cached_input_usd_per_million=_decimal(raw["cached_input_usd_per_million"], f"{model}.cached_input"),
                output_usd_per_million=_decimal(raw["output_usd_per_million"], f"{model}.output"),
                source=source,
                version=version,
            )
        return cls(prices)

    @classmethod
    def from_json(cls, path: str | Path) -> "PricingTable":
        with Path(path).open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, Mapping):
            raise PricingConfigurationError("pricing file must contain an object")
        return cls.from_dict(value)

    def price_for(self, model: str) -> PriceSnapshot | None:
        return self._prices.get(model)

    def estimate(self, model: str, usage: UsageSnapshot) -> CostEstimate | None:
        price = self.price_for(model)
        if price is None:
            return None
        million = Decimal(1_000_000)
        amount = (
            Decimal(usage.uncached_input_tokens) * price.input_usd_per_million
            + Decimal(usage.cached_input_tokens) * price.cached_input_usd_per_million
            + Decimal(usage.output_tokens) * price.output_usd_per_million
        ) / million
        return CostEstimate(amount=amount.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))
