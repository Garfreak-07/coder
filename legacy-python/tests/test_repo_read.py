from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.context.repo_read import RepoReadService


class RepoReadServiceTests(unittest.TestCase):
    def test_reads_requested_range(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")

            snippet = RepoReadService(repo_root=root).read_file_range("src/app.py", start_line=2, max_lines=1)

            self.assertEqual(snippet.path, "src/app.py")
            self.assertEqual(snippet.start_line, 2)
            self.assertEqual(snippet.end_line, 2)
            self.assertEqual(snippet.text, "two\n")

    def test_max_lines_is_enforced(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")

            snippet = RepoReadService(repo_root=root).read_file_range("src/app.py", max_lines=2)

            self.assertEqual(snippet.end_line, 2)
            self.assertTrue(snippet.truncated)

    def test_max_chars_truncates(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("abcdef\n", encoding="utf-8")

            snippet = RepoReadService(repo_root=root).read_file_range("src/app.py", max_chars=3)

            self.assertEqual(snippet.text, "abc")
            self.assertTrue(snippet.truncated)

    def test_path_traversal_rejected(self) -> None:
        with _repo() as root:
            service = RepoReadService(repo_root=root)

            with self.assertRaises(ValueError):
                service.read_file_range("../outside.txt")

    def test_outside_scope_rejected(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("app\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                RepoReadService(repo_root=root, scope_paths=["docs"]).read_file_range("src/app.py")

    def test_env_file_rejected(self) -> None:
        with _repo() as root:
            (root / ".env").write_text("SECRET=value\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                RepoReadService(repo_root=root).read_file_range(".env")

    def test_binary_file_rejected(self) -> None:
        with _repo() as root:
            (root / "src" / "bin.dat").write_bytes(b"abc\0def")

            with self.assertRaises(ValueError):
                RepoReadService(repo_root=root).read_file_range("src/bin.dat")


class _repo:
    def __enter__(self) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        (root / "docs").mkdir()
        return root

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
