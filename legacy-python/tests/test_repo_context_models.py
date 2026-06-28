from __future__ import annotations

import unittest

from pydantic import ValidationError

from coder_workbench.context.repo_models import RepoReadSnippet, RepoSearchHit


class RepoContextModelsTests(unittest.TestCase):
    def test_repo_search_hit_validates_line_numbers(self) -> None:
        hit = RepoSearchHit(path="src/app.py", line=3, column=2, text="def target():", match="target")

        self.assertEqual(hit.line, 3)
        with self.assertRaises(ValidationError):
            RepoSearchHit(path="src/app.py", line=0, text="bad")

    def test_repo_read_snippet_validates_line_range(self) -> None:
        snippet = RepoReadSnippet(path="src/app.py", start_line=1, end_line=2, text="a\nb\n")

        self.assertEqual(snippet.end_line, 2)
        with self.assertRaises(ValidationError):
            RepoReadSnippet(path="src/app.py", start_line=5, end_line=4, text="")


if __name__ == "__main__":
    unittest.main()
