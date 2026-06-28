from __future__ import annotations

import importlib
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from coder_workbench.server.app import create_app


LEGACY_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]


REMOVED_FILES = [
    "src/coder_workbench/core/schema.py",
    "src/coder_workbench/core/legacy_compile.py",
    "src/coder_workbench/core/legacy_artifacts.py",
    "src/coder_workbench/core/preflight.py",
    "src/coder_workbench/runtime/runner.py",
    "src/coder_workbench/runtime/node_executor.py",
    "src/coder_workbench/runtime/context.py",
    "src/coder_workbench/runtime/conditions.py",
    "src/coder_workbench/runtime/artifact_recorder.py",
    "src/coder_workbench/server/manager.py",
]


OLD_SYMBOL_PATTERNS = {
    "WorkflowSpec": re.compile(r"(?<!Agent)\bWorkflowSpec\b"),
    "NodeSpec": re.compile(r"\bNodeSpec\b"),
    "EdgeSpec": re.compile(r"\bEdgeSpec\b"),
    "AgentSpec": re.compile(r"(?<!Workflow)\bAgentSpec\b"),
    "ContextPolicy": re.compile(r"\bContextPolicy\b"),
    "PermissionPolicy": re.compile(r"\bPermissionPolicy\b"),
    "load_workflow": re.compile(r"\bload_workflow\b"),
    "run_workflow": re.compile(r"\brun_workflow\b"),
    "WorkflowRunner": re.compile(r"\bWorkflowRunner\b"),
    "legacy_compile": re.compile(r"\blegacy_compile\b"),
    "compile_agent_workflow": re.compile(r"\bcompile_agent_workflow\b"),
    "compile_agent_workflow_legacy_preview": re.compile(r"\bcompile_agent_workflow_legacy_preview\b"),
    "_compile_agent_workflow_legacy_impl": re.compile(r"\b_compile_agent_workflow_legacy_impl\b"),
    "old_workflow_endpoint": re.compile(r"/api/v2/workflows\b"),
    "old_live_runs_endpoint": re.compile(r"/api/v2/live-runs\b"),
    "old_compile_endpoint": re.compile(r"/api/v2/agent-workflows/compile\b"),
    "old_library_endpoint": re.compile(r"/api/v2/library/workflows\b"),
}


class NoLegacyWorkflowRuntimeTests(unittest.TestCase):
    def test_legacy_runtime_files_are_removed(self) -> None:
        for relative_path in REMOVED_FILES:
            with self.subTest(path=relative_path):
                self.assertFalse((LEGACY_ROOT / relative_path).exists())

    def test_core_and_runtime_do_not_export_legacy_symbols(self) -> None:
        core = importlib.import_module("coder_workbench.core")
        runtime = importlib.import_module("coder_workbench.runtime")
        for module in [core, runtime]:
            exported = set(getattr(module, "__all__", []))
            for symbol in [
                "WorkflowSpec",
                "NodeSpec",
                "EdgeSpec",
                "AgentSpec",
                "ContextPolicy",
                "PermissionPolicy",
                "load_workflow",
                "run_workflow",
                "WorkflowRunner",
            ]:
                with self.subTest(module=module.__name__, symbol=symbol):
                    self.assertFalse(hasattr(module, symbol))
                    self.assertNotIn(symbol, exported)

    def test_product_source_has_no_legacy_workflow_runtime_symbols(self) -> None:
        for path in _source_files("src/coder_workbench"):
            if path.name == "state.py" and path.parent.name == "runtime":
                continue
            source = path.read_text(encoding="utf-8")
            for name, pattern in OLD_SYMBOL_PATTERNS.items():
                with self.subTest(path=str(path.relative_to(ROOT)), symbol=name):
                    self.assertIsNone(pattern.search(source))

    def test_frontend_source_has_no_legacy_workflow_runtime_symbols(self) -> None:
        for path in _source_files("frontend/src"):
            source = path.read_text(encoding="utf-8")
            for name, pattern in OLD_SYMBOL_PATTERNS.items():
                with self.subTest(path=str(path.relative_to(ROOT)), symbol=name):
                    self.assertIsNone(pattern.search(source))

    def test_old_workflow_api_routes_are_not_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(store_root=tmp, frontend_dist=tmp)
            route_paths = {getattr(route, "path", "") for route in app.routes}
            client = TestClient(app)

            self.assertEqual(client.get("/api/v2/live-runs").status_code, 404)
            self.assertIn(client.post("/api/v2/runs", json={}).status_code, {405, 422})

        for path in [
            "/api/v2/workflows/validate",
            "/api/v2/live-runs",
            "/api/v2/live-runs/{run_id}",
            "/api/v2/live-runs/{run_id}/events",
            "/api/v2/agent-workflows/compile",
            "/api/v2/library/workflows",
        ]:
            with self.subTest(path=path):
                self.assertNotIn(path, route_paths)


def _source_files(relative_root: str) -> list[Path]:
    base = ROOT if relative_root.startswith("frontend/") else LEGACY_ROOT
    root = base / relative_root
    return [
        path
        for path in root.rglob("*")
        if path.suffix in {".py", ".ts", ".tsx"} and "__pycache__" not in path.parts
    ]


if __name__ == "__main__":
    unittest.main()
