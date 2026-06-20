from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.agent_graph.schema import WorkItem, WorkItemStatus


class BlockedWorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item: WorkItem
    blocked_by: list[str] = Field(default_factory=list)


class ReadyWave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wave_index: int = Field(ge=1)
    ready_work_item_ids: list[str] = Field(default_factory=list)
    deferred_ready_work_item_ids: list[str] = Field(default_factory=list)
    items: list[WorkItem] = Field(default_factory=list)


class AgentGraphScheduler:
    """Dependency scheduler for PlannerOrder work items.

    Only depends_on creates an execution dependency. merge_index is reserved
    for result presentation back to Planner and does not make earlier items
    block later independent items.
    """

    def __init__(self, work_items: list[WorkItem], *, max_concurrency: int = 4) -> None:
        self.work_items = sorted(work_items, key=lambda item: item.work_item_id)
        self.max_concurrency = max(1, max_concurrency)
        self.status_by_id: dict[str, WorkItemStatus] = {item.work_item_id: "pending" for item in self.work_items}
        self._next_wave_index = 1

    def has_pending(self) -> bool:
        return any(status == "pending" for status in self.status_by_id.values())

    def ready_all(self) -> list[WorkItem]:
        return [
            item
            for item in self.work_items
            if self.status_by_id.get(item.work_item_id) == "pending"
            and all(self.status_by_id.get(upstream_id) == "completed" for upstream_id in item.depends_on)
        ]

    def next_wave(self) -> ReadyWave:
        ready = self.ready_all()
        items = ready[: self.max_concurrency]
        deferred = ready[self.max_concurrency :]
        wave = ReadyWave(
            wave_index=self._next_wave_index,
            ready_work_item_ids=[item.work_item_id for item in ready],
            deferred_ready_work_item_ids=[item.work_item_id for item in deferred],
            items=items,
        )
        if items:
            self._next_wave_index += 1
        return wave

    def ready_items(self) -> list[WorkItem]:
        return self.ready_all()[: self.max_concurrency]

    def waiting_items(self) -> list[WorkItem]:
        return self.dependency_waiting_items()

    def dependency_waiting_items(self) -> list[WorkItem]:
        ready_ids = {item.work_item_id for item in self.ready_all()}
        return [
            item
            for item in self.work_items
            if self.status_by_id.get(item.work_item_id) == "pending"
            and item.work_item_id not in ready_ids
            and not self.failed_upstreams(item)
        ]

    def resource_deferred_items(self) -> list[WorkItem]:
        return self.ready_all()[self.max_concurrency :]

    def block_items_with_failed_upstreams(self) -> list[BlockedWorkItem]:
        blocked: list[BlockedWorkItem] = []
        for item in self.work_items:
            if self.status_by_id.get(item.work_item_id) != "pending":
                continue
            failed = self.failed_upstreams(item)
            if not failed:
                continue
            self.status_by_id[item.work_item_id] = "blocked"
            blocked.append(BlockedWorkItem(work_item=item, blocked_by=failed))
        return blocked

    def failed_upstreams(self, item: WorkItem) -> list[str]:
        return [
            upstream_id
            for upstream_id in item.depends_on
            if self.status_by_id.get(upstream_id) in {"blocked", "failed"}
        ]

    def mark_running(self, work_item_id: str) -> None:
        self._set_status(work_item_id, "running")

    def mark_completed(self, work_item_id: str) -> None:
        self._set_status(work_item_id, "completed")

    def mark_failed(self, work_item_id: str) -> None:
        self._set_status(work_item_id, "failed")

    def mark_blocked(self, work_item_id: str) -> None:
        self._set_status(work_item_id, "blocked")

    def _set_status(self, work_item_id: str, status: WorkItemStatus) -> None:
        if work_item_id not in self.status_by_id:
            raise KeyError(work_item_id)
        self.status_by_id[work_item_id] = status
