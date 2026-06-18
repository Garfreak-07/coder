from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class A2AMessage(BaseModel):
    """Internal A2A-style message.

    This is intentionally small and local-first. It can evolve toward a formal
    A2A-compatible adapter later without forcing the runtime to depend on a
    full external protocol implementation today.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    sender: str
    recipient: str
    type: str
    payload: dict = Field(default_factory=dict)
    requires_user: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuntimeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    source: str
    type: Literal["status", "message", "tool", "approval", "error", "result"]
    status: str | None = None
    message: str = ""
    payload: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

