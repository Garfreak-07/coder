from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from coder_workbench.openhands_tools.repo_context import (
    CoderRepoFindFilesAction,
    CoderRepoFindFilesTool,
    CoderRepoReadFileAction,
    CoderRepoReadFileTool,
    CoderRepoSearchTextAction,
    CoderRepoSearchTextTool,
)
from openhands.sdk.tool import list_registered_tools


class OpenHandsRepoContextToolsTests(unittest.TestCase):
    def test_tools_register(self) -> None:
        names = set(list_registered_tools())

        self.assertIn(CoderRepoFindFilesTool.name, names)
        self.assertIn(CoderRepoSearchTextTool.name, names)
        self.assertIn(CoderRepoReadFileTool.name, names)

    def test_action_schemas_exclude_bound_runtime_params(self) -> None:
        for action_type in (CoderRepoFindFilesAction, CoderRepoSearchTextAction, CoderRepoReadFileAction):
            with self.subTest(action_type=action_type.__name__):
                schema = action_type.model_json_schema()
                self.assertNotIn("repo_root", schema["properties"])
                self.assertNotIn("coder_store_root", schema["properties"])
                self.assertNotIn("run_id", schema["properties"])
                self.assertNotIn("scope_paths", schema["properties"])
                with self.assertRaises(ValidationError):
                    action_type.model_validate({"repo_root": ".", "run_id": "claimed"})

    def test_find_files_returns_evidence_ref(self) -> None:
        with _repo() as data:
            root, params = data
            (root / "src" / "app.py").write_text("app\n", encoding="utf-8")
            tool = CoderRepoFindFilesTool.create(conv_state=None, **params)[0]

            observation = tool(CoderRepoFindFilesAction(query="app"))

            self.assertEqual(observation.returned, 1)
            self.assertEqual(observation.files[0]["path"], "src/app.py")
            self.assertTrue(observation.evidence_ref.startswith("repo-file-list:"))

    def test_search_text_respects_scope(self) -> None:
        with _repo() as data:
            root, params = data
            (root / "src" / "app.py").write_text("needle\n", encoding="utf-8")
            (root / "docs" / "note.md").write_text("needle\n", encoding="utf-8")
            params["scope_paths"] = ["docs"]
            tool = CoderRepoSearchTextTool.create(conv_state=None, **params)[0]

            observation = tool(CoderRepoSearchTextAction(pattern="needle"))

            self.assertEqual([hit["path"] for hit in observation.hits], ["docs/note.md"])
            self.assertTrue(observation.evidence_ref.startswith("repo-text-search:"))

    def test_read_file_returns_line_refs_and_evidence_ref(self) -> None:
        with _repo() as data:
            root, params = data
            (root / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            tool = CoderRepoReadFileTool.create(conv_state=None, **params)[0]

            observation = tool(CoderRepoReadFileAction(path="src/app.py", start_line=2, max_lines=1))

            self.assertEqual(observation.snippet["path"], "src/app.py")
            self.assertEqual(observation.snippet["start_line"], 2)
            self.assertTrue(observation.evidence_ref.startswith("repo-read:"))

    def test_read_file_rejects_path_traversal_and_env(self) -> None:
        with _repo() as data:
            root, params = data
            (root / ".env").write_text("SECRET=value\n", encoding="utf-8")
            tool = CoderRepoReadFileTool.create(conv_state=None, **params)[0]

            with self.assertRaises(ValueError):
                tool(CoderRepoReadFileAction(path="../outside.txt"))
            with self.assertRaises(ValueError):
                tool(CoderRepoReadFileAction(path=".env"))

    def test_annotations_mark_tools_read_only(self) -> None:
        with _repo() as data:
            _root, params = data
            for tool_type in (CoderRepoFindFilesTool, CoderRepoSearchTextTool, CoderRepoReadFileTool):
                with self.subTest(tool_type=tool_type.__name__):
                    tool = tool_type.create(conv_state=None, **params)[0]
                    self.assertTrue(tool.annotations.readOnlyHint)
                    self.assertFalse(tool.annotations.destructiveHint)
                    self.assertTrue(tool.annotations.idempotentHint)
                    self.assertFalse(tool.annotations.openWorldHint)


class _repo:
    def __enter__(self) -> tuple[Path, dict[str, object]]:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        (root / "docs").mkdir()
        coder_root = root / ".coder"
        coder_root.mkdir()
        return root, {
            "coder_store_root": str(coder_root),
            "repo_root": str(root),
            "run_id": "run-1",
            "scope_paths": [],
        }

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
