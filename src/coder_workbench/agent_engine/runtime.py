from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from coder_workbench.core import AgentWorkflowAgent

if TYPE_CHECKING:
    from coder_workbench.agent_graph.schema import AgentTaskEnvelope, ExecutionRecord, WorkItem


class AgentEngine(Protocol):
    id: str

    def run_execution(
        self,
        *,
        agent: AgentWorkflowAgent,
        item: "WorkItem",
        envelope: "AgentTaskEnvelope",
        model: Any | None = None,
        emit: Any | None = None,
    ) -> "ExecutionRecord":
        ...


class CodeWorkerEngine:
    id = "code-worker-engine"

    def run_execution(
        self,
        *,
        agent: AgentWorkflowAgent,
        item: "WorkItem",
        envelope: "AgentTaskEnvelope",
        model: Any | None = None,
        emit: Any | None = None,
    ) -> "ExecutionRecord":
        from coder_workbench.agent_graph.prompts import build_worker_execution_prompt
        from coder_workbench.agent_harness import CodeWorkerHarness

        return CodeWorkerHarness(model=model).create_execution_result(
            item=item,
            envelope=envelope,
            coding_context_packet=envelope.coding_context_packet if model is not None else None,
            emit=emit,
            prompt=build_worker_execution_prompt(agent=agent, item=item, envelope=envelope),
        )
