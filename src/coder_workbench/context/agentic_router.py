from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from coder_workbench.memory.rag_models import HybridRagRequest
from coder_workbench.memory.retriever import MemoryRetrievalRequest, MemoryRetriever

from .evidence_policy import rag_result_requires_repo_verification
from .repo_context_service import NativeRepoContextService
from .repo_safety import normalize_repo_path
from .router_models import AgenticContextRouterState, RetrievalIntent, RouterMode, RouterSource
from .router_profiles import router_profile_for_mode


class AgenticContextRouter:
    def __init__(
        self,
        *,
        coder_store_root: str | Path,
        repo_root: str | Path,
        run_id: str,
        mode: RouterMode,
        scope_paths: list[str] | None = None,
        memory_store: Any | None = None,
        knowledge_store: Any | None = None,
        hybrid_retriever: Any | None = None,
    ) -> None:
        self.coder_store_root = Path(coder_store_root)
        self.repo_root = Path(repo_root)
        self.run_id = run_id
        self.mode = mode
        self.scope_paths = [normalize_repo_path(scope) for scope in scope_paths or [] if str(scope).strip()]
        self.profile = router_profile_for_mode(mode)
        self.memory_store = memory_store
        self.knowledge_store = knowledge_store
        self.hybrid_retriever = hybrid_retriever

    def route(
        self,
        query: str,
        *,
        work_item: Any | None = None,
        task_envelope: Any | None = None,
    ) -> AgenticContextRouterState:
        state = AgenticContextRouterState(
            mode=self.mode,
            query=str(query or ""),
        )
        state.intent = self.classify_intent(query, work_item=work_item, task_envelope=task_envelope)
        state.selected_source = self.choose_initial_source(state.intent)
        state.initial_source = state.selected_source
        state.requires_repo_verification = (
            self.profile.repo_verification_required_for_code_claims
            and (state.intent.needs_code_fact or state.intent.query_is_code_like)
        )
        self._trace(state, "classify_intent", state.selected_source, state.intent.reason)

        while state.iterations < state.max_iterations and state.selected_source != "none":
            state.iterations += 1
            before_counts = self._context_counts(state)
            self.retrieve_from_selected_source(state, work_item=work_item, task_envelope=task_envelope)
            state.retrieval_grade = self.grade_retrieved_context(state)
            self._trace(
                state,
                "retrieve",
                state.selected_source,
                f"grade={state.retrieval_grade}",
                before=before_counts,
                after=self._context_counts(state),
            )
            if state.retrieval_grade in {"sufficient", "partial"}:
                break
            rewritten = self.rewrite_query(state)
            if rewritten and rewritten != state.query and rewritten != state.rewritten_query:
                state.rewritten_query = rewritten
                self._trace(state, "rewrite_query", state.selected_source, rewritten)
            next_source = self.maybe_switch_source(state)
            if next_source == state.selected_source:
                break
            state.selected_source = next_source
            self._trace(state, "switch_source", state.selected_source, "weak context switched retrieval source")

        self.verify_code_fact(state, work_item=work_item, task_envelope=task_envelope)
        if state.retrieval_grade == "none":
            state.retrieval_grade = self.grade_retrieved_context(state)
        state.stop_reason = state.stop_reason or _stop_reason(state)
        return state

    def classify_intent(
        self,
        query: str,
        *,
        work_item: Any | None = None,
        task_envelope: Any | None = None,
    ) -> RetrievalIntent:
        text = _combined_query(query, work_item=work_item, task_envelope=task_envelope)
        lowered = text.lower()
        has_path = _extract_repo_file_path(text) is not None
        code_like = _query_is_code_like(text)
        modifies_code = self.mode == "task_execution" or any(
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
                "patch",
            )
        )
        runtime = self.mode == "workflow_supervisor" or any(
            marker in lowered
            for marker in (
                "test output",
                "verification",
                "execution_result",
                "runtime",
                "log",
                "diff",
                "blocked",
                "passed",
                "failed",
            )
        )
        external_docs = any(
            marker in lowered
            for marker in ("api docs", "sdk docs", "external docs", "documentation", "library usage", "provider api")
        )
        project_memory = any(
            marker in lowered
            for marker in (
                "roadmap",
                "design decision",
                "decision log",
                "why was",
                "why did",
                "what did we decide",
                "project notes",
                "architecture",
            )
        )
        user_notes = "obsidian" in lowered or "user notes" in lowered or "notes" in lowered
        prior_run = "prior run" in lowered or "previous run" in lowered or "history" in lowered or "historical blocker" in lowered
        needs_code = code_like or modifies_code
        if modifies_code:
            intent_type = "code_modification"
        elif needs_code:
            intent_type = "code_fact"
        elif runtime:
            intent_type = "runtime_fact"
        elif external_docs:
            intent_type = "external_docs"
        elif user_notes:
            intent_type = "user_notes"
        elif prior_run:
            intent_type = "prior_run_context"
        elif project_memory:
            intent_type = "project_memory"
        elif "plan" in lowered or "planning" in lowered:
            intent_type = "planning"
        else:
            intent_type = "ambiguous"
        return RetrievalIntent(
            intent_type=intent_type,
            needs_code_fact=needs_code,
            needs_current_file_state=has_path or any(marker in lowered for marker in ("current implementation", "current file", "where is", "defined")),
            needs_runtime_evidence=runtime,
            needs_external_docs=external_docs,
            needs_project_memory=project_memory,
            needs_user_notes=user_notes,
            needs_prior_run_context=prior_run,
            query_is_code_like=code_like,
            confidence="high" if intent_type != "ambiguous" else "medium",
            reason=f"intent={intent_type}; mode={self.mode}; code_like={code_like}",
        )

    def choose_initial_source(self, intent: RetrievalIntent) -> RouterSource:
        if self.mode == "workflow_supervisor" and "run_evidence" in self.profile.allowed_sources:
            return "run_evidence"
        if self.mode == "task_execution":
            return "native_repo"
        if intent.needs_code_fact or intent.needs_current_file_state:
            return "native_repo"
        if (
            self.profile.rag_first_allowed
            and (intent.needs_external_docs or intent.needs_project_memory or intent.needs_user_notes or intent.needs_prior_run_context)
            and "hybrid_rag" in self.profile.allowed_sources
        ):
            return "hybrid_rag"
        if "direct_memory" in self.profile.allowed_sources and (intent.intent_type in {"planning", "ambiguous"}):
            return "direct_memory"
        return self.profile.default_sources[0] if self.profile.default_sources else "none"

    def retrieve_from_selected_source(
        self,
        state: AgenticContextRouterState,
        *,
        work_item: Any | None,
        task_envelope: Any | None,
    ) -> None:
        if state.selected_source == "native_repo":
            self._retrieve_native_repo(state, work_item=work_item, task_envelope=task_envelope)
        elif state.selected_source == "run_evidence":
            self._retrieve_run_evidence(state, work_item=work_item, task_envelope=task_envelope)
        elif state.selected_source == "direct_memory":
            self._retrieve_direct_memory(state)
        elif state.selected_source == "hybrid_rag":
            self._retrieve_hybrid_rag(state)

    def grade_retrieved_context(self, state: AgenticContextRouterState) -> str:
        intent = state.intent or RetrievalIntent()
        if intent.needs_code_fact or intent.needs_current_file_state:
            if _has_supporting_repo_code_evidence(state.repo_evidence):
                return "sufficient"
            if _has_any_repo_observation(state.repo_evidence) or state.knowledge_hints:
                return "partial"
            return "weak"
        if intent.needs_runtime_evidence:
            if state.run_evidence:
                return "sufficient"
            if state.repo_evidence or state.knowledge_hints:
                return "partial"
            return "weak"
        if intent.needs_external_docs or intent.needs_project_memory or intent.needs_user_notes or intent.needs_prior_run_context:
            if state.knowledge_hints or state.memory_cards:
                return "sufficient"
            return "weak"
        if state.repo_evidence or state.run_evidence or state.knowledge_hints or state.memory_cards:
            return "partial"
        return "none"

    def rewrite_query(self, state: AgenticContextRouterState) -> str | None:
        base = state.rewritten_query or state.query
        if state.selected_source == "native_repo":
            file_path = _extract_repo_file_path(base)
            if file_path:
                return Path(file_path).stem
            symbol = _extract_symbol(base)
            if symbol:
                return _split_identifier(symbol)
            return _strip_query(base)
        if state.selected_source == "hybrid_rag":
            terms = _strip_query(base)
            intent = state.intent.intent_type if state.intent else "ambiguous"
            if intent in {"project_memory", "prior_run_context", "planning"}:
                return f"{terms} decision roadmap history".strip()
            if intent == "external_docs":
                return f"{terms} docs api usage".strip()
        return None

    def maybe_switch_source(self, state: AgenticContextRouterState) -> RouterSource:
        intent = state.intent or RetrievalIntent()
        if state.retrieval_grade not in {"weak", "none"}:
            return state.selected_source
        if state.selected_source == "run_evidence":
            if intent.needs_code_fact and "native_repo" in self.profile.allowed_sources:
                return "native_repo"
            if (intent.needs_project_memory or intent.needs_prior_run_context) and "hybrid_rag" in self.profile.allowed_sources:
                return "hybrid_rag"
        if state.selected_source == "native_repo":
            if (
                intent.needs_external_docs
                or intent.needs_project_memory
                or intent.needs_user_notes
                or intent.needs_prior_run_context
            ) and "hybrid_rag" in self.profile.allowed_sources:
                return "hybrid_rag"
        if state.selected_source == "direct_memory":
            if "hybrid_rag" in self.profile.allowed_sources:
                return "hybrid_rag"
            if "native_repo" in self.profile.allowed_sources:
                return "native_repo"
        if state.selected_source == "hybrid_rag" and (intent.needs_code_fact or intent.query_is_code_like):
            if "native_repo" in self.profile.allowed_sources:
                return "native_repo"
        return state.selected_source

    def verify_code_fact(
        self,
        state: AgenticContextRouterState,
        *,
        work_item: Any | None,
        task_envelope: Any | None,
    ) -> None:
        intent = state.intent or RetrievalIntent()
        hint_requires_verification = any(
            hint.get("requires_repo_verification")
            or rag_result_requires_repo_verification(hint.get("title"), hint.get("summary"), hint.get("text_preview"))
            for hint in state.knowledge_hints
        )
        if not (
            self.profile.repo_verification_required_for_code_claims
            and (intent.needs_code_fact or intent.query_is_code_like or hint_requires_verification)
        ):
            return
        state.requires_repo_verification = True
        if state.repo_evidence:
            return
        previous = state.selected_source
        state.selected_source = "native_repo"
        self._trace(state, "verify_code_fact", "native_repo", "verifying code-like hints with repo evidence")
        self._retrieve_native_repo(state, work_item=work_item, task_envelope=task_envelope)
        state.retrieval_grade = self.grade_retrieved_context(state)
        state.selected_source = previous

    def _retrieve_native_repo(
        self,
        state: AgenticContextRouterState,
        *,
        work_item: Any | None,
        task_envelope: Any | None,
    ) -> None:
        if not self.repo_root.exists():
            return
        query = state.rewritten_query or _combined_query(state.query, work_item=work_item, task_envelope=task_envelope)
        file_path = _extract_repo_file_path(query)
        search_pattern = _extract_repo_search_pattern(query, file_path=file_path)
        try:
            service = NativeRepoContextService(
                coder_store_root=self.coder_store_root,
                repo_root=self.repo_root,
                run_id=self.run_id,
                scope_paths=self.scope_paths,
            )
            if file_path:
                files, ref = service.find_files(query=file_path, max_results=50)
            else:
                files, ref = service.find_files(query=None, max_results=50)
            self._add_ref(state.repo_evidence_refs, ref.ref_id)
            self._add_evidence(
                state.repo_evidence,
                {
                    "ref_id": ref.ref_id,
                    "kind": ref.kind,
                    "evidence_kind": "repo_evidence",
                    "summary": ref.summary,
                    "source_refs": [item.path for item in files[:10]],
                },
            )
            if search_pattern:
                hits, ref = service.search_text(search_pattern, max_results=30)
                self._add_ref(state.repo_evidence_refs, ref.ref_id)
                for hit in hits[:10]:
                    self._add_evidence(
                        state.repo_evidence,
                        {
                            "evidence_ref": ref.ref_id,
                            "kind": "repo_text_search",
                            "evidence_kind": "repo_evidence",
                            "path": hit.path,
                            "line": hit.line,
                            "summary": hit.text,
                        },
                    )
                if not hits:
                    self._add_evidence(
                        state.repo_evidence,
                        {
                            "ref_id": ref.ref_id,
                            "kind": ref.kind,
                            "evidence_kind": "repo_evidence",
                            "summary": ref.summary,
                        },
                    )
            if file_path:
                snippet, ref = service.read_file_range(file_path, max_lines=80)
                self._add_ref(state.repo_evidence_refs, ref.ref_id)
                self._add_evidence(
                    state.repo_evidence,
                    {
                        "evidence_ref": ref.ref_id,
                        "kind": "repo_read",
                        "evidence_kind": "repo_evidence",
                        "path": snippet.path,
                        "start_line": snippet.start_line,
                        "end_line": snippet.end_line,
                        "text": snippet.text,
                        "truncated": snippet.truncated,
                    },
                )
        except Exception as exc:
            self._trace(state, "native_repo_error", "native_repo", str(exc))

    def _retrieve_run_evidence(
        self,
        state: AgenticContextRouterState,
        *,
        work_item: Any | None,
        task_envelope: Any | None,
    ) -> None:
        records: list[dict[str, Any]] = []
        refs: list[str] = []
        for source in (work_item, task_envelope):
            data = _model_or_dict(source)
            if not data:
                continue
            for key in (
                "execution_result",
                "execution_results",
                "round_summary",
                "verification_summary",
                "verification_summaries",
                "changed_files_summary",
                "blocked_reasons",
                "run_memory_snapshot",
                "planner_task_state",
                "planner_order",
            ):
                value = data.get(key)
                if value not in (None, "", [], {}):
                    records.append(
                        {
                            "id": f"{key}-{len(records) + 1}",
                            "source": key,
                            "evidence_kind": "run_evidence",
                            "summary": _compact_summary(value),
                        }
                    )
            refs.extend(_string_list(data.get("evidence_refs")))
            refs.extend(_string_list(data.get("diff_refs")))
            refs.extend(_string_list(data.get("log_refs")))
            refs.extend(_string_list(data.get("native_event_refs")))
        for record in records[:20]:
            self._add_evidence(state.run_evidence, record)
        for ref in refs:
            self._add_ref(state.run_evidence_refs, ref)

    def _retrieve_direct_memory(self, state: AgenticContextRouterState) -> None:
        if self.memory_store is None or self.knowledge_store is None:
            return
        try:
            cards = MemoryRetriever(
                memory_store=self.memory_store,
                knowledge_store=self.knowledge_store,
            ).retrieve(
                MemoryRetrievalRequest(
                    role=self.mode,
                    requested_context=_requested_context_for_mode(self.mode),
                    query=state.rewritten_query or state.query,
                    run_id=self.run_id,
                    scope_paths=self.scope_paths,
                )
            )
        except Exception as exc:
            self._trace(state, "direct_memory_error", "direct_memory", str(exc))
            return
        for card in cards[:8]:
            dumped = card.model_dump(mode="json", exclude_none=True)
            if dumped.get("card_type") == "knowledge_chunk":
                self._add_evidence(state.knowledge_hints, _knowledge_hint_from_card(dumped))
                self._add_ref(state.knowledge_refs, str(dumped.get("id") or ""))
            else:
                self._add_evidence(state.memory_cards, dumped)
                self._add_ref(state.memory_refs, str(dumped.get("id") or ""))

    def _retrieve_hybrid_rag(self, state: AgenticContextRouterState) -> None:
        if self.hybrid_retriever is None:
            return
        try:
            results = self.hybrid_retriever.retrieve(
                HybridRagRequest(
                    role=self.mode,
                    requested_context=_requested_context_for_mode(self.mode),
                    query=state.rewritten_query or state.query,
                    run_id=self.run_id,
                    scope_paths=self.scope_paths,
                    top_k=6,
                    include_content=False,
                )
            )
        except Exception as exc:
            self._trace(state, "hybrid_rag_error", "hybrid_rag", str(exc))
            return
        for result in results:
            dumped = result.model_dump(mode="json", exclude_none=True)
            self._add_evidence(state.knowledge_hints, dumped)
            self._add_ref(state.knowledge_refs, str(dumped.get("id") or ""))

    def _add_ref(self, refs: list[str], ref: str) -> None:
        text = str(ref or "").strip()
        if text and text not in refs:
            refs.append(text)

    def _add_evidence(self, records: list[dict[str, Any]], record: dict[str, Any]) -> None:
        key = repr(sorted(record.items()))
        if all(repr(sorted(existing.items())) != key for existing in records):
            records.append(record)

    def _trace(self, state: AgenticContextRouterState, step: str, source: RouterSource, reason: str, **extra: Any) -> None:
        item = {
            "step": step,
            "source": source,
            "reason": reason,
            "iteration": state.iterations,
        }
        item.update({key: value for key, value in extra.items() if value not in (None, "", [], {})})
        state.route_trace.append(item)

    def _context_counts(self, state: AgenticContextRouterState) -> dict[str, int]:
        return {
            "repo_evidence": len(state.repo_evidence),
            "run_evidence": len(state.run_evidence),
            "knowledge_hints": len(state.knowledge_hints),
            "memory_cards": len(state.memory_cards),
        }


def _requested_context_for_mode(mode: str) -> str:
    return {
        "planning_chat": "assistant_message",
        "workflow_supervisor": "workflow_supervision",
        "task_execution": "execution_prompt",
    }[mode]


def _combined_query(query: str, *, work_item: Any | None, task_envelope: Any | None) -> str:
    parts = [str(query or "")]
    for item in (work_item, task_envelope):
        data = _model_or_dict(item)
        if not data:
            continue
        for key in ("task_summary", "summary", "path", "round_goal", "request", "goal"):
            value = data.get(key)
            if value:
                parts.append(str(value))
        for key in ("constraints", "success_criteria", "target_files_or_outputs"):
            value = data.get(key)
            if isinstance(value, list):
                parts.extend(str(entry) for entry in value[:5] if str(entry).strip())
    return " ".join(part for part in parts if part.strip())


def _model_or_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return {}


def _query_is_code_like(text: str) -> bool:
    lowered = text.lower()
    return bool(
        _extract_repo_file_path(text)
        or re.search(r"\b(?:class|def|defined|definition|function|method|import|pytest|unittest|traceback|exception)\b", lowered)
        or re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\(", text)
        or re.search(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b", text)
        or re.search(r"\btest_[A-Za-z0-9_]+\b", text)
    )


def _extract_repo_file_path(text: str) -> str | None:
    match = re.search(r"(?:^|\s)([A-Za-z0-9_.\-/\\]+\.[A-Za-z0-9]{1,8})(?=\s|$|[:),.])", text)
    if not match:
        return None
    value = normalize_repo_path(match.group(1).strip("`'\".,:;)("))
    return value or None


def _extract_repo_search_pattern(text: str, *, file_path: str | None) -> str | None:
    quoted = re.search(r"['\"]([^'\"]{2,120})['\"]", text)
    if quoted:
        return quoted.group(1)
    symbol = _extract_symbol(text)
    if symbol:
        return symbol
    if file_path:
        stem = Path(file_path).stem
        return stem if stem else None
    return None


def _extract_symbol(text: str) -> str | None:
    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,80}\b", text)
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "what",
        "where",
        "does",
        "this",
        "that",
        "current",
        "implementation",
        "implement",
        "modify",
        "update",
        "work",
        "item",
        "defined",
    }
    for token in tokens:
        if token.lower() in stop_words:
            continue
        if "_" in token or any(char.isupper() for char in token[1:]) or token.isupper() or token.startswith("test"):
            return token
    return None


def _strip_query(text: str) -> str:
    return " ".join(re.findall(r"[A-Za-z0-9_./-]+", text))[:300]


def _split_identifier(text: str) -> str:
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    split = split.replace("_", " ")
    return " ".join(part for part in split.split() if part)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _compact_summary(value: Any) -> str:
    text = str(value)
    if len(text) <= 800:
        return text
    return text[:797].rstrip() + "..."


def _knowledge_hint_from_card(card: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            **card,
            "evidence_kind": "knowledge_hint",
            "requires_repo_verification": rag_result_requires_repo_verification(
                card.get("title"),
                card.get("summary"),
            ),
        }.items()
        if value not in (None, "", [])
    }


def _stop_reason(state: AgenticContextRouterState) -> str:
    if state.iterations >= state.max_iterations:
        return "max_iterations"
    if state.retrieval_grade in {"sufficient", "partial"}:
        return f"context_{state.retrieval_grade}"
    return "no_more_routes"


def _has_supporting_repo_code_evidence(records: list[dict[str, Any]]) -> bool:
    for record in records:
        kind = str(record.get("kind") or "")
        summary = str(record.get("summary") or "")
        if kind == "repo_read" or record.get("text"):
            return True
        if kind == "repo_text_search" and not summary.lower().startswith("found 0 repo text hits"):
            return True
        if record.get("path") and record.get("line"):
            return True
    return False


def _has_any_repo_observation(records: list[dict[str, Any]]) -> bool:
    for record in records:
        summary = str(record.get("summary") or "").lower()
        if summary.startswith("found 0 repo files") or summary.startswith("found 0 repo text hits"):
            continue
        if record.get("source_refs") or record.get("path") or record.get("text"):
            return True
    return False


__all__ = ["AgenticContextRouter"]
