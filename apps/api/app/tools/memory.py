"""Pure controlled tool: captures synthetic evidence without external effects."""
from app.domain.agents import AgentKind
from app.tools.contracts import ToolRequest, ToolResult


class InMemoryToolGateway:
    def execute(self, request: ToolRequest) -> ToolResult:
        if request.operation != 'capture_submission' or request.actor is not AgentKind.DEVELOPER:
            raise ValueError('only Developer may capture synthetic output; Reviewer is read-only')
        if not request.submission_id or request.generation < 1 or not request.content:
            raise ValueError('missing controlled tool evidence')
        if any(not isinstance(s, str) or not s.strip() for s in request.content):
            raise ValueError('invalid synthetic evidence')
        return ToolResult(request.submission_id, tuple(request.content))
