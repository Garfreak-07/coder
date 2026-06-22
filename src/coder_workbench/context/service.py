from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coder_workbench.agent_graph.cache import GraphRunCache
from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem
from coder_workbench.coding import build_coding_context_packet
from coder_workbench.context.budget import ContextBudget, context_compaction_enabled
from coder_workbench.context.compaction import CompactionResult, ContextCompactor
from coder_workbench.context.external_refs import ContextExternalRefStore
from coder_workbench.extensions import ExtensionRouter
from coder_workbench.skills import (
    ContextPacketV2,
    SkillIndex,
    SkillRouteDecision,
    TokenLedgerEntry,
    estimate_tokens,
    load_selected_skill_contexts,
)


@dataclass(frozen=True)
class AgentContextBuildResult:
    envelope: AgentTaskEnvelope
    skill_route: SkillRouteDecision
    context_packet: ContextPacketV2
    token_ledger_entry: TokenLedgerEntry
    coding_context_packet: Any
    compact_coding_context_packet: dict[str, Any] | None = None
    compaction_result: CompactionResult | None = None


class ContextService:
    def build_for_work_item(
        self,
        *,
        cache: GraphRunCache,
        item: WorkItem,
        planner_order_ref: str,
        upstream_refs: list[str],
        user_request: str,
        role: str,
        skill_index: SkillIndex,
        skill_store_root: Path,
        run_id: str,
        repo_root: str,
        repo_intelligence: dict[str, Any],
        artifact_type: str,
        context_budget: ContextBudget | None = None,
        enable_context_compaction: bool | None = None,
    ) -> AgentContextBuildResult:
        route = ExtensionRouter(skill_index).route_skills(
            user_request=user_request,
            work_item=item,
            role=role,
        )
        selected_context = load_selected_skill_contexts(
            skill_store_root=skill_store_root,
            decision=route,
            skill_index=skill_index.skills,
            task_summary=item.task_summary,
        )
        route = route.model_copy(
            update={
                "estimated_skill_tokens": sum(context.estimated_tokens for context in selected_context),
                "loaded_skill_refs": [context.ref for context in selected_context],
            }
        )
        route_payload = route.model_dump(mode="json")
        route_payload["selected_skill_context"] = [
            context.model_dump(mode="json")
            for context in selected_context
        ]
        envelope = cache.create_agent_task(
            item,
            planner_order_ref=planner_order_ref,
            upstream_refs=upstream_refs,
            skill_route=route_payload,
        )
        coding_packet = build_coding_context_packet(
            repo_root,
            envelope=envelope,
            repo_index=repo_intelligence.get("repo_index"),
            symbol_index=repo_intelligence.get("symbol_index"),
            command_discovery=repo_intelligence.get("command_discovery"),
            risk_map=repo_intelligence.get("risk_map"),
            upstream_refs=upstream_refs,
            selected_skills=route_payload["selected_skill_context"],
        )
        coding_packet_payload = coding_packet.model_dump(mode="json")
        compaction_result = None
        should_compact = (
            bool(enable_context_compaction)
            if enable_context_compaction is not None
            else context_compaction_enabled()
        )
        if should_compact:
            ref_store = ContextExternalRefStore({})
            compaction_result = ContextCompactor(context_budget or ContextBudget()).compact(
                coding_packet_payload,
                run_id=run_id,
                work_item_id=item.work_item_id,
                store=ref_store,
            )
            coding_packet_payload = compaction_result.packet
            if ref_store.backing:
                cache.record_context_external_refs(ref_store.backing)
            if compaction_result.externalized_refs or compaction_result.warnings:
                cache.record_context_compaction(
                    item.work_item_id,
                    {
                        "work_item_id": item.work_item_id,
                        "token_estimate_before": compaction_result.token_estimate_before,
                        "token_estimate_after": compaction_result.token_estimate_after,
                        "externalized_refs": compaction_result.externalized_refs,
                        "summaries": compaction_result.summaries,
                        "warnings": compaction_result.warnings,
                    },
                )
        envelope = envelope.model_copy(
            update={"coding_context_packet": coding_packet_payload}
        )
        cache.agent_tasks[item.work_item_id] = envelope
        context_packet = _context_packet_v2(
            envelope=envelope,
            route=route,
            skill_index=skill_index,
            artifact_type=artifact_type,
        )
        ledger_entry = _token_ledger_entry(
            run_id=run_id,
            round_number=cache.round,
            envelope=envelope,
            route=route,
            skill_index=skill_index,
            packet=context_packet,
            artifact_type=context_packet.artifact_type,
        )
        cache.record_context_packet_v2(item.work_item_id, context_packet.model_dump(mode="json"))
        cache.record_token_ledger_entry(ledger_entry.model_dump(mode="json"))
        return AgentContextBuildResult(
            envelope=envelope,
            skill_route=route,
            context_packet=context_packet,
            token_ledger_entry=ledger_entry,
            coding_context_packet=coding_packet,
            compact_coding_context_packet=coding_packet_payload,
            compaction_result=compaction_result,
        )


def _context_packet_v2(
    *,
    envelope: AgentTaskEnvelope,
    route: SkillRouteDecision,
    skill_index: SkillIndex,
    artifact_type: str,
) -> ContextPacketV2:
    omitted_refs = [f"skill:{skill_id}:SKILL.md" for skill_id in route.omitted_skill_ids]
    estimated_omitted = _skill_tokens_for_ids(skill_index, route.omitted_skill_ids)
    estimated_input = (
        estimate_tokens(envelope.task_summary)
        + estimate_tokens(" ".join(envelope.upstream_refs))
        + estimate_tokens(envelope.planner_order_ref)
        + estimate_tokens(str(envelope.coding_context_packet))
        + route.estimated_skill_tokens
    )
    total_skill_tokens = route.estimated_skill_tokens + estimated_omitted
    compression_ratio = 0.0 if total_skill_tokens == 0 else round(route.estimated_skill_tokens / total_skill_tokens, 4)
    return ContextPacketV2(
        agent_id=envelope.assigned_agent_id,
        work_item_id=envelope.work_item_id,
        artifact_type=artifact_type,
        included_skill_ids=route.allowed_skill_ids,
        included_refs=[*route.loaded_skill_refs, *envelope.upstream_refs, envelope.planner_order_ref],
        omitted_skill_ids=route.omitted_skill_ids,
        omitted_refs=omitted_refs,
        estimated_input_tokens=estimated_input,
        estimated_omitted_tokens=estimated_omitted,
        compression_ratio=compression_ratio,
    )


def _token_ledger_entry(
    *,
    run_id: str,
    round_number: int,
    envelope: AgentTaskEnvelope,
    route: SkillRouteDecision,
    skill_index: SkillIndex,
    packet: ContextPacketV2,
    artifact_type: str,
) -> TokenLedgerEntry:
    upstream_tokens = estimate_tokens(" ".join(envelope.upstream_refs))
    return TokenLedgerEntry(
        run_id=run_id,
        round=round_number,
        agent_id=envelope.assigned_agent_id,
        work_item_id=envelope.work_item_id,
        artifact_type=artifact_type,
        estimated_input_tokens=packet.estimated_input_tokens,
        skill_tokens_available=_skill_tokens_available(skill_index),
        skill_tokens_loaded=route.estimated_skill_tokens,
        upstream_tokens_loaded=upstream_tokens,
        omitted_tokens=packet.estimated_omitted_tokens,
        compression_ratio=packet.compression_ratio,
    )


def _skill_tokens_available(skill_index: SkillIndex) -> int:
    return sum(skill.max_skill_tokens for skill in skill_index.enabled())


def _skill_tokens_for_ids(skill_index: SkillIndex, skill_ids: list[str]) -> int:
    selected = set(skill_ids)
    return sum(skill.max_skill_tokens for skill in skill_index.enabled() if skill.id in selected)
