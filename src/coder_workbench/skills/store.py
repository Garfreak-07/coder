from __future__ import annotations

import json
import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from coder_workbench.skills.schema import InstalledSkillRecord, SkillPackageManifest, SkillSummary, SkillTrustLevel


class InstalledSkillStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.skills_dir = self.root / "skills"
        self.tmp_dir = self.root / ".tmp" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def list_installed(self) -> list[InstalledSkillRecord]:
        records: list[InstalledSkillRecord] = []
        for path in sorted(self.skills_dir.glob("*/installed.json")):
            try:
                records.append(InstalledSkillRecord.model_validate(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return records

    def list_summaries(self) -> list[dict[str, object]]:
        return [record.summary().model_dump(mode="json") for record in self.list_installed()]

    def get_skill(self, skill_id: str) -> InstalledSkillRecord:
        path = self._record_path(skill_id)
        if not path.exists():
            raise KeyError(skill_id)
        return InstalledSkillRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def skill_root(self, skill_id: str) -> Path:
        path = self._skill_dir(skill_id)
        if not path.exists():
            raise KeyError(skill_id)
        return path

    def read_skill_body(self, skill_id: str) -> str:
        path = self.skill_root(skill_id) / "SKILL.md"
        if not path.exists():
            raise KeyError(skill_id)
        return path.read_text(encoding="utf-8")

    def enable(self, skill_id: str) -> InstalledSkillRecord:
        return self._set_enabled(skill_id, True)

    def disable(self, skill_id: str) -> InstalledSkillRecord:
        return self._set_enabled(skill_id, False)

    def search(self, query: str) -> list[SkillSummary]:
        terms = [term.lower() for term in query.split() if term.strip()]
        if not terms:
            return [record.summary() for record in self.list_installed() if record.enabled]
        matches = []
        for record in self.list_installed():
            haystack = " ".join(
                [
                    record.manifest.id,
                    record.manifest.name,
                    record.manifest.description,
                    record.manifest.category,
                    " ".join(record.manifest.requires),
                    " ".join(record.manifest.produces),
                    " ".join(record.manifest.trigger_hints),
                ]
            ).lower()
            if all(term in haystack for term in terms):
                matches.append(record.summary())
        return matches

    def install_from_directory(
        self,
        package_dir: str | Path,
        *,
        manifest: SkillPackageManifest,
        package_sha256: str,
        trust_level: SkillTrustLevel,
        source: str = "remote",
        source_url: str | None = None,
        enabled: bool = True,
    ) -> InstalledSkillRecord:
        record = InstalledSkillRecord(
            manifest=manifest,
            source="remote" if source == "remote" else "local",
            source_url=source_url,
            package_sha256=package_sha256,
            trust_level=trust_level,
            enabled=enabled,
            pinned_version=manifest.version,
        )
        source_dir = Path(package_dir)
        if not source_dir.exists():
            raise FileNotFoundError(str(source_dir))

        with self._lock:
            dest = self._skill_dir(manifest.id)
            staging = self.tmp_dir / f"{manifest.id}-{uuid4().hex}"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(source_dir, staging)
            (staging / "skill.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            (staging / "installed.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(staging), str(dest))
        return record

    def remove(self, skill_id: str) -> None:
        with self._lock:
            dest = self._skill_dir(skill_id)
            if not dest.exists():
                raise KeyError(skill_id)
            shutil.rmtree(dest)

    def _set_enabled(self, skill_id: str, enabled: bool) -> InstalledSkillRecord:
        with self._lock:
            record = self.get_skill(skill_id)
            updated = record.model_copy(update={"enabled": enabled})
            self._record_path(skill_id).write_text(updated.model_dump_json(indent=2), encoding="utf-8")
            return updated

    def _record_path(self, skill_id: str) -> Path:
        return self._skill_dir(skill_id) / "installed.json"

    def _skill_dir(self, skill_id: str) -> Path:
        safe = _safe_skill_id(skill_id)
        return self.skills_dir / safe


def _safe_skill_id(skill_id: str) -> str:
    safe = "".join(char for char in skill_id if char.isalnum() or char in {"-", "_", "."})
    if not safe or safe != skill_id:
        raise KeyError(skill_id)
    return safe
