from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.runtime_capabilities import (
    ToolRegistry,
    progressive_skill_registry,
    validate_mcp_manifest,
)
from coder_workbench.skills import InstalledSkillStore, SkillPackageManifest


class RuntimeRegistryGroundworkTests(unittest.TestCase):
    def test_tool_registry_filters_by_harness_and_marks_risky_tools(self) -> None:
        registry = ToolRegistry()
        code_worker_tools = registry.list_tools(harness_id="code-worker-harness")
        names = {entry.capability.name for entry in code_worker_tools}
        patch_tool = registry.get_tool("apply_patch_sandbox")

        self.assertIn("run_command_sandbox", names)
        self.assertNotIn("inspect_run_state", names)
        self.assertTrue(patch_tool.requires_approval)

    def test_mcp_manifest_validation_never_enables_by_default(self) -> None:
        validation = validate_mcp_manifest(
            {
                "server_id": "github",
                "name": "GitHub",
                "enabled_by_default": True,
                "operations": [
                    {"name": "search_issues", "risk": "low", "side_effect": "read", "enabled_by_default": True}
                ],
            }
        )

        self.assertTrue(validation.ok)
        self.assertFalse(validation.manifest.enabled_by_default)  # type: ignore[union-attr]
        self.assertFalse(validation.manifest.operations[0].enabled_by_default)  # type: ignore[union-attr]
        self.assertGreaterEqual(len(validation.warnings), 2)

    def test_progressive_skill_registry_loads_summary_full_and_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "package"
            (package / "references").mkdir(parents=True)
            (package / "SKILL.md").write_text("# Test Skill\nUse it carefully.\n", encoding="utf-8")
            (package / "references" / "guide.md").write_text("Reference body.\n", encoding="utf-8")
            store = InstalledSkillStore(root / "store")
            store.install_from_directory(
                package,
                manifest=SkillPackageManifest(
                    id="test-skill",
                    name="Test Skill",
                    version="1.0.0",
                    description="A test skill.",
                    category="testing",
                    skill_type="knowledge",
                    risk_level="low",
                    publisher="tests",
                    allowed_authorities=["planner"],
                    trigger_hints=["test"],
                ),
                package_sha256="0" * 64,
                trust_level="local",
                source="local",
            )
            registry = progressive_skill_registry(root / "store")

            summaries = registry.list_skill_summaries()
            full = registry.load_skill_full("test-skill")
            reference = registry.load_skill_reference("test-skill", "guide.md")

            self.assertEqual(summaries[0]["id"], "test-skill")
            self.assertIn("# Test Skill", full["body"])
            self.assertEqual(reference["reference_path"], "references/guide.md")
            self.assertIn("Reference body", reference["content"])
            with self.assertRaises(KeyError):
                registry.load_skill_reference("test-skill", "../SKILL.md")


if __name__ == "__main__":
    unittest.main()
