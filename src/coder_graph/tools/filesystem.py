from __future__ import annotations

from pathlib import Path


DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".vite",
    ".venv",
    "venv",
    "__pycache__",
    "outputs",
    ".coder_history",
}

TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".css",
    ".scss",
    ".html",
    ".txt",
}


def resolve_existing_dir(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {resolved}")
    return resolved


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def summarize_project(root: Path, scopes: list[str] | None = None, max_files: int = 300) -> list[dict]:
    roots = _scope_roots(root, scopes or [])
    summaries: list[dict] = []

    for scan_root in roots:
        if not scan_root.exists():
            continue

        for file_path in scan_root.rglob("*"):
            if len(summaries) >= max_files:
                return summaries
            if not file_path.is_file():
                continue
            if _has_ignored_part(file_path, root):
                continue
            if file_path.suffix.lower() not in TEXT_EXTENSIONS:
                continue

            relative = file_path.relative_to(root).as_posix()
            summaries.append(
                {
                    "path": relative,
                    "size_bytes": file_path.stat().st_size,
                    "kind": file_path.suffix.lower().lstrip(".") or "text",
                }
            )

    return summaries


def normalize_allowed_paths(root: Path, paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in paths:
        candidate = (root / item).resolve()
        if not is_relative_to(candidate, root):
            raise ValueError(f"Allowed path escapes repo root: {item}")
        normalized.append(candidate.relative_to(root).as_posix())
    return normalized


def normalize_scope_paths(root: Path, scopes: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for item in scopes or []:
        scope = item.strip()
        if not scope or scope in {".", "./"}:
            continue
        candidate = (root / scope).resolve()
        if not is_relative_to(candidate, root):
            raise ValueError(f"Scope escapes repo root: {scope}")
        if not candidate.exists():
            raise FileNotFoundError(f"Scope does not exist: {scope}")
        if not candidate.is_dir():
            raise NotADirectoryError(f"Scope is not a directory: {scope}")
        normalized.append(candidate.relative_to(root.resolve()).as_posix())
    return normalized


def resolve_scoped_path(root: Path, path: str, scopes: list[str] | None = None) -> Path:
    candidate = (root / path).resolve()
    if not is_relative_to(candidate, root):
        raise ValueError(f"Path escapes repo root: {path}")
    allowed_scopes = normalize_scope_paths(root, scopes)
    if allowed_scopes and not any(is_relative_to(candidate, (root / scope).resolve()) for scope in allowed_scopes):
        raise ValueError(f"Path is outside allowed scopes: {path}")
    return candidate


def _scope_roots(root: Path, scopes: list[str]) -> list[Path]:
    normalized = normalize_scope_paths(root, scopes)
    if not normalized:
        return [root]
    return [(root / scope).resolve() for scope in normalized]


def _has_ignored_part(file_path: Path, root: Path) -> bool:
    relative_parts = file_path.relative_to(root).parts
    return any(part in DEFAULT_IGNORE_DIRS or part.endswith(".egg-info") for part in relative_parts)
