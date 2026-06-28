from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, url2pathname, urlopen

from coder_workbench.skills.schema import RemoteSkillEntry, RemoteSkillIndex, SkillPackageManifest


class RegistryClientError(ValueError):
    pass


class RegistryClient:
    def __init__(self, index_url: str, *, timeout: float = 20.0) -> None:
        self.index_url = str(index_url)
        self.timeout = timeout

    def fetch_index(self) -> RemoteSkillIndex:
        payload = self._read_json(self.index_url)
        try:
            return RemoteSkillIndex.model_validate(payload)
        except Exception as exc:
            raise RegistryClientError(f"registry index is invalid: {exc}") from exc

    def fetch_manifest(self, entry: RemoteSkillEntry) -> SkillPackageManifest:
        if not entry.manifest_url:
            raise RegistryClientError(f"skill {entry.id} does not declare manifest_url")
        payload = self._read_json(self._resolve(entry.manifest_url))
        try:
            return SkillPackageManifest.model_validate(payload)
        except Exception as exc:
            raise RegistryClientError(f"manifest for skill {entry.id} is invalid: {exc}") from exc

    def fetch_package(self, entry: RemoteSkillEntry) -> bytes:
        return self._read_bytes(self._resolve(entry.package_url))

    def _read_json(self, url: str) -> dict[str, Any]:
        try:
            payload = json.loads(self._read_bytes(self._resolve(url)).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RegistryClientError(f"registry JSON is invalid: {url}") from exc
        if not isinstance(payload, dict):
            raise RegistryClientError(f"registry JSON must be an object: {url}")
        return payload

    def _read_bytes(self, url: str) -> bytes:
        if _is_windows_path(url):
            return Path(url).read_bytes()
        parsed = urlparse(url)
        try:
            if parsed.scheme in {"http", "https"}:
                request = Request(url, headers={"User-Agent": "coder-workbench-skill-registry/0.1"})
                with urlopen(request, timeout=self.timeout) as response:  # nosec B310 - registry URL is user configured
                    return response.read()
            if parsed.scheme == "file":
                return Path(url2pathname(unquote(parsed.path))).read_bytes()
            if not parsed.scheme:
                return Path(url).read_bytes()
        except OSError as exc:
            raise RegistryClientError(f"failed to read registry resource {url}: {exc}") from exc
        raise RegistryClientError(f"unsupported registry URL scheme: {parsed.scheme}")

    def _resolve(self, url: str) -> str:
        if _is_windows_path(url):
            return url
        parsed = urlparse(url)
        if parsed.scheme:
            return url
        if _is_windows_path(self.index_url):
            return str((Path(self.index_url).parent / url).resolve())
        base = urlparse(self.index_url)
        if base.scheme in {"http", "https", "file"}:
            return urljoin(self.index_url, url)
        base_path = Path(self.index_url)
        return str((base_path.parent / url).resolve())


def _is_windows_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value))
