from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .profile import AgentRuntimeProfile, TokenBudget
from .recipe import AgentRecipe, recipe_from_workflow_agent

if TYPE_CHECKING:
    from coder_workbench.core import AgentWorkflowSpec


class RuntimeProfileCompiler:
    """Compile ordinary Agent recipes into internal runtime profiles."""

    def __init__(self, installed_extensions: list[dict[str, Any]] | None = None) -> None:
        self.installed_extensions = installed_extensions or []

    def compile(
        self,
        recipe: AgentRecipe,
        *,
        run_contract: dict[str, Any] | None = None,
        planner_preferences: dict[str, Any] | None = None,
    ) -> AgentRuntimeProfile:
        role = recipe.role
        return AgentRuntimeProfile(
            agent_id=recipe.id,
            role=role,
            engine_id=_engine_id(role),
            harness_id=_harness_id(role),
            context_profile=_context_profile(role),
            token_budget=_token_budget(role, planner_preferences=planner_preferences),
            allowed_artifacts=_allowed_artifacts(role),
            plugin_policy=_plugin_policy(role, recipe.preferred_extension_ids, run_contract),
            skill_policy=_skill_policy(role, recipe.preferred_extension_ids),
            memory_policy=_memory_policy(role),
            prompt_layers=_prompt_layers(role),
            repair_policy=_repair_policy(role),
            tool_policy=_tool_policy(role),
        )

    def compile_workflow(self, workflow: "AgentWorkflowSpec") -> list[AgentRuntimeProfile]:
        return [
            self.compile(recipe_from_workflow_agent(agent, primary_planner_id=workflow.primary_planner_id))
            for agent in workflow.agents
        ]


def compile_agent_recipe(recipe: AgentRecipe) -> AgentRuntimeProfile:
    return RuntimeProfileCompiler().compile(recipe)


def compile_agent_workflow_profiles(workflow: "AgentWorkflowSpec") -> list[AgentRuntimeProfile]:
    return RuntimeProfileCompiler().compile_workflow(workflow)


def _engine_id(role: str) -> str:
    return {
        "planner": "planner-engine",
        "executor": "code-worker-engine",
    }.get(role, "code-worker-engine")


def _harness_id(role: str) -> str | None:
    if role == "executor":
        return "code-worker-harness"
    return None


def _context_profile(role: str) -> str:
    if role == "planner":
        return "planner-index-only"
    return "coding-executor"


def _token_budget(role: str, *, planner_preferences: dict[str, Any] | None) -> TokenBudget:
    planner_strength = str((planner_preferences or {}).get("strength") or "balanced")
    planner_budget = {"fast": 8000, "balanced": 12000, "strong": 18000}.get(planner_strength, 12000)
    budgets = {
        "planner": planner_budget,
        "executor": 9000,
    }
    return TokenBudget(max_input_tokens=budgets.get(role, 8000))


def _allowed_artifacts(role: str) -> list[str]:
    if role == "planner":
        return ["run_contract", "planner_order", "planner_decision", "round_summary"]
    return ["execution_result"]


def _plugin_policy(role: str, preferred_extension_ids: list[str], run_contract: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "mode": "route_per_work_item",
        "preferred_extension_ids": preferred_extension_ids,
        "external_effects_require_preview": True,
        "run_contract_required": bool(run_contract),
        "can_execute_plugins": role == "executor",
    }


def _skill_policy(role: str, preferred_extension_ids: list[str]) -> dict[str, Any]:
    return {
        "mode": "route_relevant_sections",
        "preferred_extension_ids": preferred_extension_ids,
        "load_full_body": False,
        "max_skills": 5 if role != "planner" else 0,
    }


def _memory_policy(role: str) -> dict[str, Any]:
    return {
        "can_read_workflow_memory": role == "planner",
        "can_write_long_term_memory": role == "planner",
    }


def _prompt_layers(role: str) -> dict[str, Any]:
    if role == "planner":
        return {
            "schema_version": "prompt-layers/v1",
            "layer_order": [
                "output_contract",
                "planner_rules",
                "harness_contract",
                "task_context",
                "state_view",
                "capability_set",
                "memory_context",
            ],
            "max_layer_chars": 8000,
        }
    return {
        "schema_version": "prompt-layers/v1",
        "layer_order": [
            "output_contract",
            "executor_rules",
            "harness_contract",
            "agent_context",
            "work_item",
            "task_envelope",
            "coding_context",
            "capability_set",
            "skill_context",
        ],
        "max_layer_chars": 8000,
    }


def _repair_policy(role: str) -> dict[str, Any]:
    return {
        "schema_repair_attempts": 1,
        "fallback_artifact": "blocked" if role != "planner" else "finish_blocked",
    }


def _tool_policy(role: str) -> dict[str, Any]:
    return {
        "read_files": role == "executor",
        "write_files": role == "executor",
        "run_commands": role == "executor",
        "ask_human": False,
    }
