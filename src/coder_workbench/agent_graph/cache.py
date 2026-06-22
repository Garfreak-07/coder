from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.agent_graph.schema import (
    AgentTaskEnvelope,
    CachedWorkItem,
    ExecutionRecord,
    PlanCache,
    PlannerInputInterrupt,
    PlannerOrder,
    TestRecord,
    WorkItem,
)


class GraphRunCache(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int = 1
    planner_order: PlannerOrder | None = None
    plan_cache: PlanCache | None = None
    agent_tasks: dict[str, AgentTaskEnvelope] = Field(default_factory=dict)
    execution_cache: dict[str, ExecutionRecord] = Field(default_factory=dict)
    test_cache: dict[str, list[TestRecord]] = Field(default_factory=dict)
    skill_index: dict[str, Any] | None = None
    skill_routes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    context_packets_v2: dict[str, dict[str, Any]] = Field(default_factory=dict)
    token_ledger: list[dict[str, Any]] = Field(default_factory=list)
    hidden_effects: list[dict[str, Any]] = Field(default_factory=list)
    hidden_effect_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    interrupts: list[PlannerInputInterrupt] = Field(default_factory=list)

    def cache_planner_order(self, planner_order: PlannerOrder, planner_order_ref: str) -> PlanCache:
        self.round = planner_order.round
        self.planner_order = planner_order
        self.plan_cache = PlanCache(
            round=planner_order.round,
            planner_order_ref=planner_order_ref,
            work_items=[
                CachedWorkItem(**item.model_dump(mode="python"), status="pending")
                for item in planner_order.plan_graph.work_items
            ],
        )
        return self.plan_cache

    def create_agent_task(
        self,
        item: WorkItem,
        *,
        planner_order_ref: str,
        upstream_refs: list[str] | None = None,
        skill_route: dict[str, Any] | None = None,
    ) -> AgentTaskEnvelope:
        route = skill_route or {}
        selected_skill_context = list(route.get("selected_skill_context") or [])
        envelope = AgentTaskEnvelope(
            round=self.round,
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            assigned_agent_id=item.assignee_agent_id,
            task_summary=item.task_summary,
            constraints=[
                "Stay inside RunContract scope.",
                "Return execution facts only.",
            ],
            upstream_refs=upstream_refs or [],
            planner_order_ref=planner_order_ref,
            allowed_skill_ids=list(route.get("allowed_skill_ids") or []),
            loaded_skill_refs=list(route.get("loaded_skill_refs") or []),
            omitted_skill_ids=list(route.get("omitted_skill_ids") or []),
            estimated_skill_tokens=int(route.get("estimated_skill_tokens") or 0),
            selected_skill_context=selected_skill_context,
        )
        self.agent_tasks[item.work_item_id] = envelope
        if skill_route is not None:
            self.skill_routes[item.work_item_id] = skill_route
        self._set_work_item_status(item.work_item_id, "running")
        return envelope

    def record_context_packet_v2(self, work_item_id: str, packet: dict[str, Any]) -> dict[str, Any]:
        self.context_packets_v2[work_item_id] = packet
        return packet

    def record_token_ledger_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        self.token_ledger.append(entry)
        return entry

    def record_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        self.execution_cache[record.work_item_id] = record
        self._set_work_item_status(record.work_item_id, record.status)
        return record

    def record_test(self, record: TestRecord) -> TestRecord:
        self.test_cache.setdefault(record.work_item_id, []).append(record)
        return record

    def record_hidden_effect(self, record: dict[str, Any], output: dict[str, Any] | None = None) -> dict[str, Any]:
        self.hidden_effects.append(record)
        output_ref = record.get("output_ref") or record.get("patch_ref")
        if output_ref and output is not None:
            self.hidden_effect_outputs[str(output_ref)] = output
        return record

    def record_interrupt(self, interrupt: PlannerInputInterrupt | dict[str, Any]) -> PlannerInputInterrupt:
        record = PlannerInputInterrupt.model_validate(interrupt)
        self.interrupts.append(record)
        return record

    def work_items(self) -> list[CachedWorkItem]:
        return sorted(self.plan_cache.work_items if self.plan_cache else [], key=lambda item: item.merge_index)

    def refs_for_work_item(self, work_item_id: str) -> list[str]:
        refs: list[str] = []
        execution = self.execution_cache.get(work_item_id)
        if execution:
            refs.append(execution.execution_result_ref)
        for test in self.test_cache.get(work_item_id, []):
            if test.test_result_ref:
                refs.append(test.test_result_ref)
        return refs

    def as_runtime_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def _set_work_item_status(self, work_item_id: str, status: str) -> None:
        if not self.plan_cache:
            return
        for index, item in enumerate(self.plan_cache.work_items):
            if item.work_item_id == work_item_id:
                self.plan_cache.work_items[index] = item.model_copy(update={"status": status})
                return
