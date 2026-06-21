from __future__ import annotations

from .runtime import AgentEngine, CodeWorkerEngine


class AgentEngineRegistry:
    def __init__(self, engines: list[AgentEngine] | None = None) -> None:
        self._engines = {engine.id: engine for engine in (engines or [CodeWorkerEngine()])}

    def get(self, engine_id: str) -> AgentEngine:
        try:
            return self._engines[engine_id]
        except KeyError as exc:
            raise KeyError(f"unknown AgentEngine {engine_id!r}") from exc

    def ids(self) -> list[str]:
        return sorted(self._engines)


def default_agent_engine_registry() -> AgentEngineRegistry:
    return AgentEngineRegistry()
