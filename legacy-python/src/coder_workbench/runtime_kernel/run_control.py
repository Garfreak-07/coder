from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event
from typing import Any


class RunCancelled(RuntimeError):
    pass


@dataclass
class RunControl:
    cancel_requested: bool = False
    pause_requested: bool = False
    paused: bool = False
    last_heartbeat_at: str = field(default_factory=lambda: _now_iso())
    location: str = ""
    active_round: int | None = None
    active_wave: int | None = None
    active_work_item_ids: list[str] = field(default_factory=list)
    _resume_event: Event = field(default_factory=Event)

    def __post_init__(self) -> None:
        self._resume_event.set()

    def request_cancel(self) -> None:
        self.cancel_requested = True
        self.pause_requested = False
        self.paused = False
        self._resume_event.set()
        self.heartbeat("cancel_requested")

    def request_pause(self) -> None:
        if self.cancel_requested:
            return
        self.pause_requested = True
        self._resume_event.clear()
        self.heartbeat("pause_requested")

    def request_resume(self) -> None:
        self.pause_requested = False
        self.paused = False
        self._resume_event.set()
        self.heartbeat("resume_requested")

    def heartbeat(
        self,
        location: str,
        *,
        round_number: int | None = None,
        wave_index: int | None = None,
        active_work_item_ids: list[str] | None = None,
    ) -> None:
        self.location = location
        self.last_heartbeat_at = _now_iso()
        if round_number is not None:
            self.active_round = round_number
        if wave_index is not None:
            self.active_wave = wave_index
        if active_work_item_ids is not None:
            self.active_work_item_ids = list(active_work_item_ids)

    def checkpoint(
        self,
        location: str,
        emit: Any | None = None,
        *,
        round_number: int | None = None,
        wave_index: int | None = None,
        active_work_item_ids: list[str] | None = None,
    ) -> None:
        self.heartbeat(
            location,
            round_number=round_number,
            wave_index=wave_index,
            active_work_item_ids=active_work_item_ids,
        )
        if self.cancel_requested:
            raise RunCancelled(f"Run cancelled at {location}.")
        if self.pause_requested:
            self.paused = True
            _emit(emit, "agent_graph.run.paused", f"Run paused at {location}", location=location)
            while self.pause_requested and not self.cancel_requested:
                self._resume_event.wait(timeout=0.1)
            self.paused = False
            if self.cancel_requested:
                raise RunCancelled(f"Run cancelled at {location}.")
            _emit(emit, "agent_graph.run.resumed", f"Run resumed at {location}", location=location)
        _emit(
            emit,
            "agent_graph.run.heartbeat",
            f"Run heartbeat at {location}",
            location=location,
            active_round=self.active_round,
            active_wave=self.active_wave,
            active_work_item_ids=self.active_work_item_ids,
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "cancel_requested": self.cancel_requested,
            "pause_requested": self.pause_requested,
            "paused": self.paused,
            "last_heartbeat_at": self.last_heartbeat_at,
            "location": self.location,
            "active_round": self.active_round,
            "active_wave": self.active_wave,
            "active_work_item_ids": self.active_work_item_ids,
        }


def _emit(emit: Any | None, event_type: str, message: str, **payload: Any) -> None:
    if emit is not None:
        emit(event_type, message, **{key: value for key, value in payload.items() if value is not None})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
