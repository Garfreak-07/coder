from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from coder_workbench.server.app import create_app
from coder_workbench.skills import (
    InstalledSkillStore,
    RegistryClient,
    SkillInstaller,
    SkillVerificationError,
    build_skill_index,
    select_skills_for_work_item,
    sha256_digest,
    verify_sha256,
)
from coder_workbench.skills.schema import SkillPackageManifest


class SkillStoreSchemaTests(unittest.TestCase):
    def test_valid_manifest_accepts_skillpack_fields(self) -> None:
        manifest = SkillPackageManifest.model_validate(_manifest())

        self.assertEqual(manifest.id, "github-research")
        self.assertEqual(manifest.skill_type, "procedure")
        self.assertEqual(manifest.context_policy.max_skill_tokens, 1200)

    def test_invalid_manifest_rejects_unknown_type_and_external_effect_without_approval(self) -> None:
        invalid_type = _manifest(skill_type="automation")
        with self.assertRaises(Exception):
            SkillPackageManifest.model_validate(invalid_type)

        unsafe_effect = _manifest(
            id="publishing-skill",
            external_effect=True,
            requires_preview=False,
            requires_human_approval=False,
        )
        with self.assertRaises(Exception):
            SkillPackageManifest.model_validate(unsafe_effect)

    def test_checksum_verifier_rejects_mismatch(self) -> None:
        with self.assertRaises(SkillVerificationError):
            verify_sha256(b"package", "0" * 64)


class SkillInstallerTests(unittest.TestCase):
    def test_installer_verifies_package_and_persists_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_path, digest = _write_skill_package(root)
            registry_path = _write_registry(root, package_path, digest)

            store = InstalledSkillStore(root / ".coder")
            result = SkillInstaller(client=RegistryClient(str(registry_path)), store=store).install("github-research")

            self.assertEqual(result.record.manifest.id, "github-research")
            self.assertEqual(result.record.trust_level, "official")
            self.assertEqual(result.verification.sha256, digest)
            self.assertTrue((root / ".coder" / "skills" / "github-research" / "SKILL.md").exists())

            loaded = store.get_skill("github-research")
            self.assertTrue(loaded.enabled)
            self.assertEqual(loaded.package_sha256, digest)

    def test_installer_rejects_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_path, _digest = _write_skill_package(root)
            registry_path = _write_registry(root, package_path, "1" * 64)

            store = InstalledSkillStore(root / ".coder")
            with self.assertRaises(SkillVerificationError):
                SkillInstaller(client=RegistryClient(str(registry_path)), store=store).install("github-research")

    def test_skill_router_selects_matching_installed_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_path, digest = _write_skill_package(root)
            registry_path = _write_registry(root, package_path, digest)
            store = InstalledSkillStore(root / ".coder")
            SkillInstaller(client=RegistryClient(str(registry_path)), store=store).install("github-research")
            skill_index = build_skill_index(store.list_installed())

            decision = select_skills_for_work_item(
                skill_index=skill_index,
                user_request="Research GitHub repositories for similar projects.",
                work_item={"work_item_id": "research", "task_summary": "Search GitHub sources"},
                role="researcher",
            )

            self.assertEqual(decision.allowed_skill_ids, ["github-research"])
            self.assertEqual(decision.loaded_skill_refs, ["skill:github-research:SKILL.md"])


class SkillApiTests(unittest.TestCase):
    def test_skill_api_discovers_installs_and_disables_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_path, digest = _write_skill_package(root)
            registry_path = _write_registry(root, package_path, digest)
            client = TestClient(create_app(store_root=root / ".coder", frontend_dist=root))

            discover = client.get("/api/v2/skills/discover", params={"registry_url": str(registry_path)})
            self.assertEqual(discover.status_code, 200)
            self.assertEqual(discover.json()["skills"][0]["id"], "github-research")
            self.assertFalse(discover.json()["skills"][0]["installed"])

            install = client.post(
                "/api/v2/skills/install",
                json={"skill_id": "github-research", "registry_url": str(registry_path)},
            )
            self.assertEqual(install.status_code, 200)
            self.assertEqual(install.json()["record"]["manifest"]["id"], "github-research")

            installed = client.get("/api/v2/skills/installed")
            self.assertEqual(installed.status_code, 200)
            self.assertEqual(installed.json()["skills"][0]["id"], "github-research")
            self.assertEqual(installed.json()["index"]["skills"][0]["id"], "github-research")

            disabled = client.post("/api/v2/skills/github-research/disable")
            self.assertEqual(disabled.status_code, 200)
            self.assertFalse(disabled.json()["skill"]["enabled"])


def _manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "id": "github-research",
        "name": "GitHub Research",
        "version": "0.1.0",
        "description": "Search and compare open-source GitHub repositories.",
        "category": "research",
        "skill_type": "procedure",
        "risk_level": "low",
        "publisher": "coder-official",
        "allowed_authorities": ["planner", "worker", "tester", "synthesizer"],
        "requires": ["search_query"],
        "produces": ["source_collection", "synthesis_artifact", "execution_result"],
        "connectors": ["github_readonly"],
        "external_effect": False,
        "requires_preview": False,
        "requires_human_approval": False,
        "context_policy": {
            "load_mode": "on_demand",
            "max_skill_tokens": 1200,
        },
        "compatibility": {
            "coder_min_version": "0.7.0",
            "agent_graph_runtime": True,
        },
        "trigger_hints": ["github", "repository", "open source research"],
    }
    manifest.update(overrides)
    return manifest


def _write_skill_package(root: Path, *, manifest: dict[str, object] | None = None) -> tuple[Path, str]:
    package_path = root / "github-research.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("skill.json", json.dumps(manifest or _manifest(), ensure_ascii=False, indent=2))
        archive.writestr("SKILL.md", "# GitHub Research\n\nUse for GitHub source research.\n")
    data = package_path.read_bytes()
    return package_path, sha256_digest(data)


def _write_registry(root: Path, package_path: Path, digest: str) -> Path:
    registry_path = root / "registry.json"
    registry = {
        "registry_version": "0.1",
        "generated_at": "2026-06-20T00:00:00Z",
        "skills": [
            {
                "id": "github-research",
                "name": "GitHub Research",
                "version": "0.1.0",
                "description": "Search and compare open-source GitHub repositories.",
                "category": "research",
                "publisher": "coder-official",
                "package_url": package_path.name,
                "manifest_url": None,
                "sha256": digest,
                "signature": "sig-placeholder",
                "risk_level": "low",
                "external_effect": False,
                "requires_connectors": ["github_readonly"],
            }
        ],
    }
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry_path


if __name__ == "__main__":
    unittest.main()
