from __future__ import annotations

from .router_models import RouterRoleProfile


PLANNING_CHAT_ROUTER_PROFILE = RouterRoleProfile(
    role="planning_chat",
    default_sources=["direct_memory", "hybrid_rag", "native_repo"],
    allowed_sources=["native_repo", "run_evidence", "direct_memory", "hybrid_rag", "clarify_user"],
    allowed_memory_scopes=["user", "project", "planner_session", "workflow_run", "knowledge_source", "agent_style"],
    allowed_contexts=["assistant_message", "planner_task_state"],
    rag_first_allowed=True,
    repo_verification_required_for_code_claims=True,
    can_ask_user=True,
    can_write_files=False,
    can_run_commands=False,
    max_repo_evidence_tokens=3000,
    max_run_evidence_tokens=2000,
    max_rag_hint_tokens=4000,
)

WORKFLOW_SUPERVISOR_ROUTER_PROFILE = RouterRoleProfile(
    role="workflow_supervisor",
    default_sources=["run_evidence", "native_repo", "direct_memory", "hybrid_rag"],
    allowed_sources=["run_evidence", "native_repo", "direct_memory", "hybrid_rag"],
    allowed_memory_scopes=["project", "workflow_run", "knowledge_source"],
    allowed_contexts=["workflow_supervision", "planner_order", "final_report"],
    rag_first_allowed=False,
    repo_verification_required_for_code_claims=True,
    can_ask_user=False,
    can_write_files=False,
    can_run_commands=False,
    max_repo_evidence_tokens=3000,
    max_run_evidence_tokens=4000,
    max_rag_hint_tokens=2000,
)

TASK_EXECUTION_ROUTER_PROFILE = RouterRoleProfile(
    role="task_execution",
    default_sources=["native_repo", "run_evidence", "hybrid_rag"],
    allowed_sources=["native_repo", "run_evidence", "hybrid_rag"],
    allowed_memory_scopes=["knowledge_source", "workflow_run"],
    allowed_contexts=["execution_prompt"],
    rag_first_allowed=False,
    repo_verification_required_for_code_claims=True,
    can_ask_user=False,
    can_write_files=True,
    can_run_commands=True,
    max_repo_evidence_tokens=4000,
    max_run_evidence_tokens=2000,
    max_rag_hint_tokens=1500,
)


def router_profile_for_mode(mode: str) -> RouterRoleProfile:
    profiles = {
        "planning_chat": PLANNING_CHAT_ROUTER_PROFILE,
        "workflow_supervisor": WORKFLOW_SUPERVISOR_ROUTER_PROFILE,
        "task_execution": TASK_EXECUTION_ROUTER_PROFILE,
    }
    try:
        return profiles[mode]
    except KeyError as exc:
        raise ValueError(f"unsupported router mode {mode!r}") from exc


__all__ = [
    "PLANNING_CHAT_ROUTER_PROFILE",
    "TASK_EXECUTION_ROUTER_PROFILE",
    "WORKFLOW_SUPERVISOR_ROUTER_PROFILE",
    "router_profile_for_mode",
]
