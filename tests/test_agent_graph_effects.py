from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.core import default_planner_led_agent_workflow
from coder_workbench.server.storage import RunStore


class AgentGraphEffectsTests(unittest.TestCase):
    def test_unapproved_optional_check_command_requires_planner_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            marker = repo / "created.txt"
            command = f'"{sys.executable}" -c "from pathlib import Path; Path(\'created.txt\').write_text(\'bad\')"'

            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Run hidden effect.",
                str(repo),
                initial_data={"requested_check_commands": [{"work_item_id": "executor-work", "command": command}]},
            )
            marker_exists = marker.exists()

        self.assertEqual(result.status, "completed")
        self.assertFalse(marker_exists)
        effect = result.data["planner_input_bundle"]["effects"][0]
        self.assertEqual(effect["effect_type"], "optional_check_command")
        self.assertEqual(effect["status"], "check_requires_planner_confirmation")
        self.assertIn("approval_key", effect)

    def test_preapproved_optional_check_command_records_output_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            command = f'"{sys.executable}" -c "print(42)"'

            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Run hidden effect.",
                str(repo),
                initial_data={
                    "preapprove_all": True,
                    "requested_check_commands": [{"work_item_id": "executor-work", "command": command}],
                },
            )

        effect = result.data["planner_input_bundle"]["effects"][0]
        self.assertEqual(effect["status"], "completed")
        self.assertEqual(effect["output_ref"], "check_output_1")
        output = result.data["graph_run_cache"]["hidden_effect_outputs"]["check_output_1"]
        self.assertIn("42", output["output"])
        tool_event = next(event for event in result.events if event.type == "tool.result")
        self.assertEqual(tool_event.payload["tool_result_id"], "check_output_1")

        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp) / ".coder")
            stored = store.save("agent-graph", tmp, "Run hidden effect.", result)
            loaded = store.get_tool_result(stored.id, "check_output_1")

        self.assertIn("42", loaded["output"])

    def test_modify_files_effect_creates_patch_preview_without_applying(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            src = repo / "src"
            src.mkdir()
            target = src / "example.txt"
            target.write_text("before\n", encoding="utf-8")

            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Preview file changes.",
                str(repo),
                initial_data={
                    "scopes": ["src"],
                    "proposed_changes": [
                        {
                            "path": "src/example.txt",
                            "action": "update",
                            "expected_before": "before\n",
                            "content": "after\n",
                        }
                    ],
                },
            )
            current_content = target.read_text(encoding="utf-8")

        self.assertEqual(current_content, "before\n")
        effect = result.data["planner_input_bundle"]["effects"][0]
        self.assertEqual(effect["effect_type"], "modify_files")
        self.assertEqual(effect["status"], "patch_preview_created")
        patch_ref = effect["patch_ref"]
        self.assertTrue(patch_ref.startswith("patch_preview_"))
        preview = result.data["graph_run_cache"]["hidden_effect_outputs"][patch_ref]
        self.assertEqual(preview["status"], "proposed")
        self.assertTrue(preview["requires_approval"])
        self.assertIn("-before", preview["files"][0]["diff"])
        self.assertIn("+after", preview["files"][0]["diff"])


if __name__ == "__main__":
    unittest.main()
