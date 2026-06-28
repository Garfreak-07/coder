from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.tools.registry import default_tool_registry


class ProjectSummaryTests(unittest.TestCase):
    def test_project_index_reports_summary_and_candidate_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
            (repo / "tests").mkdir()
            (repo / "tests" / "test_app.py").write_text("def test_app():\n    assert True\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
            (repo / "frontend").mkdir()
            (repo / "frontend" / "package.json").write_text(
                '{"scripts":{"build":"vite build"}}',
                encoding="utf-8",
            )
            (repo / "frontend" / "vite.config.ts").write_text("export default {}\n", encoding="utf-8")

            result = default_tool_registry().run(
                "project_index",
                {"max_files": 20},
                {"repo_root": str(repo), "scopes": [], "data": {}, "request": "test"},
            )

            self.assertIn("summary", result)
            self.assertIn("python", result["detected_frameworks"])
            self.assertIn("vite", result["detected_frameworks"])
            self.assertIn("pyproject.toml", result["important_files"])
            self.assertIn("frontend/package.json", result["important_files"])
            self.assertIn("python -m unittest discover -s tests", result["candidate_check_commands"])
            self.assertIn("npm --prefix frontend run build", result["candidate_check_commands"])


if __name__ == "__main__":
    unittest.main()
