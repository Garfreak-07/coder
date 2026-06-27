from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.context.repo_evidence import RepoEvidenceStore


class RepoEvidenceStoreTests(unittest.TestCase):
    def test_writes_and_reads_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".coder"
            store = RepoEvidenceStore(root)

            ref = store.write_evidence(
                run_id="run-1",
                kind="repo_text_search",
                repo_root=tmp,
                scope_paths=["src"],
                summary="Found one hit.",
                payload={"hits": [{"path": "src/app.py", "line": 1, "text": "target"}]},
            )

            payload = store.read_evidence(ref.ref_id)
            self.assertEqual(payload["hits"][0]["path"], "src/app.py")
            self.assertEqual(ref.kind, "repo_text_search")
            self.assertTrue(Path(ref.payload_path or "").is_relative_to(root / "runs" / "run-1" / "repo_evidence"))

    def test_rejects_path_traversal_in_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RepoEvidenceStore(Path(tmp) / ".coder")

            with self.assertRaises(ValueError):
                store.write_evidence(
                    run_id="../escape",
                    kind="repo_read",
                    repo_root=tmp,
                    scope_paths=[],
                    summary="bad",
                    payload={"text": "safe"},
                )

    def test_rejects_path_traversal_in_ref_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RepoEvidenceStore(Path(tmp) / ".coder")

            with self.assertRaises(ValueError):
                store.read_evidence("../escape")

    def test_large_payload_is_compacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RepoEvidenceStore(Path(tmp) / ".coder")
            ref = store.write_evidence(
                run_id="run-1",
                kind="repo_read",
                repo_root=tmp,
                scope_paths=[],
                summary="large",
                payload={"snippet": "x" * 20_000},
            )

            payload = store.read_evidence(ref.ref_id)
            self.assertLess(len(payload["snippet"]), 20_000)
            self.assertTrue(payload["snippet"].endswith("..."))

    def test_secret_like_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RepoEvidenceStore(Path(tmp) / ".coder")

            with self.assertRaises(ValueError):
                store.write_evidence(
                    run_id="run-1",
                    kind="repo_read",
                    repo_root=tmp,
                    scope_paths=[],
                    summary="secret",
                    payload={"snippet": "api_key=abc"},
                )


if __name__ == "__main__":
    unittest.main()
