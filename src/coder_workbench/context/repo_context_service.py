from __future__ import annotations

from pathlib import Path
from typing import Any

from .repo_discovery import RepoFileDiscoveryService
from .repo_evidence import RepoEvidenceStore
from .repo_models import RepoEvidenceRef, RepoFileRef, RepoReadSnippet, RepoSearchHit
from .repo_read import RepoReadService
from .repo_search import RepoTextSearchService


class NativeRepoContextService:
    def __init__(
        self,
        *,
        coder_store_root: str | Path,
        repo_root: str | Path,
        run_id: str,
        scope_paths: list[str] | None = None,
    ) -> None:
        self.coder_store_root = Path(coder_store_root)
        self.repo_root = Path(repo_root)
        self.run_id = run_id
        self.scope_paths = list(scope_paths or [])
        self.evidence_store = RepoEvidenceStore(self.coder_store_root)

    def find_files(
        self,
        *,
        query: str | None = None,
        extensions: list[str] | None = None,
        max_results: int = 200,
    ) -> tuple[list[RepoFileRef], RepoEvidenceRef]:
        files = RepoFileDiscoveryService(repo_root=self.repo_root, scope_paths=self.scope_paths).list_files(
            query=query,
            extensions=extensions,
            max_results=max_results,
        )
        ref = self._write_evidence(
            kind="repo_file_list",
            summary=f"Found {len(files)} repo files.",
            payload={
                "evidence_kind": "repo_evidence",
                "operation": "find_files",
                "query": query,
                "extensions": extensions or [],
                "max_results": max_results,
                "files": [item.model_dump(mode="json", exclude_none=True) for item in files],
            },
        )
        return files, ref

    def search_text(
        self,
        pattern: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        include_globs: list[str] | None = None,
        max_results: int = 100,
        context_lines: int = 0,
    ) -> tuple[list[RepoSearchHit], RepoEvidenceRef]:
        hits = RepoTextSearchService(repo_root=self.repo_root, scope_paths=self.scope_paths).search_text(
            pattern,
            regex=regex,
            case_sensitive=case_sensitive,
            include_globs=include_globs,
            max_results=max_results,
            context_lines=context_lines,
        )
        ref = self._write_evidence(
            kind="repo_text_search",
            summary=f"Found {len(hits)} repo text hits for {pattern!r}.",
            payload={
                "evidence_kind": "repo_evidence",
                "operation": "search_text",
                "pattern": pattern,
                "regex": regex,
                "case_sensitive": case_sensitive,
                "include_globs": include_globs or [],
                "max_results": max_results,
                "hits": [item.model_dump(mode="json", exclude_none=True) for item in hits],
            },
        )
        return hits, ref

    def read_file_range(
        self,
        path: str,
        *,
        start_line: int = 1,
        max_lines: int = 120,
        max_chars: int = 16_000,
    ) -> tuple[RepoReadSnippet, RepoEvidenceRef]:
        snippet = RepoReadService(repo_root=self.repo_root, scope_paths=self.scope_paths).read_file_range(
            path,
            start_line=start_line,
            max_lines=max_lines,
            max_chars=max_chars,
        )
        ref = self._write_evidence(
            kind="repo_read",
            summary=f"Read {snippet.path}:{snippet.start_line}-{snippet.end_line}.",
            payload={
                "evidence_kind": "repo_evidence",
                "operation": "read_file_range",
                "path": path,
                "snippet": snippet.model_dump(mode="json", exclude_none=True),
            },
        )
        return snippet, ref

    def read_evidence(self, ref_id: str) -> dict[str, Any]:
        return self.evidence_store.read_evidence(ref_id)

    def _write_evidence(self, *, kind: str, summary: str, payload: dict[str, Any]) -> RepoEvidenceRef:
        return self.evidence_store.write_evidence(
            run_id=self.run_id,
            kind=kind,
            repo_root=str(self.repo_root),
            scope_paths=self.scope_paths,
            summary=summary,
            payload=payload,
        )


__all__ = ["NativeRepoContextService"]
