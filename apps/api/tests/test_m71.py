from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.agents.langchain_layer import DeveloperToolAdapter
from app.agents.runtime import AgentRuntime, InvocationError, UndeclaredToolError
from app.domain.agents import AgentKind
from app.domain.agents import default_agent_definitions
from app.permissions.policy import WorkspacePolicy
from app.providers.base import ProviderCapabilities, ProviderResponse, ProviderToolCall, UsageSnapshot
from app.tools.gateway import WorkspaceToolGateway
from tests.test_m11 import project_fixture


class LangChainDeveloperToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name) / "work"
        self.root.mkdir()
        (self.root / "hello.txt").write_text("hello\n")
        self.gateway = WorkspaceToolGateway(
            WorkspacePolicy(self.root), before_mutation=lambda request: None,
        )
        self.tools = {tool.name: tool for tool in DeveloperToolAdapter(
            self.gateway, "attempt-1", 1,
        ).tools()}

    def tearDown(self):
        self.temp.cleanup()

    def test_list_read_edit_write_use_gateway_and_return_receipts(self):
        listed = self.tools["list_files"].invoke({"path": "."})
        self.assertEqual(listed["entries"], ["hello.txt"])
        read = self.tools["read_file"].invoke({"path": "hello.txt"})
        self.assertEqual(read["content"], "hello\n")
        self.assertEqual(read["outcome"], "succeeded")
        edited = self.tools["edit_file"].invoke({
            "path": "hello.txt", "old_text": "hello", "new_text": "hello world",
            "expected_hash": read["content_hash"],
        })
        self.assertTrue(edited["operation_id"].startswith("file_"))
        written = self.tools["write_file"].invoke({
            "path": "new.txt", "content": "new", "expected_hash": None,
        })
        self.assertEqual(written["outcome"], "succeeded")
        self.assertEqual((self.root / "hello.txt").read_text(), "hello world\n")
        self.assertEqual((self.root / "new.txt").read_text(), "new")
        self.assertTrue(all(r.actor == AgentKind.DEVELOPER.value for r in self.gateway.records))

    def test_protected_paths_and_gateway_failures_remain_failures(self):
        with self.assertRaisesRegex(ValueError, "protected path denied"):
            self.tools["read_file"].invoke({"path": ".env.local"})
        self.assertEqual(self.gateway.records[-1].outcome, "denied")

    def test_tool_checks_execution_boundary_before_gateway(self):
        calls = []
        tool = DeveloperToolAdapter(self.gateway, "attempt-1", 1,
                                    before_tool=lambda: calls.append("checked") or (_ for _ in ()).throw(RuntimeError("paused"))).tools()[1]
        with self.assertRaisesRegex(RuntimeError, "paused"):
            tool.invoke({"path": "hello.txt"})
        self.assertEqual(calls, ["checked"])
        self.assertEqual(self.gateway.records, ())

    def test_runtime_loops_through_langchain_tool_and_accounts_each_model_call(self):
        class Provider:
            name = "fixture"
            capabilities = ProviderCapabilities(structured_outputs=True, tools=True, usage=True)
            def __init__(self): self.requests = []
            def complete(self, request):
                self.requests.append(request)
                if len(self.requests) == 1:
                    return ProviderResponse({}, request.model, "req-tool", (
                        ProviderToolCall("list_files", {"path": "."}),
                    ), UsageSnapshot(10, 2))
                self.assert_tool_result(request)
                return ProviderResponse({
                    "submission_id": "attempt-1:submission", "task_id": "task-1",
                    "output_version": 1, "summary": "ready", "changed_files": [],
                    "tests": [], "ready_for_review": True, "notes": [],
                }, request.model, "req-final", usage=UsageSnapshot(12, 4))
            @staticmethod
            def assert_tool_result(request):
                assert request.context["tool_results"][0]["result"]["entries"] == ["hello.txt"]

        from langchain_core.tools import tool
        @tool
        def list_files(path: str = ".") -> dict:
            """List workspace files."""
            return self.tools["list_files"].invoke({"path": path})

        provider = Provider()
        result = AgentRuntime().invoke(
            default_agent_definitions()[AgentKind.DEVELOPER], project_fixture(), provider,
            invocation_id="attempt-1", langchain_tools=(list_files,),
        )
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(len(result.call_records), 2)
        self.assertEqual(result.usage.total_tokens, 28)
        self.assertEqual(result.output.submission_id, "attempt-1:submission")
        self.assertEqual(len(self.gateway.records), 1)

    def test_runtime_rejects_undeclared_or_excess_tool_calls(self):
        class Provider:
            name = "fixture"
            capabilities = ProviderCapabilities(structured_outputs=True, tools=True)
            def complete(self, request):
                return ProviderResponse({}, request.model, "req-tool", (
                    ProviderToolCall("shell", {}),
                ))
        from langchain_core.tools import tool
        @tool
        def list_files(path: str = ".") -> dict:
            """List files."""
            return {}
        with self.assertRaises(UndeclaredToolError):
            AgentRuntime().invoke(default_agent_definitions()[AgentKind.DEVELOPER],
                project_fixture(), Provider(), langchain_tools=(list_files,))

    def test_denied_model_requested_tool_fails_and_keeps_call_accounting(self):
        class Provider:
            name = "fixture"
            capabilities = ProviderCapabilities(structured_outputs=True, tools=True, usage=True)
            def complete(self, request):
                return ProviderResponse({}, request.model, "req-denied", (
                    ProviderToolCall("read_file", {"path": ".env.local"}),
                ), UsageSnapshot(7, 2))
        with self.assertRaises(InvocationError) as raised:
            AgentRuntime().invoke(default_agent_definitions()[AgentKind.DEVELOPER],
                project_fixture(), Provider(), invocation_id="denied",
                langchain_tools=(self.tools["read_file"],))
        self.assertEqual(len(raised.exception.call_records), 1)
        self.assertEqual(raised.exception.call_records[0].usage.input_tokens, 7)
        self.assertEqual(self.gateway.records[-1].outcome, "denied")

    def test_tool_loop_stops_at_configured_bound(self):
        class Provider:
            name = "fixture"
            capabilities = ProviderCapabilities(structured_outputs=True, tools=True)
            def complete(self, request):
                return ProviderResponse({}, request.model, "req-loop", (
                    ProviderToolCall("list_files", {"path": "."}),
                ))
        with self.assertRaisesRegex(UndeclaredToolError, "limit reached"):
            AgentRuntime().invoke(default_agent_definitions()[AgentKind.DEVELOPER],
                project_fixture(), Provider(), langchain_tools=(self.tools["list_files"],),
                max_tool_calls=1)
        self.assertEqual(len(self.gateway.records), 1)


if __name__ == "__main__":
    unittest.main()
