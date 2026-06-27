from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from coder_workbench.memory.hybrid_retriever import is_code_like_query


class RetrievalIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    needs_code_fact: bool = False
    needs_current_file_state: bool = False
    needs_external_docs: bool = False
    needs_project_memory: bool = False
    needs_user_notes: bool = False
    needs_prior_run_context: bool = False
    query_is_code_like: bool = False


class ContextRetrievalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_repo_discovery: bool = False
    use_repo_search: bool = False
    use_repo_read: bool = False
    use_rag: bool = False
    rag_is_hint_only: bool = True
    requires_repo_verification: bool = False
    reason: str


class ContextRetrievalRouter:
    def infer_intent(
        self,
        query: str,
        *,
        mode: str = "planning_chat",
        work_item: Any | None = None,
        task_envelope: Any | None = None,
    ) -> RetrievalIntent:
        text = _combined_query(query, work_item=work_item, task_envelope=task_envelope)
        lowered = text.lower()
        code_like = is_code_like_query(text) or _mentions_code_fact(text)
        file_state = _mentions_file_path(text) or any(
            marker in lowered
            for marker in (
                "current implementation",
                "current file",
                "where is",
                "where does",
                "defined",
                "definition",
                "import path",
                "test assert",
                "error string",
            )
        )
        modifies_code = mode == "task_execution" or any(
            marker in lowered
            for marker in (
                "modify",
                "edit",
                "implement",
                "fix",
                "refactor",
                "change code",
                "add test",
                "update code",
            )
        )
        knowledge = any(
            marker in lowered
            for marker in (
                "roadmap",
                "design decision",
                "decision log",
                "why was",
                "why did",
                "what did we decide",
                "project notes",
                "obsidian",
                "prior run",
                "history",
            )
        )
        external_docs = any(
            marker in lowered
            for marker in ("api docs", "sdk docs", "external docs", "documentation", "library usage")
        )
        return RetrievalIntent(
            needs_code_fact=code_like or modifies_code,
            needs_current_file_state=file_state,
            needs_external_docs=external_docs,
            needs_project_memory=knowledge,
            needs_user_notes="notes" in lowered or "obsidian" in lowered,
            needs_prior_run_context="prior run" in lowered or "history" in lowered,
            query_is_code_like=code_like,
        )

    def decide(
        self,
        query: str = "",
        *,
        mode: str = "planning_chat",
        work_item: Any | None = None,
        task_envelope: Any | None = None,
        intent: RetrievalIntent | None = None,
    ) -> ContextRetrievalDecision:
        parsed = intent or self.infer_intent(query, mode=mode, work_item=work_item, task_envelope=task_envelope)
        text = _combined_query(query, work_item=work_item, task_envelope=task_envelope)
        has_path = _mentions_file_path(text)
        repo_needed = (
            parsed.needs_code_fact
            or parsed.needs_current_file_state
            or mode == "task_execution"
        )
        rag_needed = (
            parsed.needs_external_docs
            or parsed.needs_project_memory
            or parsed.needs_user_notes
            or parsed.needs_prior_run_context
        )
        requires_verification = bool(rag_needed and (parsed.query_is_code_like or parsed.needs_code_fact))
        reasons: list[str] = []
        if repo_needed:
            reasons.append("current code facts require native repo evidence")
        if rag_needed:
            reasons.append("knowledge-oriented context may use RAG hints")
        if requires_verification:
            reasons.append("code-like knowledge hints require repo verification")
        if not reasons:
            reasons.append("no retrieval-heavy context required")
        return ContextRetrievalDecision(
            use_repo_discovery=repo_needed,
            use_repo_search=repo_needed and (parsed.query_is_code_like or mode == "task_execution"),
            use_repo_read=repo_needed and has_path,
            use_rag=rag_needed,
            rag_is_hint_only=True,
            requires_repo_verification=requires_verification,
            reason="; ".join(reasons),
        )


def _combined_query(query: str, *, work_item: Any | None, task_envelope: Any | None) -> str:
    parts = [str(query or "")]
    for item in (work_item, task_envelope):
        if item is None:
            continue
        if isinstance(item, dict):
            parts.extend(str(item.get(key) or "") for key in ("task_summary", "summary", "path"))
            continue
        for key in ("task_summary", "summary", "path"):
            value = getattr(item, key, None)
            if value:
                parts.append(str(value))
    return " ".join(part for part in parts if part.strip())


def _mentions_file_path(text: str) -> bool:
    return bool(re.search(r"(?:^|\s)[A-Za-z0-9_.\-/\\]+\.[A-Za-z0-9]{1,8}(?=\s|$|[:),])", text))


def _mentions_code_fact(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"\b(?:class|def|defined|definition|function|method|import|pytest|unittest|traceback|exception)\b", lowered)
        or re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\(", text)
        or re.search(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b", text)
    )


__all__ = [
    "ContextRetrievalDecision",
    "ContextRetrievalRouter",
    "RetrievalIntent",
]
