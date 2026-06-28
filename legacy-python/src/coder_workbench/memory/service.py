from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coder_workbench.agent_graph.schema import PlannerInputBundle, PlanRunSummary
from coder_workbench.agent_graph.memory import WorkflowMemory
from coder_workbench.memory.schema import MemoryCommitResult, MemoryDelta, StagedMemoryWrite
from coder_workbench.memory.store import WorkflowMemoryStore


class MemoryService:
    """Gated long-term memory service.

    Executors may report evidence through execution artifacts, but they cannot
    write durable workflow or project memory directly.
    """

    def __init__(self, repo_root: str | Path, *, workflow_store: WorkflowMemoryStore | None = None) -> None:
        self.workflow_store = workflow_store or WorkflowMemoryStore(repo_root)
        self._staged: dict[str, StagedMemoryWrite] = {}

    def load_workflow_memory(self, workflow_id: str) -> WorkflowMemory:
        return self.workflow_store.load_workflow_memory(workflow_id)

    def stage_delta(self, delta: MemoryDelta | dict[str, Any]) -> StagedMemoryWrite:
        parsed = delta if isinstance(delta, MemoryDelta) else MemoryDelta.model_validate(delta)
        rejection = self._rejection_reason(parsed)
        if rejection:
            return StagedMemoryWrite(status="rejected", delta=parsed, reason=rejection)
        write = StagedMemoryWrite(status="staged", delta=parsed)
        self._staged[write.write_id] = write
        return write

    def commit_staged(self, write_id: str, *, approved_by: str) -> MemoryCommitResult:
        write = self._staged.get(write_id)
        if write is None:
            return MemoryCommitResult(write_id=write_id, status="rejected", reason="unknown_memory_write")
        if write.status != "staged":
            return MemoryCommitResult(write_id=write_id, status=write.status, reason=write.reason)
        if not approved_by:
            return MemoryCommitResult(write_id=write_id, status="rejected", reason="memory_write_requires_approval")

        entry = dict(write.delta.entry)
        entry.setdefault("evidence_refs", list(write.delta.evidence_refs))
        entry.setdefault("memory_write_id", write.write_id)
        entry.setdefault("memory_actor", {"id": write.delta.actor_id, "role": write.delta.actor_role})
        self.workflow_store.append_entry(
            workflow_id=write.delta.workflow_id,
            collection=write.delta.collection,
            entry=entry,
        )
        committed = write.model_copy(
            update={
                "status": "committed",
                "approved_by": approved_by,
                "committed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._staged[write_id] = committed
        return MemoryCommitResult(write_id=write_id, status="committed")

    def record_planner_round(
        self,
        *,
        workflow_id: str,
        bundle: PlannerInputBundle,
        round_summary: PlanRunSummary,
        planner_decision: dict[str, Any],
    ) -> WorkflowMemory:
        deltas = self._planner_round_deltas(
            workflow_id=workflow_id,
            bundle=bundle,
            round_summary=round_summary,
            planner_decision=planner_decision,
        )
        for delta in deltas:
            staged = self.stage_delta(delta)
            if staged.status == "staged":
                self.commit_staged(staged.write_id, approved_by="runtime")
        return self.load_workflow_memory(workflow_id)

    def _planner_round_deltas(
        self,
        *,
        workflow_id: str,
        bundle: PlannerInputBundle,
        round_summary: PlanRunSummary,
        planner_decision: dict[str, Any],
    ) -> list[MemoryDelta]:
        deltas: list[MemoryDelta] = []
        for item in bundle.items:
            if item.execution_status == "completed" and item.verification_status in {"pass", "skipped"}:
                refs = _evidence_refs(item.refs, bundle.planner_order_ref)
                deltas.append(
                    MemoryDelta(
                        workflow_id=workflow_id,
                        collection="successful_assignments",
                        actor_id="planner",
                        actor_role="planner",
                        evidence_refs=refs,
                        entry={
                            "round": bundle.round,
                            "work_item_id": item.work_item_id,
                            "task_summary": item.task_summary,
                            "refs": item.refs,
                        },
                    )
                )
        for interrupt in bundle.interrupts:
            deltas.append(
                MemoryDelta(
                    workflow_id=workflow_id,
                    collection="common_blockers",
                    actor_id="planner",
                    actor_role="planner",
                    evidence_refs=_evidence_refs([interrupt.artifact_ref], bundle.planner_order_ref),
                    entry={
                        "round": interrupt.round,
                        "work_item_id": interrupt.work_item_id,
                        "blocker_type": interrupt.blocker_type,
                        "reason": interrupt.reason,
                        "planner_question": interrupt.planner_question,
                        "artifact_ref": interrupt.artifact_ref,
                    },
                )
            )

        round_refs = _evidence_refs(
            [
                ref
                for item in round_summary.ordered_state
                for ref in item.refs
            ],
            bundle.planner_order_ref,
        )
        deltas.append(
            MemoryDelta(
                workflow_id=workflow_id,
                collection="planner_notes",
                actor_id="planner",
                actor_role="planner",
                evidence_refs=round_refs,
                entry={
                    "round": bundle.round,
                    "plan_status": bundle.plan_status,
                    "next_action": planner_decision.get("next_action"),
                    "reason": planner_decision.get("reason"),
                    "remaining_work": round_summary.remaining_work,
                },
            )
        )
        return deltas

    def _rejection_reason(self, delta: MemoryDelta) -> str | None:
        if delta.actor_role == "executor":
            return "executor_cannot_write_long_term_memory"
        if not delta.evidence_refs:
            return "memory_delta_requires_evidence_refs"
        if delta.scope != "workflow":
            return "memory_scope_not_supported"
        return None


def _evidence_refs(refs: list[str], fallback_ref: str) -> list[str]:
    cleaned = [str(ref) for ref in refs if str(ref).strip()]
    return cleaned or [fallback_ref]
