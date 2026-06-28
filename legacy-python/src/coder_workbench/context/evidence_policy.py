from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceKind(str, Enum):
    REPO_EVIDENCE = "repo_evidence"
    KNOWLEDGE_HINT = "knowledge_hint"
    RUN_EVIDENCE = "run_evidence"


class KnowledgeHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: Literal["hybrid_rag", "memory", "obsidian", "external_doc"]
    title: str
    summary: str
    source_refs: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    requires_repo_verification: bool = True
    evidence_kind: Literal["knowledge_hint"] = "knowledge_hint"


def is_code_like_text(text: str) -> bool:
    return bool(
        re.search(r"[\\/][A-Za-z0-9_.-]+", text)
        or re.search(r"\.[A-Za-z0-9]{1,8}\b", text)
        or re.search(r"\b[a-z]+_[a-z0-9_]+\b", text)
        or re.search(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b", text)
        or re.search(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b", text)
        or re.search(r"\b[A-Z][A-Z0-9_]{2,}\b", text)
        or re.search(r"\b(?:E[A-Z0-9]{2,}|[A-Z]+-\d+|\d{3,})\b", text)
        or re.search(r"\btest_[A-Za-z0-9_]+\b", text)
        or re.search(r"\b(?:class|def|function|method|import|pytest|unittest|traceback|exception)\b", text.lower())
    )


def rag_result_requires_repo_verification(*texts: str | None) -> bool:
    return any(is_code_like_text(text or "") for text in texts)


def code_fact_supported_by_evidence_kind(kind: str) -> bool:
    return kind in {EvidenceKind.REPO_EVIDENCE.value, EvidenceKind.RUN_EVIDENCE.value}


def rag_evidence_metadata(*texts: str | None) -> dict[str, object]:
    return {
        "evidence_kind": EvidenceKind.KNOWLEDGE_HINT.value,
        "requires_repo_verification": rag_result_requires_repo_verification(*texts),
    }


__all__ = [
    "EvidenceKind",
    "KnowledgeHint",
    "code_fact_supported_by_evidence_kind",
    "is_code_like_text",
    "rag_evidence_metadata",
    "rag_result_requires_repo_verification",
]
