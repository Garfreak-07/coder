from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field

from coder_workbench.context.repo_context_service import NativeRepoContextService
from coder_workbench.memory.models import SECRET_MARKERS

os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from openhands.sdk.llm import TextContent
from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)

if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation
    from openhands.sdk.conversation.state import ConversationState


class CoderRepoFindFilesAction(Action):
    query: str | None = None
    extensions: list[str] = Field(default_factory=list)
    max_results: int = Field(default=50, ge=1, le=200)


class CoderRepoSearchTextAction(Action):
    pattern: str
    regex: bool = False
    case_sensitive: bool = False
    include_globs: list[str] = Field(default_factory=list)
    max_results: int = Field(default=50, ge=1, le=100)


class CoderRepoReadFileAction(Action):
    path: str
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=80, ge=1, le=200)


class CoderRepoFindFilesObservation(Observation):
    files: list[dict[str, Any]]
    returned: int
    evidence_ref: str

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        lines = [f"Found {self.returned} files:"]
        for item in self.files[:50]:
            lines.append(f"- {_redact(str(item.get('path') or ''))}")
        lines.append(f"Evidence ref: {_redact(self.evidence_ref)}")
        return [TextContent(text="\n".join(lines))]


class CoderRepoSearchTextObservation(Observation):
    hits: list[dict[str, Any]]
    returned: int
    evidence_ref: str

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        lines = [f"Search returned {self.returned} hits:"]
        for item in self.hits[:50]:
            path = _redact(str(item.get("path") or ""))
            line = item.get("line")
            text = _redact(str(item.get("text") or ""))
            lines.append(f"- {path}:{line}: {text}")
        lines.append(f"Evidence ref: {_redact(self.evidence_ref)}")
        return [TextContent(text="\n".join(lines))]


class CoderRepoReadFileObservation(Observation):
    snippet: dict[str, Any]
    evidence_ref: str

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        path = _redact(str(self.snippet.get("path") or ""))
        start = self.snippet.get("start_line")
        end = self.snippet.get("end_line")
        text = _redact(str(self.snippet.get("text") or ""))
        truncated = " (truncated)" if self.snippet.get("truncated") else ""
        return [
            TextContent(
                text=(
                    f"Read snippet: {path}:{start}-{end}{truncated}\n"
                    f"{text}\n"
                    f"Evidence ref: {_redact(self.evidence_ref)}"
                ).strip()
            )
        ]


class _RepoContextExecutorMixin:
    def __init__(
        self,
        *,
        coder_store_root: str,
        repo_root: str,
        run_id: str,
        scope_paths: list[str],
    ) -> None:
        self.service = NativeRepoContextService(
            coder_store_root=Path(coder_store_root),
            repo_root=Path(repo_root),
            run_id=run_id,
            scope_paths=scope_paths,
        )


class CoderRepoFindFilesExecutor(
    _RepoContextExecutorMixin,
    ToolExecutor[CoderRepoFindFilesAction, CoderRepoFindFilesObservation],
):
    def __call__(
        self,
        action: CoderRepoFindFilesAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> CoderRepoFindFilesObservation:
        files, ref = self.service.find_files(
            query=action.query,
            extensions=action.extensions,
            max_results=action.max_results,
        )
        return CoderRepoFindFilesObservation(
            files=[item.model_dump(mode="json", exclude_none=True) for item in files],
            returned=len(files),
            evidence_ref=ref.ref_id,
        )


class CoderRepoSearchTextExecutor(
    _RepoContextExecutorMixin,
    ToolExecutor[CoderRepoSearchTextAction, CoderRepoSearchTextObservation],
):
    def __call__(
        self,
        action: CoderRepoSearchTextAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> CoderRepoSearchTextObservation:
        hits, ref = self.service.search_text(
            action.pattern,
            regex=action.regex,
            case_sensitive=action.case_sensitive,
            include_globs=action.include_globs,
            max_results=action.max_results,
        )
        return CoderRepoSearchTextObservation(
            hits=[item.model_dump(mode="json", exclude_none=True) for item in hits],
            returned=len(hits),
            evidence_ref=ref.ref_id,
        )


class CoderRepoReadFileExecutor(
    _RepoContextExecutorMixin,
    ToolExecutor[CoderRepoReadFileAction, CoderRepoReadFileObservation],
):
    def __call__(
        self,
        action: CoderRepoReadFileAction,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> CoderRepoReadFileObservation:
        snippet, ref = self.service.read_file_range(
            action.path,
            start_line=action.start_line,
            max_lines=action.max_lines,
        )
        return CoderRepoReadFileObservation(
            snippet=snippet.model_dump(mode="json", exclude_none=True),
            evidence_ref=ref.ref_id,
        )


class CoderRepoFindFilesTool(ToolDefinition[CoderRepoFindFilesAction, CoderRepoFindFilesObservation]):
    name = "coder_repo_find_files"

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,  # noqa: ARG003
        **params: Any,
    ) -> Sequence["CoderRepoFindFilesTool"]:
        return [
            cls(
                description="Read-only fd-like file discovery over the current scoped repository.",
                action_type=CoderRepoFindFilesAction,
                observation_type=CoderRepoFindFilesObservation,
                executor=CoderRepoFindFilesExecutor(**_bound_params(params)),
                annotations=_read_only_annotations("Coder Repo Find Files"),
            )
        ]


class CoderRepoSearchTextTool(ToolDefinition[CoderRepoSearchTextAction, CoderRepoSearchTextObservation]):
    name = "coder_repo_search_text"

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,  # noqa: ARG003
        **params: Any,
    ) -> Sequence["CoderRepoSearchTextTool"]:
        return [
            cls(
                description="Read-only rg-like text search over the current scoped repository.",
                action_type=CoderRepoSearchTextAction,
                observation_type=CoderRepoSearchTextObservation,
                executor=CoderRepoSearchTextExecutor(**_bound_params(params)),
                annotations=_read_only_annotations("Coder Repo Search Text"),
            )
        ]


class CoderRepoReadFileTool(ToolDefinition[CoderRepoReadFileAction, CoderRepoReadFileObservation]):
    name = "coder_repo_read_file"

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,  # noqa: ARG003
        **params: Any,
    ) -> Sequence["CoderRepoReadFileTool"]:
        return [
            cls(
                description="Read-only bounded file range reader for current scoped repository evidence.",
                action_type=CoderRepoReadFileAction,
                observation_type=CoderRepoReadFileObservation,
                executor=CoderRepoReadFileExecutor(**_bound_params(params)),
                annotations=_read_only_annotations("Coder Repo Read File"),
            )
        ]


def _bound_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "coder_store_root": params["coder_store_root"],
        "repo_root": params["repo_root"],
        "run_id": params["run_id"],
        "scope_paths": list(params.get("scope_paths") or []),
    }


def _read_only_annotations(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def _redact(text: str) -> str:
    redacted = text
    for marker in (*SECRET_MARKERS, "DEEPSEEK_API_KEY", "LLM_API_KEY", "BEGIN RSA"):
        redacted = redacted.replace(marker, "[redacted]")
        redacted = redacted.replace(marker.lower(), "[redacted]")
    return redacted


for _tool in (CoderRepoFindFilesTool, CoderRepoSearchTextTool, CoderRepoReadFileTool):
    register_tool(_tool.name, _tool)


__all__ = [
    "CoderRepoFindFilesAction",
    "CoderRepoFindFilesTool",
    "CoderRepoReadFileAction",
    "CoderRepoReadFileTool",
    "CoderRepoSearchTextAction",
    "CoderRepoSearchTextTool",
]
