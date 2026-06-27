from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.context.repo_search import RepoTextSearchService


class RepoTextSearchServiceTests(unittest.TestCase):
    def test_exact_string_search_finds_hit(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("def target_function():\n    return 1\n", encoding="utf-8")

            hits = _FallbackSearch(repo_root=root).search_text("target_function")

            self.assertEqual(hits[0].path, "src/app.py")
            self.assertEqual(hits[0].line, 1)

    def test_regex_search_finds_hit(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("class PlannerTaskState:\n    pass\n", encoding="utf-8")

            hits = _FallbackSearch(repo_root=root).search_text(r"Planner\w+", regex=True)

            self.assertEqual(hits[0].match, "PlannerTaskState")

    def test_case_insensitive_search_works(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("DeepSeekProvider\n", encoding="utf-8")

            hits = _FallbackSearch(repo_root=root).search_text("deepseekprovider")

            self.assertEqual(len(hits), 1)

    def test_scope_paths_are_respected(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("needle\n", encoding="utf-8")
            (root / "docs" / "note.md").write_text("needle\n", encoding="utf-8")

            hits = _FallbackSearch(repo_root=root, scope_paths=["docs"]).search_text("needle")

            self.assertEqual([hit.path for hit in hits], ["docs/note.md"])

    def test_max_results_is_enforced(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("\n".join("needle" for _ in range(5)), encoding="utf-8")

            hits = _FallbackSearch(repo_root=root).search_text("needle", max_results=2)

            self.assertEqual(len(hits), 2)

    def test_sensitive_dirs_and_files_are_skipped(self) -> None:
        with _repo() as root:
            (root / ".env").write_text("needle\n", encoding="utf-8")
            (root / ".coder" / "state.txt").write_text("needle\n", encoding="utf-8")
            (root / "src" / "app.py").write_text("needle\n", encoding="utf-8")

            hits = _FallbackSearch(repo_root=root).search_text("needle")

            self.assertEqual([hit.path for hit in hits], ["src/app.py"])

    def test_binary_file_is_skipped(self) -> None:
        with _repo() as root:
            (root / "src" / "bin.dat").write_bytes(b"needle\0more")
            (root / "src" / "app.py").write_text("needle\n", encoding="utf-8")

            hits = _FallbackSearch(repo_root=root).search_text("needle")

            self.assertEqual([hit.path for hit in hits], ["src/app.py"])

    def test_include_globs_filter_results(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("needle\n", encoding="utf-8")
            (root / "docs" / "note.md").write_text("needle\n", encoding="utf-8")

            hits = _FallbackSearch(repo_root=root).search_text("needle", include_globs=["*.md"])

            self.assertEqual([hit.path for hit in hits], ["docs/note.md"])


class _FallbackSearch(RepoTextSearchService):
    def _command_available(self, command: str) -> bool:
        return False


class _repo:
    def __enter__(self) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        (root / "docs").mkdir()
        (root / ".coder").mkdir()
        return root

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
