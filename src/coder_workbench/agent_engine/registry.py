from __future__ import annotations

from typing import Any

from .runtime import (
    AgentEngine,
    CodeWorkerEngine,
    PlannerEngine,
)


class AgentEngineRegistry:
    def __init__(self, engines: list[Any] | None = None) -> None:
        self._engines = {
            engine.id: engine
            for engine in (
                engines
                or [
                    PlannerEngine(),
                    CodeWorkerEngine(),
                ]
            )
        }

    def get(self, engine_id: str) -> AgentEngine:
        try:
            return self._engines[engine_id]
        except KeyError as exc:
            raise KeyError(f"unknown AgentEngine {engine_id!r}") from exc

    def ids(self) -> list[str]:
        return sorted(self._engines)

    def planner(self) -> PlannerEngine:
        return self.get(PlannerEngine.id)  # type: ignore[return-value]


def default_agent_engine_registry() -> AgentEngineRegistry:
    return AgentEngineRegistry()
