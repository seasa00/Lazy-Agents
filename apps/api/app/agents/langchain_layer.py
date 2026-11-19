"""LangChain abstractions at the Developer tool boundary.

Tools here are deliberately thin adapters: all policy, filesystem access,
receipts, and evidence remain owned by WorkspaceToolGateway.
"""
from __future__ import annotations

from typing import Any, Callable

from langchain_core.tools import BaseTool, tool

from app.domain.agents import AgentKind
from app.tools.gateway import FileToolRequest, WorkspaceToolGateway


class ApprovalRequired(RuntimeError):
    """Control transfer: the request is pending human approval, not a tool error."""
    def __init__(self, approval_id: str, tool_request_id: str, request: Any) -> None:
        super().__init__('WAITING_FOR_APPROVAL')
        self.approval_id = approval_id
        self.tool_request_id = tool_request_id
        self.request = request


class DeveloperToolAdapter:
    """Build LangChain tools bound to one Developer attempt and generation."""

    def __init__(self, gateway: WorkspaceToolGateway, attempt_id: str,
                 generation: int, *, before_tool: Callable[[], None] | None = None,
                 request_command: Callable[[Any], Any] | None = None) -> None:
        if not attempt_id or generation < 1:
            raise ValueError("attempt_id and positive generation are required")
        self.gateway = gateway
        self.attempt_id = attempt_id
        self.generation = generation
        self.before_tool = before_tool or (lambda: None)
        self.request_command = request_command

    def _execute(self, operation: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.before_tool()
        result = self.gateway.execute(FileToolRequest(
            operation, AgentKind.DEVELOPER, self.attempt_id, self.generation,
            path=path, **kwargs,
        ))
        record = self.gateway.records[-1]
        return {
            "operation_id": record.id,
            "operation": record.operation,
            "outcome": record.outcome,
            "path": record.path,
            "content": result.content,
            "content_hash": result.content_hash,
            "entries": list(result.entries),
        }

    def tools(self) -> tuple[BaseTool, ...]:
        """Return the existing file operations as structured LangChain tools."""
        adapter = self

        @tool("list_files")
        def list_files(path: str = ".") -> dict[str, Any]:
            """List files in the current approved workspace scope."""
            return adapter._execute("list", path)

        @tool("read_file")
        def read_file(path: str) -> dict[str, Any]:
            """Read a file through the workspace permission gateway."""
            return adapter._execute("read", path)

        @tool("write_file")
        def write_file(path: str, content: str, expected_hash: str | None = "") -> dict[str, Any]:
            """Write a file through the workspace permission gateway."""
            return adapter._execute("write", path, content=content, expected_hash=expected_hash)

        @tool("edit_file")
        def edit_file(path: str, old_text: str, new_text: str, expected_hash: str) -> dict[str, Any]:
            """Apply an exact text edit through the workspace permission gateway."""
            return adapter._execute("edit", path, old_text=old_text, new_text=new_text,
                                    expected_hash=expected_hash)

        tools = (list_files, read_file, write_file, edit_file)
        if adapter.request_command is None:
            return tools

        @tool('run_approved_command')
        def run_approved_command(profile: str) -> dict[str, Any]:
            """Request a configured command/test profile; execution waits for explicit user approval."""
            adapter.before_tool()
            request = adapter.gateway.command_request(profile, attempt_id=adapter.attempt_id,
                                                       generation=adapter.generation)
            approval = adapter.request_command(request)
            record = adapter.gateway.command_records[-1]
            raise ApprovalRequired(approval.id, record.id, request)

        return (*tools, run_approved_command)
