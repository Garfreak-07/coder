from __future__ import annotations

from typing import Any

from coder_workbench.agent_engine import AgentEngineRegistry, default_agent_engine_registry
from coder_workbench.agent_graph.schema import AgentTaskEnvelope, ExecutionRecord, WorkItem
from coder_workbench.agent_model import RuntimeProfileCompiler, recipe_from_workflow_agent
from coder_workbench.core import AgentWorkflowAgent, AgentWorkflowSpec


class AgentRun:
    """Runs one Agent work item through a compiled runtime profile and AgentEngine."""

    def __init__(
        self,
        agent_workflow: AgentWorkflowSpec,
        *,
        engine_registry: AgentEngineRegistry | None = None,
        profile_compiler: RuntimeProfileCompiler | None = None,
    ) -> None:
        self.agent_workflow = agent_workflow
        self.engine_registry = engine_registry or default_agent_engine_registry()
        self.profile_compiler = profile_compiler or RuntimeProfileCompiler()

    def run_execution(
        self,
        *,
        item: WorkItem,
        envelope: AgentTaskEnvelope,
        model: Any | None = None,
        emit: Any | None = None,
    ) -> ExecutionRecord:
        agent = self._agent(item.assignee_agent_id)
        recipe = recipe_from_workflow_agent(agent, primary_planner_id=self.agent_workflow.primary_planner_id)
        profile = self.profile_compiler.compile(recipe)
        engine = self.engine_registry.get(profile.engine_id)
        return engine.run_execution(agent=agent, item=item, envelope=envelope, model=model, emit=emit)

    def _agent(self, agent_id: str) -> AgentWorkflowAgent:
        for agent in self.agent_workflow.agents:
            if agent.id == agent_id:
                return agent
        raise KeyError(agent_id)
