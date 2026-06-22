from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
WORKBENCH_SURFACES = [
    FRONTEND / "App.tsx",
    FRONTEND / "workflowGraph.ts",
    FRONTEND / "runEvents.tsx",
    FRONTEND / "features" / "agent-workflow" / "AgentWorkflowAgentInspector.tsx",
]


class WorkbenchUiSimplifiedModelTests(unittest.TestCase):
    def test_default_frontend_workflow_uses_product_role_names(self) -> None:
        source = (FRONTEND / "examples.ts").read_text(encoding="utf-8")

        self.assertIn('name: "Planner"', source)
        self.assertIn('name: "Executor"', source)
        self.assertIn('name: "Tester"', source)
        self.assertIn('role_card: "executor"', source)
        self.assertIn('role_card: "tester"', source)
        self.assertNotIn("Planner Agent", source)
        self.assertNotIn("Executor Agent", source)
        self.assertNotIn("Tester Agent", source)

    def test_canvas_role_labels_are_only_planner_executor_tester(self) -> None:
        source = (FRONTEND / "workflowGraph.ts").read_text(encoding="utf-8")

        self.assertIn('planner: "Planner"', source)
        self.assertIn('executor: "Executor"', source)
        self.assertIn('tester: "Tester"', source)
        self.assertNotIn("can ask user", source)

    def test_agent_inspector_does_not_expose_runtime_internals(self) -> None:
        source = (FRONTEND / "features" / "agent-workflow" / "AgentWorkflowAgentInspector.tsx").read_text(encoding="utf-8")

        self.assertNotIn("CapabilitySpec", source)
        self.assertNotIn("capabilities: CapabilitySpec", source)
        self.assertNotIn('type="checkbox"', source)
        self.assertNotIn("Runtime Role", source)
        self.assertNotIn("Custom", source)

    def test_planner_delete_is_disabled_in_workbench(self) -> None:
        source = (FRONTEND / "App.tsx").read_text(encoding="utf-8")

        self.assertRegex(source, re.compile(r"selectedAgentWorkflowAgent\?\.id === agentWorkflow\.primary_planner_id"))
        self.assertNotIn("Runtime profiles are compiled internally", source)
        self.assertNotIn("capabilities={", source)

    def test_removed_words_are_absent_from_user_visible_workbench_surfaces(self) -> None:
        forbidden = [
            "Worker",
            "Do work",
            "Custom",
            "Engine",
            "Harness",
            "Runtime Role",
            "raw capabilities",
            "legacy runtime preview",
        ]
        offenders: list[str] = []
        for path in WORKBENCH_SURFACES:
            source = path.read_text(encoding="utf-8")
            for word in forbidden:
                if word in source:
                    offenders.append(f"{path.relative_to(ROOT)} contains {word!r}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
