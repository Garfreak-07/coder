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
from coder_workbench.agent_harness.contracts import (
    CODE_WORKER_HARNESS,
    PLANNER_DECISION_HARNESS,
    PLANNER_ORDER_HARNESS,
)
from coder_workbench.agent_model import RuntimeProfileCache, RuntimeProfileCompiler, recipe_from_workflow_agent
from coder_workbench.budget import BudgetBroker
from coder_workbench.config import RuntimeConfig, load_runtime_config
from coder_workbench.core import AgentWorkflowAgent, AgentWorkflowSpec
from coder_workbench.harness_runtime import HarnessRuntimeContext, HarnessRuntimeManager
from coder_workbench.harness_runtime.fallback_provider import InternalFallbackProvider
from coder_workbench.llm import create_chat_model
from coder_workbench.runtime_capabilities import CapabilitySet, resolve_capabilities
from coder_workbench.runtime_state import SharedRunState, build_executor_state_view, build_planner_state_view


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
        self.harness_runtime_manager = HarnessRuntimeManager(
            providers=[
                InternalFallbackProvider(
                    planner_order_runner=self._run_planner_order_legacy,
                    task_execution_runner=self._run_execution_legacy,
                    planner_decision_runner=self._run_planner_decision_legacy,
                )
            ]
        )

    def run_planner_order(
        self,
        request: str,
        *,
        previous_bundle: Any | None = None,
        previous_round_summary: dict[str, Any] | None = None,
        skill_index: Any | None = None,
        repo_intelligence: dict[str, Any] | None = None,
        round_number: int = 1,
        emit: Any | None = None,
    ) -> Any:
        planner = self._agent(self.agent_workflow.primary_planner_id)
        profile = self._profile_for_agent(planner)
        state_view = self._planner_state_view()
        capability_set = resolve_capabilities(
            agent=planner,
            runtime_profile=profile,
            harness_id=PLANNER_ORDER_HARNESS.harness_id,
            work_item=None,
            state_view=state_view,
            installed_capabilities=skill_index,
        )
        self._record_capability_set(
            agent_id=planner.id,
            harness_id=PLANNER_ORDER_HARNESS.harness_id,
            capability_set=capability_set,
        )
        context = self._harness_context(
            agent_id=planner.id,
            harness_id="conversation-harness",
            mode="workflow_supervisor",
            profile_id="internal-fallback-workflow-supervisor",
            round_number=round_number,
            state_view=state_view,
            capability_set=capability_set.model_dump(mode="json"),
        )
        result = self.harness_runtime_manager.run_workflow_supervisor(
            context=context,
            profile_id="internal-fallback-workflow-supervisor",
            input_artifacts={
                "legacy_operation": "planner_order",
                "legacy_kwargs": {
                    "request": request,
                    "previous_bundle": previous_bundle,
                    "previous_round_summary": previous_round_summary,
                    "skill_index": skill_index,
                    "repo_intelligence": repo_intelligence,
                    "round_number": round_number,
                    "state_view": state_view,
                    "capability_set": capability_set.model_dump(mode="json"),
                },
            },
            emit=emit,
        )
        legacy_output = getattr(result, "_legacy_output", None)
        if legacy_output is not None:
            return legacy_output
        return result.artifact

    def _run_planner_order_legacy(
        self,
        *,
        request: str,
        previous_bundle: Any | None = None,
        previous_round_summary: dict[str, Any] | None = None,
        skill_index: Any | None = None,
        repo_intelligence: dict[str, Any] | None = None,
        round_number: int = 1,
        state_view: dict[str, Any] | None = None,
        capability_set: dict[str, Any] | None = None,
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
            skill_index=skill_index,
            repo_intelligence=repo_intelligence,
            state_view=state_view,
            capability_set=capability_set,
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
        profile = self._profile_for_agent(agent)
        state_view = self._executor_state_view(item.work_item_id)
        harness_id = profile.harness_id or CODE_WORKER_HARNESS.harness_id
        capability_set = resolve_capabilities(
            agent=agent,
            runtime_profile=profile,
            harness_id=harness_id,
            work_item=item,
            state_view=state_view,
            installed_capabilities={"allowed_skill_ids": envelope.allowed_skill_ids},
        )
        capability_payload = capability_set.model_dump(mode="json")
        envelope = envelope.model_copy(update={"capability_set": capability_payload})
        self._record_capability_set(
            agent_id=agent.id,
            harness_id=harness_id,
            capability_set=capability_set,
        )
        context = self._harness_context(
            agent_id=agent.id,
            harness_id="task-execution-harness",
            mode="task_execution",
            profile_id="internal-fallback-task-executor",
            round_number=envelope.round,
            state_view=state_view,
            capability_set=capability_payload,
        )
        result = self.harness_runtime_manager.run_task_execution(
            context=context,
            profile_id="internal-fallback-task-executor",
            input_artifacts={
                "legacy_operation": "task_execution",
                "legacy_kwargs": {
                    "agent": agent,
                    "engine_id": profile.engine_id,
                    "item": item,
                    "envelope": envelope,
                    "capability_set": capability_payload,
                    "model": model,
                },
            },
            emit=emit,
        )
        legacy_output = getattr(result, "_legacy_output", None)
        if legacy_output is not None:
            return legacy_output
        raise RuntimeError("HarnessRuntimeManager did not return an ExecutionRecord")

    def _run_execution_legacy(
        self,
        *,
        agent: AgentWorkflowAgent,
        engine_id: str,
        item: WorkItem,
        envelope: AgentTaskEnvelope,
        capability_set: dict[str, Any],
        model: Any | None = None,
        emit: Any | None = None,
    ) -> ExecutionRecord:
        engine = self.engine_registry.get(engine_id)
        return engine.run_execution(
            agent=agent,
            item=item,
            envelope=envelope,
            capability_set=capability_set,
            model=model or self._chat_model(),
            repo_root=str(self.initial_data.get("repo_root") or "."),
            sandbox_root=_optional_string(self.initial_data.get("sandbox_root")),
            scopes=_scopes_from_data(self.initial_data),
            run_id=self.run_id,
            data=self.initial_data,
            action_gateway=self.action_gateway,
            emit=emit,
        )

    def run_planner_decision(
        self,
        *,
        bundle: Any,
        emit: Any | None = None,
    ) -> dict[str, Any]:
        planner = self._agent(self.agent_workflow.primary_planner_id)
        profile = self._profile_for_agent(planner)
        state_view = self._planner_state_view()
        capability_set = resolve_capabilities(
            agent=planner,
            runtime_profile=profile,
            harness_id=PLANNER_DECISION_HARNESS.harness_id,
            work_item=None,
            state_view=state_view,
            installed_capabilities=self.initial_data.get("skill_index"),
        )
        self._record_capability_set(
            agent_id=planner.id,
            harness_id=PLANNER_DECISION_HARNESS.harness_id,
            capability_set=capability_set,
        )
        round_number = int(getattr(bundle, "round", 1) or 1)
        context = self._harness_context(
            agent_id=planner.id,
            harness_id="conversation-harness",
            mode="workflow_supervisor",
            profile_id="internal-fallback-workflow-supervisor",
            round_number=round_number,
            state_view=state_view,
            capability_set=capability_set.model_dump(mode="json"),
        )
        result = self.harness_runtime_manager.run_workflow_supervisor(
            context=context,
            profile_id="internal-fallback-workflow-supervisor",
            input_artifacts={
                "legacy_operation": "planner_decision",
                "legacy_kwargs": {
                    "bundle": bundle,
                    "state_view": state_view,
                    "capability_set": capability_set.model_dump(mode="json"),
                },
            },
            emit=emit,
        )
        legacy_output = getattr(result, "_legacy_output", None)
        if legacy_output is not None:
            return legacy_output
        return result.artifact or {}

    def _run_planner_decision_legacy(
        self,
        *,
        bundle: Any,
        state_view: dict[str, Any] | None = None,
        capability_set: dict[str, Any] | None = None,
        emit: Any | None = None,
    ) -> dict[str, Any]:
        mode = self._planner_mode()
        strategy = planner_strategy_for_mode(mode)
        decision = strategy.create_decision(
            PlannerStrategyContext(
                agent_workflow=self.agent_workflow,
                round_number=getattr(bundle, "round", 1),
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
            runtime_settings=self.runtime_settings,
            model_factory=self.model_factory,
            budget_broker=self.budget_broker,
            action_gateway=self.action_gateway,
            run_id=self.run_id,
            state_view=state_view,
            capability_set=capability_set,
            emit=emit,
        )

    def _agent(self, agent_id: str) -> AgentWorkflowAgent:
        for agent in self.agent_workflow.agents:
            if agent.id == agent_id:
                return agent
        raise KeyError(agent_id)

    def _profile_for_agent(self, agent: AgentWorkflowAgent) -> Any:
        profiles = self.profile_cache.compile_or_get(
            self.agent_workflow,
            compiler=self.profile_compiler,
        ).profiles
        profile = next((profile for profile in profiles if profile.agent_id == agent.id), None)
        if profile is not None:
            return profile
        return self.profile_compiler.compile(
            recipe_from_workflow_agent(agent, primary_planner_id=self.agent_workflow.primary_planner_id)
        )

    def _shared_run_state(self) -> SharedRunState | None:
        value = self.initial_data.get("shared_run_state")
        if not isinstance(value, dict):
            return None
        try:
            return SharedRunState.model_validate(value)
        except Exception:
            return None

    def _planner_state_view(self) -> dict[str, Any]:
        state = self._shared_run_state()
        return build_planner_state_view(state) if state is not None else {}

    def _executor_state_view(self, work_item_id: str) -> dict[str, Any]:
        state = self._shared_run_state()
        return build_executor_state_view(state, work_item_id) if state is not None else {}

    def _harness_context(
        self,
        *,
        agent_id: str,
        harness_id: str,
        mode: str,
        profile_id: str,
        round_number: int | None,
        state_view: dict[str, Any] | None,
        capability_set: dict[str, Any] | None,
    ) -> HarnessRuntimeContext:
        shared_state = self.initial_data.get("shared_run_state")
        return HarnessRuntimeContext(
            run_id=self.run_id or str(self.initial_data.get("run_id") or self.agent_workflow.id),
            round=round_number,
            agent_id=agent_id,
            workflow_id=self.agent_workflow.id,
            harness_id=harness_id,
            mode=mode,
            profile_id=profile_id,
            repo_root=str(self.initial_data.get("repo_root") or "."),
            sandbox_root=_optional_string(self.initial_data.get("sandbox_root")),
            capability_set=capability_set,
            shared_run_state=shared_state if isinstance(shared_state, dict) else None,
            round_working_set=state_view,
            initial_data=self.initial_data,
        )

    def _record_capability_set(
        self,
        *,
        agent_id: str,
        harness_id: str,
        capability_set: CapabilitySet,
    ) -> None:
        payload = capability_set.model_dump(mode="json")
        records = self.initial_data.setdefault("capability_sets", [])
        if isinstance(records, list):
            records.append(
                {
                    "agent_id": agent_id,
                    "harness_id": harness_id,
                    "skills": [skill["skill_id"] for skill in payload.get("skills", [])],
                    "tools": [tool["name"] for tool in payload.get("tools", [])],
                    "memory_scopes": [
                        f"{scope['scope']}:{scope['access']}"
                        for scope in payload.get("memory_scopes", [])
                    ],
                    "denied": [capability["name"] for capability in payload.get("denied", [])],
                }
            )
        by_harness = self.initial_data.setdefault("capability_sets_by_harness", {})
        if isinstance(by_harness, dict):
            by_harness[f"{agent_id}:{harness_id}"] = payload

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


def _optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _scopes_from_data(data: dict[str, Any]) -> list[str]:
    value = data.get("scopes", data.get("scope"))
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
