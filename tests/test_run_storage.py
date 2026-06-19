from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.runtime import RunEvent, RunResult
from coder_workbench.server.storage import RunStore, StoredRun


class RunStoreTests(unittest.TestCase):
    def test_split_run_layout_reconstructs_events_and_lists_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".coder"
            store = RunStore(root)
            result = _result()

            stored = store.save("workflow-1", "/repo", "do work", result)

            run_dir = root / "runs" / stored.id
            self.assertTrue((run_dir / "metadata.json").exists())
            self.assertTrue((run_dir / "result.json").exists())
            self.assertTrue((run_dir / "events.jsonl").exists())
            self.assertFalse((root / "runs" / f"{stored.id}.json").exists())

            loaded = store.get(stored.id)
            self.assertEqual(loaded.result.status, "completed")
            self.assertEqual([event.type for event in loaded.result.events], ["run.started", "node.started", "run.completed"])

            without_events = store.get(stored.id, include_events=False)
            self.assertEqual(without_events.result.events, [])

            event_page = store.get_events(stored.id, cursor=1, limit=1)
            self.assertEqual(event_page["cursor"], 1)
            self.assertEqual(event_page["next_cursor"], 2)
            self.assertTrue(event_page["has_more"])
            self.assertEqual(event_page["events"][0]["type"], "node.started")

            (run_dir / "result.json").write_text("not valid json", encoding="utf-8")
            listed = store.list()
            self.assertEqual(listed[0]["id"], stored.id)
            self.assertEqual(listed[0]["events"], 3)

    def test_legacy_single_file_runs_still_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".coder"
            store = RunStore(root)
            legacy = StoredRun(
                id="legacy-run",
                workflow_id="workflow-legacy",
                repo_root="/repo",
                request="legacy work",
                result=_result(),
            )
            (root / "runs" / "legacy-run.json").write_text(legacy.model_dump_json(indent=2), encoding="utf-8")

            loaded = store.get("legacy-run")
            self.assertEqual(loaded.workflow_id, "workflow-legacy")
            self.assertEqual(len(loaded.result.events), 3)

            without_events = store.get("legacy-run", include_events=False)
            self.assertEqual(without_events.result.events, [])

            event_page = store.get_events("legacy-run", cursor=0, limit=2)
            self.assertEqual([event["type"] for event in event_page["events"]], ["run.started", "node.started"])
            self.assertTrue(event_page["has_more"])

            listed = store.list()
            self.assertEqual(listed[0]["id"], "legacy-run")
            self.assertEqual(listed[0]["events"], 3)


def _result() -> RunResult:
    return RunResult(
        status="completed",
        data={"answer": "done"},
        summaries={"answer": "done"},
        events=[
            RunEvent(type="run.started", message="started"),
            RunEvent(type="node.started", node_id="start", message="start"),
            RunEvent(type="run.completed", message="completed"),
        ],
        estimated_tokens_used=12,
        agent_calls=1,
        tool_calls=2,
    )


if __name__ == "__main__":
    unittest.main()
