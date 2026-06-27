from __future__ import annotations

import re
from pathlib import Path


DEFAULT_IGNORED_DIRS = {
    ".git",
    ".coder",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".cache",
}

ALWAYS_DENIED_DIRS = {
    ".git",
    ".ssh",
    ".aws",
    ".kube",
    ".azure",
    ".gnupg",
    ".docker",
}

SENSITIVE_FILE_NAMES = {
    ".env",
    ".local-env.ps1",
    "credentials",
    "id_rsa",
    "id_ed25519",
}

SENSITIVE_SUFFIXES = {
    ".pem",
    ".p12",
    ".pfx",
    ".key",
}


def resolve_repo_root(repo_root: str | Path) -> Path:
    return Path(repo_root).expanduser().resolve(strict=False)


def normalize_repo_path(path: str | Path) -> str:
    text = str(path).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text.strip("/")


def resolve_under_root(repo_root: str | Path, path: str | Path) -> tuple[Path, str]:
    root = resolve_repo_root(repo_root)
    raw = Path(path)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.expanduser().resolve(strict=False)
    if not _is_relative_to(resolved, root):
        raise ValueError("path must stay under repo_root")
    return resolved, normalize_repo_path(resolved.relative_to(root))


def path_is_within_scopes(relative_path: str, scope_paths: list[str] | None) -> bool:
    scopes = [normalize_repo_path(scope) for scope in scope_paths or [] if str(scope).strip()]
    if not scopes:
        return True
    rel = normalize_repo_path(relative_path)
    for scope in scopes:
        if rel == scope or rel.startswith(f"{scope}/"):
            return True
    return False


def ignored_by_default(relative_path: str, scope_paths: list[str] | None = None) -> bool:
    parts = _parts(relative_path)
    if not parts:
        return False
    lowered = [part.lower() for part in parts]
    if any(part in ALWAYS_DENIED_DIRS for part in lowered):
        return True
    ignored = next((part for part in lowered if part in DEFAULT_IGNORED_DIRS), None)
    if ignored is None:
        return False
    return not _scope_explicitly_includes(scope_paths or [], ignored)


def sensitive_repo_path(relative_path: str) -> bool:
    parts = [part.lower() for part in _parts(relative_path)]
    if not parts:
        return False
    name = parts[-1]
    if name in SENSITIVE_FILE_NAMES or name.startswith(".env."):
        return True
    if any(part in ALWAYS_DENIED_DIRS - {".git"} for part in parts):
        return True
    if name.endswith(tuple(SENSITIVE_SUFFIXES)):
        return True
    return bool(re.search(r"(^|[-_.])(private[-_.]?key|secret[-_.]?key)($|[-_.])", name))


def binary_bytes(data: bytes) -> bool:
    return b"\0" in data


def safe_store_segment(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    if text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError(f"{label} must be a single safe path segment")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", text):
        raise ValueError(f"{label} contains unsupported characters")
    return text


def _scope_explicitly_includes(scope_paths: list[str], ignored_dir: str) -> bool:
    for scope in scope_paths:
        normalized = normalize_repo_path(scope).lower()
        if normalized == ignored_dir or normalized.startswith(f"{ignored_dir}/"):
            return True
    return False


def _parts(path: str) -> tuple[str, ...]:
    normalized = normalize_repo_path(path)
    return tuple(part for part in normalized.split("/") if part)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = [
    "DEFAULT_IGNORED_DIRS",
    "binary_bytes",
    "ignored_by_default",
    "normalize_repo_path",
    "path_is_within_scopes",
    "resolve_repo_root",
    "resolve_under_root",
    "safe_store_segment",
    "sensitive_repo_path",
]
