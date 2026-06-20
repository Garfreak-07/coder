from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.skills.schema import SkillPackageManifest


class SkillVerificationError(ValueError):
    pass


class SkillPackageVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str
    manifest: SkillPackageManifest
    warnings: list[str] = Field(default_factory=list)
    signature_present: bool = False


def sha256_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_sha256(data: bytes, expected: str) -> str:
    expected_digest = _normalize_sha256(expected)
    actual = sha256_digest(data)
    if actual != expected_digest:
        raise SkillVerificationError(f"checksum mismatch: expected {expected_digest}, got {actual}")
    return actual


def safe_extract_zip(data: bytes, destination: str | Path) -> Path:
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                _validate_zip_member(member.filename, dest_resolved)
            archive.extractall(dest)
    except zipfile.BadZipFile as exc:
        raise SkillVerificationError("skill package must be a valid zip archive") from exc
    return dest


def locate_skill_root(extracted_dir: str | Path) -> Path:
    root = Path(extracted_dir)
    if (root / "skill.json").is_file():
        return root
    candidates = [path.parent for path in root.rglob("skill.json") if path.is_file()]
    if len(candidates) == 1:
        return candidates[0]
    raise SkillVerificationError("skill package must contain exactly one skill.json")


def read_skill_manifest(skill_root: str | Path) -> SkillPackageManifest:
    path = Path(skill_root) / "skill.json"
    if not path.exists():
        raise SkillVerificationError("skill package is missing skill.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillVerificationError("skill.json must be valid JSON") from exc
    return SkillPackageManifest.model_validate(payload)


def verify_package_layout(skill_root: str | Path) -> list[str]:
    root = Path(skill_root)
    warnings: list[str] = []
    if not (root / "SKILL.md").is_file():
        raise SkillVerificationError("skill package is missing SKILL.md")
    if (root / "scripts").exists():
        warnings.append("scripts directory is present but runtime script execution is disabled")
    if (root / "hooks").exists():
        warnings.append("hooks directory is present but hook execution is disabled")
    return warnings


def verify_extracted_package(
    skill_root: str | Path,
    *,
    package_sha256: str,
    signature_present: bool = False,
) -> SkillPackageVerification:
    manifest = read_skill_manifest(skill_root)
    warnings = verify_package_layout(skill_root)
    return SkillPackageVerification(
        sha256=package_sha256,
        manifest=manifest,
        warnings=warnings,
        signature_present=signature_present,
    )


def _normalize_sha256(value: str) -> str:
    text = value.strip().lower()
    if text.startswith("sha256:"):
        text = text.removeprefix("sha256:")
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise SkillVerificationError("expected sha256 must be a 64-character hex digest")
    return text


def _validate_zip_member(name: str, dest_resolved: Path) -> None:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        raise SkillVerificationError(f"unsafe absolute package path: {name}")
    if re.match(r"^[A-Za-z]:", normalized):
        raise SkillVerificationError(f"unsafe drive-qualified package path: {name}")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise SkillVerificationError(f"unsafe parent traversal in package path: {name}")
    target = (dest_resolved / Path(*parts)).resolve()
    if not target.is_relative_to(dest_resolved):
        raise SkillVerificationError(f"unsafe package path: {name}")

