from __future__ import annotations

import json
import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from coder_workbench.skills.schema import (
    InstalledSkillRecord,
    SkillPackageManifest,
    SkillSummary,
    SkillTrustLevel,
    SkillUpdatePolicy,
)


class InstalledSkillStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.skills_dir = self.root / "skills"
        self.history_dir = self.root / "skill-history"
        self.tmp_dir = self.root / ".tmp" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
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
        pinned_version: str | None = None,
        update_policy: SkillUpdatePolicy | None = None,
        archive_existing: bool = True,
        clear_pin: bool = False,
    ) -> InstalledSkillRecord:
        existing = self._read_record_if_exists(manifest.id)
        resolved_pinned_version = None if clear_pin else (
            pinned_version if pinned_version is not None else (existing.pinned_version if existing else None)
        )
        record = InstalledSkillRecord(
            manifest=manifest,
            source="remote" if source == "remote" else "local",
            source_url=source_url,
            package_sha256=package_sha256,
            trust_level=trust_level,
            enabled=enabled,
            pinned_version=resolved_pinned_version,
            update_policy=update_policy or (existing.update_policy if existing else "manual"),
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
                if archive_existing:
                    self._archive_skill_dir(dest)
                shutil.rmtree(dest)
            shutil.move(str(staging), str(dest))
        return record

    def list_versions(self, skill_id: str) -> list[dict[str, object]]:
        current = self.get_skill(skill_id)
        versions: list[dict[str, object]] = [
            {
                "version": current.manifest.version,
                "package_sha256": current.package_sha256,
                "installed_at": current.installed_at,
                "source": current.source,
                "current": True,
            }
        ]
        for path, record in self._history_records(skill_id):
            versions.append(
                {
                    "version": record.manifest.version,
                    "package_sha256": record.package_sha256,
                    "installed_at": record.installed_at,
                    "source": record.source,
                    "current": False,
                    "history_id": path.name,
                }
            )
        return versions

    def pin(self, skill_id: str, version: str | None = None) -> InstalledSkillRecord:
        with self._lock:
            record = self.get_skill(skill_id)
            target = (version or record.manifest.version).strip()
            if not target:
                raise ValueError("pinned version must not be empty")
            available = {str(item["version"]) for item in self.list_versions(skill_id)}
            if target not in available:
                raise ValueError(f"version {target!r} is not available for skill {skill_id!r}")
            updated = record.model_copy(update={"pinned_version": target, "update_policy": "manual"})
            self._record_path(skill_id).write_text(updated.model_dump_json(indent=2), encoding="utf-8")
            return updated

    def unpin(self, skill_id: str) -> InstalledSkillRecord:
        with self._lock:
            record = self.get_skill(skill_id)
            updated = record.model_copy(update={"pinned_version": None})
            self._record_path(skill_id).write_text(updated.model_dump_json(indent=2), encoding="utf-8")
            return updated

    def set_update_policy(self, skill_id: str, update_policy: SkillUpdatePolicy) -> InstalledSkillRecord:
        with self._lock:
            record = self.get_skill(skill_id)
            if update_policy == "auto_official_low_risk" and not _auto_update_allowed_for_record(record):
                raise ValueError("auto-update is only allowed for official low-risk skills without external effects")
            updated = record.model_copy(update={"update_policy": update_policy})
            self._record_path(skill_id).write_text(updated.model_dump_json(indent=2), encoding="utf-8")
            return updated

    def rollback(self, skill_id: str, *, version: str | None = None) -> InstalledSkillRecord:
        with self._lock:
            dest = self._skill_dir(skill_id)
            if not dest.exists():
                raise KeyError(skill_id)
            candidates = self._history_records(skill_id)
            if version is not None:
                candidates = [(path, record) for path, record in candidates if record.manifest.version == version]
            if not candidates:
                raise KeyError(version or skill_id)
            source_path, _record = candidates[-1]
            staging = self.tmp_dir / f"{skill_id}-rollback-{uuid4().hex}"
            shutil.copytree(source_path, staging)
            self._archive_skill_dir(dest)
            shutil.rmtree(dest)
            shutil.move(str(staging), str(dest))
            return self.get_skill(skill_id)

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

    def _read_record_if_exists(self, skill_id: str) -> InstalledSkillRecord | None:
        path = self._record_path(skill_id)
        if not path.exists():
            return None
        try:
            return InstalledSkillRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _archive_skill_dir(self, skill_dir: Path) -> None:
        record = self._read_record_if_exists(skill_dir.name)
        if record is None:
            return
        history_root = self._history_skill_dir(record.id)
        label = f"{record.manifest.version}-{record.package_sha256[:12]}-{uuid4().hex[:8]}"
        shutil.copytree(skill_dir, history_root / label)

    def _history_records(self, skill_id: str) -> list[tuple[Path, InstalledSkillRecord]]:
        records: list[tuple[Path, InstalledSkillRecord]] = []
        history_root = self._history_skill_dir(skill_id)
        if not history_root.exists():
            return records
        for path in sorted(history_root.iterdir(), key=lambda item: item.stat().st_mtime):
            record_path = path / "installed.json"
            if not record_path.exists():
                continue
            try:
                records.append((path, InstalledSkillRecord.model_validate(json.loads(record_path.read_text(encoding="utf-8")))))
            except Exception:
                continue
        return records

    def _record_path(self, skill_id: str) -> Path:
        return self._skill_dir(skill_id) / "installed.json"

    def _skill_dir(self, skill_id: str) -> Path:
        safe = _safe_skill_id(skill_id)
        return self.skills_dir / safe

    def _history_skill_dir(self, skill_id: str) -> Path:
        safe = _safe_skill_id(skill_id)
        path = self.history_dir / safe
        path.mkdir(parents=True, exist_ok=True)
        return path


def _safe_skill_id(skill_id: str) -> str:
    safe = "".join(char for char in skill_id if char.isalnum() or char in {"-", "_", "."})
    if not safe or safe != skill_id:
        raise KeyError(skill_id)
    return safe


def _auto_update_allowed_for_record(record: InstalledSkillRecord) -> bool:
    return (
        record.trust_level == "official"
        and record.manifest.risk_level == "low"
        and not record.manifest.external_effect
    )
