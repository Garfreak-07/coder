from __future__ import annotations

import tempfile
import unittest

from coder_workbench.core import WorkflowSpec
from coder_workbench.runtime import run_workflow


class LoopAndContextPacketTests(unittest.TestCase):
    def test_loop_node_stops_at_max_iterations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow = WorkflowSpec.model_validate(
                {
                    "id": "loop-test",
                    "name": "Loop test",
                    "max_steps": 10,
                    "nodes": [
                        {"id": "start", "type": "start"},
                        {
                            "id": "retry",
                            "type": "loop",
                            "loop_mode": "retry_until",
                            "condition": "review.status == 'done'",
                            "max_iterations": 2,
                            "output_key": "retry_state",
                        },
                        {"id": "end", "type": "end"},
                    ],
                    "edges": [
                        {"from": "start", "to": "retry"},
                        {"from": "retry", "to": "retry", "when": "retry_state.should_continue == True", "max_traversals": 3},
                        {"from": "retry", "to": "end", "when": "retry_state.should_continue == False"},
                    ],
                }
            )

            result = run_workflow(
                workflow,
                "retry until done",
                tmp,
                initial_data={"review": {"status": "needs_changes"}},
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.data["retry_state"]["iteration"], 2)
            self.assertFalse(result.data["retry_state"]["should_continue"])
            self.assertEqual(result.data["retry_state"]["break_reason"], "max_iterations")
            self.assertTrue(any(event.type == "loop.iteration.started" for event in result.events))
            self.assertTrue(any(event.type == "loop.completed" for event in result.events))

    def test_agent_context_packet_includes_loop_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow = WorkflowSpec.model_validate(
                {
                    "id": "context-packet-test",
                    "name": "Context packet test",
                    "nodes": [
                        {"id": "start", "type": "start"},
                        {
                            "id": "retry",
                            "type": "loop",
                            "loop_mode": "retry_until",
                            "condition": "review.status == 'done'",
                            "max_iterations": 2,
                            "output_key": "retry_state",
                        },
                        {"id": "agent", "type": "agent", "agent_id": "worker", "output_key": "worker_result"},
                        {"id": "end", "type": "end"},
                    ],
                    "edges": [
                        {"from": "start", "to": "retry"},
                        {"from": "retry", "to": "agent", "when": "retry_state.should_continue == True"},
                        {"from": "agent", "to": "end"},
                    ],
                    "agents": [
                        {
                            "id": "worker",
                            "role": "Worker",
                            "goal": "Use compact context.",
                            "context": {"input_keys": ["retry_state"], "summary_keys": []},
                        }
                    ],
                }
            )

            result = run_workflow(
                workflow,
                "inspect context",
                tmp,
                initial_data={"review": {"status": "needs_changes"}, "scopes": ["src"]},
            )

            self.assertEqual(result.status, "completed")
            event_types = [event.type for event in result.events]
            packet_index = event_types.index("agent.context_packet")
            called_index = event_types.index("agent.called")
            self.assertLess(packet_index, called_index)
            packet = result.events[packet_index].payload["packet"]
            self.assertEqual(packet["agent"]["id"], "worker")
            self.assertEqual(packet["loop"]["node_id"], "retry")
            self.assertEqual(packet["loop"]["iteration"], 1)
            self.assertEqual(packet["project_context"]["scopes"], ["src"])
            self.assertIn("retry_state", packet["selected_state_keys"])


if __name__ == "__main__":
    unittest.main()
