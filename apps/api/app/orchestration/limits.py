"""Lifetime run budgets; quality rounds and technical requests are separate."""
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    max_review_rounds: int = 3
    max_invocations: int = 60
    max_llm_calls: int = 100
    max_calls_per_invocation: int = 4
    max_provider_attempts: int = 3
    max_repairs: int = 1
    max_tasks: int = 20
    max_replans: int = 2
    max_iterations: int = 200

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            minimum = 0 if field.name in {'max_repairs', 'max_replans'} else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f'invalid {field.name}')


class LimitExceeded(ValueError):
    pass
