from __future__ import annotations

from uuid import uuid4
from typing import Literal

from coder_graph.models import A2AMessage, AgentCard, RuntimeEvent
from coder_graph.runtime.a2a import A2ARouter


class RuntimeEventBus:
    """Small in-memory event bus for UI runtime visualization.

    This is intentionally simple. Later it can back a WebSocket/SSE stream.
    """

    def __init__(self, task_id: str | None = None, agents: list[AgentCard] | None = None) -> None:
        self.task_id = task_id or str(uuid4())
        self.events: list[RuntimeEvent] = []
        self.messages: list[A2AMessage] = []
        self.router = A2ARouter(agents or [])

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

    def send_message(
        self,
        sender: str,
        recipient: str,
        message_type: str,
        payload: dict | None = None,
        action: str | None = None,
        correlation_id: str | None = None,
        metadata: dict | None = None,
        requires_user: bool = False,
    ) -> A2AMessage:
        message = A2AMessage(
            id=str(uuid4()),
            task_id=self.task_id,
            protocol="local-a2a-v1",
            sender=sender,
            recipient=recipient,
            type=message_type,
            action=action,
            correlation_id=correlation_id,
            payload=payload or {},
            metadata=metadata or {},
            requires_user=requires_user,
        )
        self.messages.append(message)
        self.router.route(message)
        return message

    def dump(self) -> list[dict]:
        return [event.model_dump(mode="json") for event in self.events]

    def dump_messages(self) -> list[dict]:
        return [message.model_dump(mode="json") for message in self.messages]

    def dump_a2a_queues(self) -> dict:
        return self.router.dump()
