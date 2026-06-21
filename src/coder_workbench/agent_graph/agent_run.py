from __future__ import annotations

from typing import Any

from coder_workbench.actions import ActionGateway
from coder_workbench.agent_engine import AgentEngineRegistry, default_agent_engine_registry
from coder_workbench.agent_graph.planner_strategy import (
    PlannerStrategyContext,
    planner_mode_from,
    planner_strategy_for_mode,
)
from coder_workbench.agent_graph.schema import AgentTaskEnvelope, ExecutionRecord, WorkItem
from coder_workbench.agent_model import RuntimeProfileCache, RuntimeProfileCompiler, recipe_from_workflow_agent
from coder_workbench.budget import BudgetBroker
from coder_workbench.config import RuntimeConfig, load_runtime_config
from coder_workbench.core import AgentWorkflowAgent, AgentWorkflowSpec
from coder_workbench.llm import create_chat_model


ModelFactory = Any


class AgentRun:
    """Runs one Agent work item through a compiled runtime profile and AgentEngine."""

    def __init__(
        self,
        agent_workflow: AgentWorkflowSpec,
        *,
        engine_registry: AgentEngineRegistry | None = None,
        profile_compiler: RuntimeProfileCompiler | None = None,
        profile_cache: RuntimeProfileCache | None = None,
        runtime_settings: Any | None = None,
        model_factory: ModelFactory = create_chat_model,
        budget_broker: BudgetBroker | None = None,
        action_gateway: ActionGateway | None = None,
        run_id: str | None = None,
        initial_data: dict[str, Any] | None = None,
    ) -> None:
        self.agent_workflow = agent_workflow
        self.engine_registry = engine_registry or default_agent_engine_registry()
        self.profile_compiler = profile_compiler or RuntimeProfileCompiler()
        self.profile_cache = profile_cache or RuntimeProfileCache()
        self.runtime_settings = runtime_settings
        self.model_factory = model_factory
        self.budget_broker = budget_broker
        self.action_gateway = action_gateway
        self.run_id = run_id
        self.initial_data = initial_data or {}

    def run_planner_order(
        self,
        request: str,
        *,
        previous_bundle: Any | None = None,
        previous_round_summary: dict[str, Any] | None = None,
        planner_human_response: dict[str, Any] | None = None,
        skill_index: Any | None = None,
        repo_intelligence: dict[str, Any] | None = None,
        round_number: int = 1,
        emit: Any | None = None,
    ) -> Any:
        mode = self._planner_mode()
        strategy = planner_strategy_for_mode(mode)
        order = strategy.create_order(
            PlannerStrategyContext(
                agent_workflow=self.agent_workflow,
                request=request,
                round_number=round_number,
                previous_bundle=previous_bundle,
                previous_round_summary=previous_round_summary,
                planner_human_response=planner_human_response,
                skill_index=skill_index,
                repo_intelligence=repo_intelligence,
                initial_data=self.initial_data,
            )
        )
        if order is not None:
            self._emit_strategy_used(emit, mode, "planner_order", round_number)
            return order
        return self.engine_registry.planner().run_planner_order(
            request,
            agent_workflow=self.agent_workflow,
            runtime_settings=self.runtime_settings,
            model_factory=self.model_factory,
            budget_broker=self.budget_broker,
            action_gateway=self.action_gateway,
            run_id=self.run_id,
            previous_bundle=previous_bundle,
            previous_round_summary=previous_round_summary,
            planner_human_response=planner_human_response,
            skill_index=skill_index,
            repo_intelligence=repo_intelligence,
            round_number=round_number,
            emit=emit,
        )

    def run_execution(
        self,
        *,
        item: WorkItem,
        envelope: AgentTaskEnvelope,
        model: Any | None = None,
        emit: Any | None = None,
    ) -> ExecutionRecord:
        agent = self._agent(item.assignee_agent_id)
        profiles = self.profile_cache.compile_or_get(
            self.agent_workflow,
            compiler=self.profile_compiler,
        ).profiles
        profile = next((profile for profile in profiles if profile.agent_id == agent.id), None)
        if profile is None:
            profile = self.profile_compiler.compile(
                recipe_from_workflow_agent(agent, primary_planner_id=self.agent_workflow.primary_planner_id)
            )
        engine = self.engine_registry.get(profile.engine_id)
        if profile.engine_id == "synthesizer-engine" and hasattr(engine, "run_synthesis"):
            return engine.run_synthesis(
                agent_workflow=self.agent_workflow,
                agent=agent,
                item=item,
                envelope=envelope,
                model=model,
                runtime_settings=self.runtime_settings,
                model_factory=self.model_factory,
                budget_broker=self.budget_broker,
                action_gateway=self.action_gateway,
                run_id=self.run_id,
                emit=emit,
            )
        return engine.run_execution(agent=agent, item=item, envelope=envelope, model=model or self._chat_model(), emit=emit)

    def run_test(
        self,
        *,
        item: WorkItem,
        execution_artifact: dict[str, Any],
        tester_agent_id: str,
        emit: Any | None = None,
    ) -> Any:
        return self.engine_registry.tester().run_test(
            agent_workflow=self.agent_workflow,
            item=item,
            execution_artifact=execution_artifact,
            tester_agent_id=tester_agent_id,
            runtime_settings=self.runtime_settings,
            model_factory=self.model_factory,
            budget_broker=self.budget_broker,
            action_gateway=self.action_gateway,
            run_id=self.run_id,
            emit=emit,
        )

    def run_final_test(
        self,
        *,
        bundle: Any,
        final_tester_agent_id: str,
        emit: Any | None = None,
    ) -> Any:
        return self.engine_registry.final_review().run_final_test(
            agent_workflow=self.agent_workflow,
            bundle=bundle,
            final_tester_agent_id=final_tester_agent_id,
            runtime_settings=self.runtime_settings,
            model_factory=self.model_factory,
            budget_broker=self.budget_broker,
            action_gateway=self.action_gateway,
            run_id=self.run_id,
            emit=emit,
        )

    def run_planner_decision(
        self,
        *,
        bundle: Any,
        planner_human_response: dict[str, Any] | None = None,
        emit: Any | None = None,
    ) -> dict[str, Any]:
        mode = self._planner_mode()
        strategy = planner_strategy_for_mode(mode)
        decision = strategy.create_decision(
            PlannerStrategyContext(
                agent_workflow=self.agent_workflow,
                round_number=getattr(bundle, "round", 1),
                planner_human_response=planner_human_response,
                initial_data=self.initial_data,
                bundle=bundle,
            )
        )
        if decision is not None:
            self._emit_strategy_used(emit, mode, "planner_decision", int(getattr(bundle, "round", 1) or 1))
            return decision
        return self.engine_registry.planner().run_planner_decision(
            agent_workflow=self.agent_workflow,
            bundle=bundle,
            planner_human_response=planner_human_response,
            runtime_settings=self.runtime_settings,
            model_factory=self.model_factory,
            budget_broker=self.budget_broker,
            action_gateway=self.action_gateway,
            run_id=self.run_id,
            emit=emit,
        )

    def _agent(self, agent_id: str) -> AgentWorkflowAgent:
        for agent in self.agent_workflow.agents:
            if agent.id == agent_id:
                return agent
        raise KeyError(agent_id)

    def _chat_model(self) -> Any | None:
        config = self._runtime_config()
        if not config.has_llm_credentials:
            return None
        return self.model_factory(config)

    def _runtime_config(self) -> RuntimeConfig:
        if self.runtime_settings is not None:
            from coder_workbench.server.settings import resolve_settings_config

            values = resolve_settings_config(self.runtime_settings, None, None)
            return RuntimeConfig(
                provider=str(values["provider"]),
                model=str(values["model"]),
                api_key=values["api_key"],
                base_url=values["base_url"],
            )
        return load_runtime_config()

    def _planner_mode(self) -> str:
        return planner_mode_from(self.initial_data, self.runtime_settings)

    def _emit_strategy_used(self, emit: Any | None, mode: str, artifact_type: str, round_number: int) -> None:
        if emit is None:
            return
        emit(
            "planner.strategy.used",
            "PlannerStrategy produced local artifact",
            planner_mode=mode,
            artifact_type=artifact_type,
            round=round_number,
        )
