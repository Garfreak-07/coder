from __future__ import annotations

from uuid import uuid4
from typing import Literal

from coder_graph.models import RuntimeEvent


class RuntimeEventBus:
    """Small in-memory event bus for UI runtime visualization.

    This is intentionally simple. Later it can back a WebSocket/SSE stream.
    """

    def __init__(self, task_id: str | None = None) -> None:
        self.task_id = task_id or str(uuid4())
        self.events: list[RuntimeEvent] = []

    def emit(
        self,
        source: str,
        event_type: Literal["status", "message", "tool", "approval", "error", "result"],
        message: str,
        status: str | None = None,
        payload: dict | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            id=str(uuid4()),
            task_id=self.task_id,
            source=source,
            type=event_type,
            status=status,
            message=message,
            payload=payload or {},
        )
        self.events.append(event)
        return event

    def dump(self) -> list[dict]:
        return [event.model_dump(mode="json") for event in self.events]
