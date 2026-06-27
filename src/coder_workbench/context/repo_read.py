from __future__ import annotations

from pathlib import Path

from .repo_models import RepoReadSnippet
from .repo_safety import (
    binary_bytes,
    ignored_by_default,
    path_is_within_scopes,
    resolve_repo_root,
    resolve_under_root,
    sensitive_repo_path,
)


class RepoReadService:
    def __init__(self, *, repo_root: str | Path, scope_paths: list[str] | None = None) -> None:
        self.repo_root = resolve_repo_root(repo_root)
        self.scope_paths = list(scope_paths or [])

    def read_file_range(
        self,
        path: str,
        *,
        start_line: int = 1,
        max_lines: int = 120,
        max_chars: int = 16_000,
    ) -> RepoReadSnippet:
        start = max(1, int(start_line or 1))
        line_limit = min(max(int(max_lines or 1), 1), 200)
        char_limit = min(max(int(max_chars or 1), 1), 100_000)
        absolute, relative_path = resolve_under_root(self.repo_root, path)
        self._validate_readable_path(absolute, relative_path)

        chunks: list[str] = []
        chars_used = 0
        end_line = start
        truncated = False
        last_requested = start + line_limit - 1
        with absolute.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line_number < start:
                    continue
                if line_number > last_requested:
                    truncated = True
                    break
                remaining = char_limit - chars_used
                if remaining <= 0:
                    truncated = True
                    break
                if len(line) > remaining:
                    chunks.append(line[:remaining])
                    chars_used += remaining
                    end_line = line_number
                    truncated = True
                    break
                chunks.append(line)
                chars_used += len(line)
                end_line = line_number
        if not chunks:
            end_line = start
        return RepoReadSnippet(
            path=relative_path,
            start_line=start,
            end_line=end_line,
            text="".join(chunks),
            truncated=truncated,
        )

    def _validate_readable_path(self, path: Path, relative_path: str) -> None:
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        if not path_is_within_scopes(relative_path, self.scope_paths):
            raise ValueError("path is outside configured scope_paths")
        if ignored_by_default(relative_path, self.scope_paths):
            raise ValueError("path is ignored by default")
        if sensitive_repo_path(relative_path):
            raise ValueError("path matches a sensitive credential policy")
        if binary_bytes(path.read_bytes()[:4096]):
            raise ValueError("binary files cannot be read as repo evidence")


__all__ = ["RepoReadService"]
