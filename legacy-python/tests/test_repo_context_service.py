from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.context.repo_context_service import NativeRepoContextService


class NativeRepoContextServiceTests(unittest.TestCase):
    def test_find_files_writes_evidence_ref(self) -> None:
        with _repo() as data:
            root, coder_root = data
            (root / "src" / "app.py").write_text("app\n", encoding="utf-8")
            service = NativeRepoContextService(coder_store_root=coder_root, repo_root=root, run_id="run-1")

            files, ref = service.find_files(query="app", max_results=10)

            self.assertEqual([item.path for item in files], ["src/app.py"])
            payload = service.read_evidence(ref.ref_id)
            self.assertEqual(payload["files"][0]["path"], "src/app.py")
            self.assertEqual(payload["evidence_kind"], "repo_evidence")

    def test_search_text_writes_evidence_ref(self) -> None:
        with _repo() as data:
            root, coder_root = data
            (root / "src" / "app.py").write_text("def target_function():\n    pass\n", encoding="utf-8")
            service = NativeRepoContextService(coder_store_root=coder_root, repo_root=root, run_id="run-1")

            hits, ref = service.search_text("target_function")

            self.assertEqual(hits[0].path, "src/app.py")
            payload = service.read_evidence(ref.ref_id)
            self.assertEqual(payload["hits"][0]["line"], 1)

    def test_read_file_range_writes_evidence_ref(self) -> None:
        with _repo() as data:
            root, coder_root = data
            (root / "src" / "app.py").write_text("one\ntwo\n", encoding="utf-8")
            service = NativeRepoContextService(coder_store_root=coder_root, repo_root=root, run_id="run-1")

            snippet, ref = service.read_file_range("src/app.py", start_line=2, max_lines=1)

            self.assertEqual(snippet.text, "two\n")
            payload = service.read_evidence(ref.ref_id)
            self.assertEqual(payload["snippet"]["start_line"], 2)

    def test_scope_is_enforced_across_operations(self) -> None:
        with _repo() as data:
            root, coder_root = data
            (root / "src" / "app.py").write_text("needle\n", encoding="utf-8")
            (root / "docs" / "note.md").write_text("needle\n", encoding="utf-8")
            service = NativeRepoContextService(
                coder_store_root=coder_root,
                repo_root=root,
                run_id="run-1",
                scope_paths=["docs"],
            )

            files, _file_ref = service.find_files(max_results=10)
            hits, _search_ref = service.search_text("needle")

            self.assertEqual([item.path for item in files], ["docs/note.md"])
            self.assertEqual([hit.path for hit in hits], ["docs/note.md"])
            with self.assertRaises(ValueError):
                service.read_file_range("src/app.py")

    def test_read_payload_is_bounded(self) -> None:
        with _repo() as data:
            root, coder_root = data
            (root / "src" / "large.py").write_text("x" * 20_000, encoding="utf-8")
            service = NativeRepoContextService(coder_store_root=coder_root, repo_root=root, run_id="run-1")

            snippet, ref = service.read_file_range("src/large.py", max_chars=100)

            self.assertEqual(len(snippet.text), 100)
            payload = service.read_evidence(ref.ref_id)
            self.assertLessEqual(len(payload["snippet"]["text"]), 100)


class _repo:
    def __enter__(self) -> tuple[Path, Path]:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        (root / "docs").mkdir()
        coder_root = root / ".coder"
        coder_root.mkdir()
        return root, coder_root

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
