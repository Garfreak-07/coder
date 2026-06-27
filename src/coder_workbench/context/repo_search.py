from __future__ import annotations

import fnmatch
import json
import re
import shutil
import subprocess
from pathlib import Path

from .repo_discovery import RepoFileDiscoveryService
from .repo_models import RepoSearchHit
from .repo_safety import binary_bytes, ignored_by_default, normalize_repo_path, path_is_within_scopes, resolve_repo_root, sensitive_repo_path


_MAX_PATTERN_CHARS = 300
_MAX_LINE_CHARS = 500
_MAX_FALLBACK_FILE_BYTES = 2 * 1024 * 1024


class RepoTextSearchService:
    def __init__(self, *, repo_root: str | Path, scope_paths: list[str] | None = None) -> None:
        self.repo_root = resolve_repo_root(repo_root)
        self.scope_paths = [normalize_repo_path(scope) for scope in scope_paths or [] if str(scope).strip()]

    def search_text(
        self,
        pattern: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        include_globs: list[str] | None = None,
        max_results: int = 100,
        context_lines: int = 0,
    ) -> list[RepoSearchHit]:
        clean_pattern = self._clean_pattern(pattern)
        limit = _bounded_limit(max_results, upper=100)
        context = min(max(int(context_lines or 0), 0), 5)
        globs = [str(item) for item in include_globs or [] if str(item).strip()]
        if self._command_available("rg"):
            hits = self._rg_search(
                clean_pattern,
                regex=regex,
                case_sensitive=case_sensitive,
                include_globs=globs,
                max_results=limit,
            )
            if hits:
                return hits[:limit]
        return self._python_search(
            clean_pattern,
            regex=regex,
            case_sensitive=case_sensitive,
            include_globs=globs,
            max_results=limit,
            context_lines=context,
        )

    def _rg_search(
        self,
        pattern: str,
        *,
        regex: bool,
        case_sensitive: bool,
        include_globs: list[str],
        max_results: int,
    ) -> list[RepoSearchHit]:
        args = ["rg", "--json", "--line-number", "--column", "--color", "never"]
        if not regex:
            args.append("-F")
        if not case_sensitive:
            args.append("-i")
        for dirname in sorted({".git", ".coder", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".cache"}):
            args.extend(["--glob", f"!{dirname}/**"])
        for glob in include_globs:
            args.extend(["--glob", glob])
        args.append(pattern)
        args.extend(self.scope_paths or ["."])
        result = self._run_command(args)
        if result.returncode not in {0, 1}:
            return []
        hits: list[RepoSearchHit] = []
        for line in result.stdout.splitlines():
            if len(hits) >= max_results:
                break
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "match":
                continue
            hit = self._hit_from_rg_match(record)
            if hit is None:
                continue
            if not self._allowed_path(hit.path):
                continue
            hits.append(hit)
        return hits

    def _python_search(
        self,
        pattern: str,
        *,
        regex: bool,
        case_sensitive: bool,
        include_globs: list[str],
        max_results: int,
        context_lines: int,
    ) -> list[RepoSearchHit]:
        compiled = _compile_pattern(pattern, regex=regex, case_sensitive=case_sensitive)
        files = RepoFileDiscoveryService(repo_root=self.repo_root, scope_paths=self.scope_paths).list_files(max_results=5000)
        hits: list[RepoSearchHit] = []
        for file_ref in files:
            if len(hits) >= max_results:
                break
            if include_globs and not any(fnmatch.fnmatch(file_ref.path, glob) for glob in include_globs):
                continue
            absolute = self.repo_root / file_ref.path
            if not self._safe_text_file(absolute, file_ref.path):
                continue
            text = absolute.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            for index, line in enumerate(lines, start=1):
                if len(hits) >= max_results:
                    break
                hit = _line_hit(
                    file_ref.path,
                    index,
                    line,
                    pattern=pattern,
                    compiled=compiled,
                    regex=regex,
                    case_sensitive=case_sensitive,
                    context_lines=context_lines,
                    all_lines=lines,
                )
                if hit is not None:
                    hits.append(hit)
        return hits

    def _hit_from_rg_match(self, record: dict[str, object]) -> RepoSearchHit | None:
        data = record.get("data")
        if not isinstance(data, dict):
            return None
        path_record = data.get("path")
        line_record = data.get("lines")
        submatches = data.get("submatches")
        if not isinstance(path_record, dict) or not isinstance(line_record, dict) or not isinstance(submatches, list):
            return None
        path = normalize_repo_path(str(path_record.get("text") or ""))
        line_number = int(data.get("line_number") or 0)
        text = _preview_line(str(line_record.get("text") or ""))
        first_match = next((item for item in submatches if isinstance(item, dict)), None)
        column = int(first_match.get("start") or 0) + 1 if first_match else None
        match = None
        if first_match and isinstance(first_match.get("match"), dict):
            match = str(first_match["match"].get("text") or "")
        if not path or line_number <= 0:
            return None
        return RepoSearchHit(path=path, line=line_number, column=column, text=text, match=match)

    def _allowed_path(self, relative_path: str) -> bool:
        return (
            path_is_within_scopes(relative_path, self.scope_paths)
            and not ignored_by_default(relative_path, self.scope_paths)
            and not sensitive_repo_path(relative_path)
        )

    def _safe_text_file(self, path: Path, relative_path: str) -> bool:
        if not self._allowed_path(relative_path):
            return False
        if not path.is_file() or path.stat().st_size > _MAX_FALLBACK_FILE_BYTES:
            return False
        sample = path.read_bytes()[:4096]
        return not binary_bytes(sample)

    def _clean_pattern(self, pattern: str) -> str:
        text = str(pattern or "")
        if not text.strip():
            raise ValueError("search pattern is required")
        if len(text) > _MAX_PATTERN_CHARS:
            raise ValueError("search pattern is too long")
        return text

    def _command_available(self, command: str) -> bool:
        return shutil.which(command) is not None

    def _run_command(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=self.repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _compile_pattern(pattern: str, *, regex: bool, case_sensitive: bool) -> re.Pattern[str] | None:
    if not regex:
        return None
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags=flags)


def _line_hit(
    path: str,
    line_number: int,
    line: str,
    *,
    pattern: str,
    compiled: re.Pattern[str] | None,
    regex: bool,
    case_sensitive: bool,
    context_lines: int,
    all_lines: list[str],
) -> RepoSearchHit | None:
    if regex:
        match = compiled.search(line) if compiled else None
        if match is None:
            return None
        column = match.start() + 1
        matched_text = match.group(0)
    else:
        haystack = line if case_sensitive else line.lower()
        needle = pattern if case_sensitive else pattern.lower()
        position = haystack.find(needle)
        if position < 0:
            return None
        column = position + 1
        matched_text = line[position : position + len(pattern)]
    text = _line_with_context(line_number, line, context_lines=context_lines, all_lines=all_lines)
    return RepoSearchHit(path=path, line=line_number, column=column, text=_preview_line(text), match=matched_text)


def _line_with_context(line_number: int, line: str, *, context_lines: int, all_lines: list[str]) -> str:
    if context_lines <= 0:
        return line
    start = max(1, line_number - context_lines)
    end = min(len(all_lines), line_number + context_lines)
    return "\n".join(f"{index}: {all_lines[index - 1]}" for index in range(start, end + 1))


def _preview_line(line: str) -> str:
    text = line.rstrip("\n\r")
    if len(text) <= _MAX_LINE_CHARS:
        return text
    return text[: _MAX_LINE_CHARS - 3].rstrip() + "..."


def _bounded_limit(value: int, *, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = upper
    return min(max(parsed, 1), upper)


__all__ = ["RepoTextSearchService"]
