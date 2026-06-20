from __future__ import annotations

import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.skills.registry_client import RegistryClient
from coder_workbench.skills.schema import InstalledSkillRecord, RemoteSkillEntry
from coder_workbench.skills.store import InstalledSkillStore
from coder_workbench.skills.verifier import (
    SkillPackageVerification,
    SkillVerificationError,
    locate_skill_root,
    safe_extract_zip,
    verify_extracted_package,
    verify_sha256,
)


class SkillInstallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: InstalledSkillRecord
    verification: SkillPackageVerification
    warnings: list[str] = Field(default_factory=list)


class SkillInstaller:
    def __init__(self, *, client: RegistryClient, store: InstalledSkillStore) -> None:
        self.client = client
        self.store = store

    def install(self, skill_id: str, *, allow_untrusted: bool = False) -> SkillInstallResult:
        index = self.client.fetch_index()
        entry = index.get(skill_id)
        return self.install_entry(entry, allow_untrusted=allow_untrusted)

    def install_entry(self, entry: RemoteSkillEntry, *, allow_untrusted: bool = False) -> SkillInstallResult:
        warnings = _install_policy_warnings(entry, allow_untrusted=allow_untrusted)
        package_bytes = self.client.fetch_package(entry)
        package_sha256 = verify_sha256(package_bytes, entry.sha256)
        with tempfile.TemporaryDirectory() as tmp:
            extracted = safe_extract_zip(package_bytes, Path(tmp) / "package")
            skill_root = locate_skill_root(extracted)
            verification = verify_extracted_package(
                skill_root,
                package_sha256=package_sha256,
                signature_present=entry.signature is not None,
            )
            _assert_manifest_matches_registry(entry, verification)
            record = self.store.install_from_directory(
                skill_root,
                manifest=verification.manifest,
                package_sha256=package_sha256,
                trust_level=entry.trust_level,
                source="remote",
                source_url=entry.package_url,
                enabled=True,
            )
        return SkillInstallResult(
            record=record,
            verification=verification,
            warnings=[*warnings, *verification.warnings],
        )


def _install_policy_warnings(entry: RemoteSkillEntry, *, allow_untrusted: bool) -> list[str]:
    if entry.trust_level in {"local", "untrusted"} and not allow_untrusted:
        raise SkillVerificationError("local or untrusted skills require developer import or advanced mode")
    if entry.trust_level == "untrusted" and entry.risk_level == "high":
        raise SkillVerificationError("high-risk untrusted skills cannot be installed")
    warnings: list[str] = []
    if entry.trust_level == "community":
        warnings.append("community skill installed with warning")
    if entry.external_effect:
        warnings.append("skill declares external effects and requires runtime preview before use")
    if entry.signature and entry.trust_level not in {"official", "verified"}:
        warnings.append("signature is present but publisher trust is not official or verified")
    return warnings


def _assert_manifest_matches_registry(entry: RemoteSkillEntry, verification: SkillPackageVerification) -> None:
    manifest = verification.manifest
    if manifest.id != entry.id:
        raise SkillVerificationError(f"manifest id {manifest.id!r} does not match registry id {entry.id!r}")
    if manifest.version != entry.version:
        raise SkillVerificationError(
            f"manifest version {manifest.version!r} does not match registry version {entry.version!r}"
        )
    if manifest.external_effect != entry.external_effect:
        raise SkillVerificationError("manifest external_effect does not match registry metadata")
    if manifest.risk_level != entry.risk_level:
        raise SkillVerificationError("manifest risk_level does not match registry metadata")
