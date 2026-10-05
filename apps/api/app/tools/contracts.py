"""Minimal gateway boundary for synthetic submission evidence."""
from dataclasses import dataclass
from typing import Protocol
from app.domain.agents import AgentKind


@dataclass(frozen=True, slots=True)
class ToolRequest:
    operation: str
    actor: AgentKind
    submission_id: str
    generation: int
    content: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolResult:
    submission_id: str
    evidence: tuple[str, ...]


class ToolGateway(Protocol):
    def execute(self, request: ToolRequest) -> ToolResult: ...
