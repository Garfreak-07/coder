from __future__ import annotations

import math
import re
from typing import Any

from coder_workbench.memory.bm25_index import BM25Index
from coder_workbench.memory.chroma_index import ChromaVectorIndex
from coder_workbench.memory.models import (
    AgentMemoryRole,
    KnowledgeChunk,
    MemoryAllowedContext,
    MemoryPurpose,
    MemoryRecord,
    MemoryScope,
    MemorySourceRef,
    SECRET_MARKERS,
    memory_has_expired,
)
from coder_workbench.memory.policy import AgentMemoryPolicy, policy_for_role
from coder_workbench.memory.rag_models import HybridRagRequest, HybridRagResult, RetrievalHit
from coder_workbench.memory.retriever import MemoryRetrievalRequest, MemoryRetriever
from coder_workbench.memory.store import AgentScopedMemoryStore, KnowledgeStore


class HybridRagRetriever:
    def __init__(
        self,
        *,
        memory_store: AgentScopedMemoryStore,
        knowledge_store: KnowledgeStore,
        bm25_index: BM25Index | None = None,
        chroma_index: ChromaVectorIndex | None = None,
        policies: dict[AgentMemoryRole, AgentMemoryPolicy] | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.knowledge_store = knowledge_store
        self.bm25_index = bm25_index
        self.chroma_index = chroma_index
        self.policies = policies or {}

    def retrieve(self, request: HybridRagRequest | dict[str, Any]) -> list[HybridRagResult]:
        parsed = request if isinstance(request, HybridRagRequest) else HybridRagRequest.model_validate(request)
        policy = self.policies.get(parsed.role) or policy_for_role(parsed.role)
        if parsed.requested_context not in policy.allowed_contexts:
            return []

        dense_hits = self._dense_hits(parsed)
        bm25_hits = self._bm25_hits(parsed)
        if not dense_hits and not bm25_hits:
            return self._fallback_results(parsed, policy)

        dense_weight, bm25_weight = _weights_for_request(parsed)
        fused = weighted_rrf(
            dense_hits,
            bm25_hits,
            dense_weight=dense_weight,
            bm25_weight=bm25_weight,
        )
        dense_by_id = {hit.id: hit for hit in dense_hits}
        bm25_by_id = {hit.id: hit for hit in bm25_hits}
        item_type_by_id = {hit.id: hit.item_type for hit in [*bm25_hits, *dense_hits]}
        chunks = {chunk.chunk_id: chunk for chunk in self.knowledge_store.list_chunks()}
        records = {record.id: record for record in self.memory_store.list_records(status="active")}

        selected: list[HybridRagResult] = []
        used_tokens = 0
        max_results = min(parsed.top_k, policy.max_records)
        for item_id, fusion_score in fused:
            item_type = item_type_by_id.get(item_id)
            if item_type == "knowledge_chunk":
                item = chunks.get(item_id)
                if item is None or not _chunk_allowed(item, parsed, policy):
                    continue
                result = _result_from_chunk(
                    item,
                    request=parsed,
                    dense_hit=dense_by_id.get(item_id),
                    bm25_hit=bm25_by_id.get(item_id),
                    fusion_score=fusion_score,
                    remaining_preview_chars=_remaining_preview_chars(parsed, selected),
                )
            elif item_type == "memory_record":
                item = records.get(item_id)
                if item is None or not _record_allowed(item, parsed, policy):
                    continue
                result = _result_from_record(
                    item,
                    request=parsed,
                    dense_hit=dense_by_id.get(item_id),
                    bm25_hit=bm25_by_id.get(item_id),
                    fusion_score=fusion_score,
                    remaining_preview_chars=_remaining_preview_chars(parsed, selected),
                )
            else:
                continue
            cost = max(1, result.token_estimate)
            if used_tokens + cost > policy.max_tokens:
                continue
            selected.append(result)
            used_tokens += cost
            if len(selected) >= max_results:
                break
        return selected

    def _dense_hits(self, request: HybridRagRequest) -> list[RetrievalHit]:
        if self.chroma_index is None:
            return []
        try:
            search = self.chroma_index.search(request.query, top_k=request.dense_k)
        except Exception:
            return []
        return [
            RetrievalHit(
                id=hit.id,
                item_type="knowledge_chunk",
                rank=hit.rank,
                score=hit.score,
                channel="dense",
            )
            for hit in search
        ]

    def _bm25_hits(self, request: HybridRagRequest) -> list[RetrievalHit]:
        if self.bm25_index is None:
            return []
        try:
            search = self.bm25_index.search(request.query, top_k=request.bm25_k)
        except Exception:
            return []
        return [
            RetrievalHit(
                id=hit.id,
                item_type=hit.item_type,
                rank=hit.rank,
                score=hit.score,
                channel="bm25",
            )
            for hit in search
        ]

    def _fallback_results(
        self,
        request: HybridRagRequest,
        policy: AgentMemoryPolicy,
    ) -> list[HybridRagResult]:
        cards = MemoryRetriever(
            memory_store=self.memory_store,
            knowledge_store=self.knowledge_store,
            policies=self.policies,
        ).retrieve(
            MemoryRetrievalRequest(
                role=request.role,
                query=request.query,
                project_id=request.project_id,
                session_id=request.session_id,
                run_id=request.run_id,
                scope_paths=request.scope_paths,
                tags=request.tags,
                requested_context=request.requested_context,
            )
        )
        results: list[HybridRagResult] = []
        for card in cards[: min(request.top_k, policy.max_records)]:
            results.append(
                HybridRagResult(
                    id=card.id,
                    item_type=card.card_type,
                    title=card.title,
                    summary=card.summary,
                    scope=card.scope,
                    purpose=card.purpose,
                    tags=card.tags,
                    source_refs=card.source_refs,
                    evidence_refs=card.evidence_refs,
                    fusion_score=card.score,
                    token_estimate=card.token_estimate,
                    requires_repo_verification=_rag_result_requires_repo_verification(
                        request.query,
                        card.title,
                        card.summary,
                    ),
                    metadata={"fallback": "memory_retriever"},
                )
            )
        return results


def weighted_rrf(
    dense_hits: list[RetrievalHit],
    bm25_hits: list[RetrievalHit],
    *,
    dense_weight: float,
    bm25_weight: float,
    c: int = 60,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for hit in dense_hits:
        scores[hit.id] = scores.get(hit.id, 0.0) + dense_weight / (hit.rank + c)
    for hit in bm25_hits:
        scores[hit.id] = scores.get(hit.id, 0.0) + bm25_weight / (hit.rank + c)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def is_code_like_query(query: str) -> bool:
    return bool(
        re.search(r"[\\/][A-Za-z0-9_.-]+", query)
        or re.search(r"\.[A-Za-z0-9]{1,8}\b", query)
        or re.search(r"\b[a-z]+_[a-z0-9_]+\b", query)
        or re.search(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b", query)
        or re.search(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b", query)
        or re.search(r"\b[A-Z][A-Z0-9_]{2,}\b", query)
        or re.search(r"\b(?:E[A-Z0-9]{2,}|[A-Z]+-\d+|\d{3,})\b", query)
        or re.search(r"\btest_[A-Za-z0-9_]+\b", query)
    )


def _weights_for_request(request: HybridRagRequest) -> tuple[float, float]:
    default_dense, default_bm25 = (0.45, 0.55) if is_code_like_query(request.query) else (0.60, 0.40)
    return (
        default_dense if request.dense_weight is None else request.dense_weight,
        default_bm25 if request.bm25_weight is None else request.bm25_weight,
    )


def _record_allowed(record: MemoryRecord, request: HybridRagRequest, policy: AgentMemoryPolicy) -> bool:
    if record.status != "active" or memory_has_expired(record):
        return False
    if record.scope not in policy.allowed_scopes:
        return False
    if not set(record.purpose).issubset(set(policy.allowed_purposes)):
        return False
    if request.role not in record.acl.allowed_agents:
        return False
    if request.requested_context not in record.acl.allowed_contexts:
        return False
    if record.acl.sensitivity == "secret":
        return False
    if not _scope_identity_allowed(record.project_id, request.project_id):
        return False
    if not _scope_identity_allowed(record.session_id, request.session_id):
        return False
    if not _scope_identity_allowed(record.run_id, request.run_id):
        return False
    if request.role == "task_execution" and (record.scope == "user" or "persona_style" in record.purpose):
        return False
    if request.role == "workflow_supervisor" and "persona_style" in record.purpose:
        return False
    return True


def _chunk_allowed(chunk: KnowledgeChunk, request: HybridRagRequest, policy: AgentMemoryPolicy) -> bool:
    if "knowledge_source" not in policy.allowed_scopes:
        return False
    if not set(chunk.purpose).issubset(set(policy.allowed_purposes)):
        return False
    if request.role not in chunk.acl.allowed_agents:
        return False
    if request.requested_context not in chunk.acl.allowed_contexts:
        return False
    if chunk.sensitivity == "secret" or chunk.acl.sensitivity == "secret":
        return False
    if request.role == "task_execution" and "persona_style" in chunk.purpose:
        return False
    if request.role == "workflow_supervisor" and "persona_style" in chunk.purpose:
        return False
    return True


def _result_from_chunk(
    chunk: KnowledgeChunk,
    *,
    request: HybridRagRequest,
    dense_hit: RetrievalHit | None,
    bm25_hit: RetrievalHit | None,
    fusion_score: float,
    remaining_preview_chars: int,
) -> HybridRagResult:
    token_estimate = _token_estimate(chunk.token_estimate, chunk.title, chunk.summary)
    preview = _preview(chunk.text, request=request, remaining_chars=remaining_preview_chars)
    return HybridRagResult(
        id=chunk.chunk_id,
        item_type="knowledge_chunk",
        title=chunk.title,
        summary=chunk.summary,
        text_preview=preview,
        scope="knowledge_source",
        purpose=chunk.purpose,
        tags=chunk.tags,
        source_refs=[
            MemorySourceRef(
                kind="external",
                ref=chunk.source_id,
                title=chunk.title,
                content_hash=chunk.content_hash,
            )
        ],
        evidence_refs=[],
        dense_rank=dense_hit.rank if dense_hit else None,
        bm25_rank=bm25_hit.rank if bm25_hit else None,
        dense_score=dense_hit.score if dense_hit else None,
        bm25_score=bm25_hit.score if bm25_hit else None,
        fusion_score=round(fusion_score, 8),
        token_estimate=token_estimate,
        requires_repo_verification=_rag_result_requires_repo_verification(
            request.query,
            chunk.title,
            chunk.summary,
            preview,
        ),
        metadata={"source_id": chunk.source_id, "content_hash": chunk.content_hash},
    )


def _result_from_record(
    record: MemoryRecord,
    *,
    request: HybridRagRequest,
    dense_hit: RetrievalHit | None,
    bm25_hit: RetrievalHit | None,
    fusion_score: float,
    remaining_preview_chars: int,
) -> HybridRagResult:
    token_estimate = _token_estimate(record.token_estimate, record.title, record.summary)
    preview = _preview(record.content or "", request=request, remaining_chars=remaining_preview_chars)
    return HybridRagResult(
        id=record.id,
        item_type="memory_record",
        title=record.title,
        summary=record.summary,
        text_preview=preview,
        scope=record.scope,
        purpose=record.purpose,
        tags=record.tags,
        source_refs=record.source_refs,
        evidence_refs=record.evidence_refs,
        dense_rank=dense_hit.rank if dense_hit else None,
        bm25_rank=bm25_hit.rank if bm25_hit else None,
        dense_score=dense_hit.score if dense_hit else None,
        bm25_score=bm25_hit.score if bm25_hit else None,
        fusion_score=round(fusion_score, 8),
        token_estimate=token_estimate,
        requires_repo_verification=_rag_result_requires_repo_verification(
            request.query,
            record.title,
            record.summary,
            preview,
        ),
        metadata={"project_id": record.project_id, "session_id": record.session_id, "run_id": record.run_id},
    )


def _preview(text: str, *, request: HybridRagRequest, remaining_chars: int) -> str | None:
    if not request.include_content:
        return None
    if remaining_chars <= 0:
        return None
    if _unsafe_preview_text(text):
        return None
    limit = min(request.content_preview_chars, remaining_chars)
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    if limit <= 3:
        return compact[:limit]
    return compact[: limit - 3].rstrip() + "..."


def _unsafe_preview_text(text: str) -> bool:
    lowered = text.lower()
    forbidden = (
        *SECRET_MARKERS,
        "raw prompt",
        "raw model output",
        "chain-of-thought",
        "diff --git",
        "begin rsa",
    )
    return any(marker in lowered for marker in forbidden)


def _remaining_preview_chars(request: HybridRagRequest, selected: list[HybridRagResult]) -> int:
    if not request.include_content:
        return 0
    total_limit = min(4000, request.content_preview_chars * max(1, request.top_k))
    used = sum(len(item.text_preview or "") for item in selected)
    return max(0, total_limit - used)


def _token_estimate(value: int, *texts: str) -> int:
    if value > 0:
        return value
    chars = sum(len(text) for text in texts)
    return max(1, math.ceil(chars / 4))


def _rag_result_requires_repo_verification(*texts: str | None) -> bool:
    return any(is_code_like_query(text or "") for text in texts)


def _scope_identity_allowed(record_value: str | None, request_value: str | None) -> bool:
    return not record_value or not request_value or record_value == request_value
