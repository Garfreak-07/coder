from __future__ import annotations

import tempfile
import unittest

from coder_workbench.runtime import RunEvent
from coder_workbench.server.stores import PartitionedRunStores


class PartitionedStoreTests(unittest.TestCase):
    def test_partitioned_store_facade_reads_and_writes_run_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stores = PartitionedRunStores(tmp)
            event = RunEvent(type="run.started", message="started")

            stores.metadata.write("run-1", {"id": "run-1", "status": "completed"})
            stores.results.write("run-1", {"status": "completed", "events": []})
            stores.events.append("run-1", event)
            stores.artifacts.write("run-1", "artifact_1", {"artifact_type": "sample", "value": 1})
            stores.ledgers.write("run-1", "ledger_1", {"kind": "token", "tokens": 12})
            stores.contexts.write("run-1", "packet_1", {"task": "inspect"})
            stores.tool_results.write("run-1", "tool_1", {"output": "ok"})
            stores.live_runs.write("live-1", {"id": "live-1", "runtime_type": "agent_graph"})
            blob_id = stores.blobs.write_text("large output")

            self.assertEqual(stores.metadata.read("run-1")["status"], "completed")
            self.assertEqual(stores.results.read("run-1")["status"], "completed")
            self.assertEqual(stores.events.read("run-1")[0].type, "run.started")
            self.assertEqual(stores.artifacts.read("run-1", "artifact_1")["value"], 1)
            self.assertEqual(stores.ledgers.read("run-1", "ledger_1")["tokens"], 12)
            self.assertEqual(stores.ledgers.list("run-1")[0]["kind"], "token")
            self.assertEqual(stores.contexts.read("run-1", "packet_1")["task"], "inspect")
            self.assertEqual(stores.tool_results.read("run-1", "tool_1")["output"], "ok")
            self.assertEqual(stores.live_runs.list()[0]["id"], "live-1")
            self.assertEqual(stores.blobs.read_text(blob_id), "large output")
            self.assertTrue(stores.extensions.plugins_dir.exists())
            self.assertTrue(stores.extensions.skills_dir.exists())
            self.assertTrue(stores.cache.namespace("repo-index").exists())


if __name__ == "__main__":
    unittest.main()
