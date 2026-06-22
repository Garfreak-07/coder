from __future__ import annotations

from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.core import AgentWorkflowSpec, compile_runtime_profiles
from coder_workbench.runtime.state import RunEvent


class AgentEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    agent_archetype: str
    calls: int = 0
    schema_valid_rate: float = 0.0
    repair_rate: float = 0.0
    blocked_rate: float = 0.0
    interrupt_rate: float = 0.0
    average_input_tokens: int = 0
    average_output_tokens: int = 0
    skill_activation_precision: float | None = None
    notes: list[str] = Field(default_factory=list)


class SkillEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    activation_precision: float | None = None
    activation_recall: float | None = None
    success_when_used: int = 0
    failure_when_used: int = 0
    average_token_cost: int = 0
    risk_incident_count: int = 0
    user_disable_rate: float | None = None


def build_agent_evaluation_reports(
    *,
    workflow: AgentWorkflowSpec,
    graph_run_cache: dict[str, Any],
    events: list[RunEvent],
    token_ledger: list[dict[str, Any]],
) -> list[AgentEvaluationReport]:
    profile_by_agent = {profile.agent_id: profile for profile in compile_runtime_profiles(workflow)}
    schema_failures = _count_events_by_agent(events, "agent_graph.agent_call.schema_failed")
    repairs = _count_events_by_agent(events, "agent_graph.agent_call.repair_completed")
    interrupts = _count_events_by_agent(events, "agent_graph.interrupt.requested")
    blocked_by_agent = _blocked_counts(graph_run_cache)
    call_counts = _call_counts(graph_run_cache, token_ledger, workflow, events)
    reports: list[AgentEvaluationReport] = []
    for agent in workflow.agents:
        calls = call_counts.get(agent.id, 0)
        failures = schema_failures.get(agent.id, 0)
        report = AgentEvaluationReport(
            agent_id=agent.id,
            agent_archetype=profile_by_agent[agent.id].agent_archetype if agent.id in profile_by_agent else agent.role,
            calls=calls,
            schema_valid_rate=_rate(max(0, calls - failures), calls),
            repair_rate=_rate(repairs.get(agent.id, 0), calls),
            blocked_rate=_rate(blocked_by_agent.get(agent.id, 0), calls),
            interrupt_rate=_rate(interrupts.get(agent.id, 0), calls),
            average_input_tokens=_average_tokens(token_ledger, agent.id, "estimated_input_tokens"),
            average_output_tokens=_average_tokens(token_ledger, agent.id, "estimated_output_tokens"),
            notes=[] if calls else ["agent was not called in this run"],
        )
        reports.append(report)
    return reports


def build_skill_evaluation_reports(
    *,
    graph_run_cache: dict[str, Any],
    token_ledger: list[dict[str, Any]],
) -> list[SkillEvaluationReport]:
    skill_routes = graph_run_cache.get("skill_routes") if isinstance(graph_run_cache, dict) else {}
    execution_cache = graph_run_cache.get("execution_cache") if isinstance(graph_run_cache, dict) else {}
    if not isinstance(skill_routes, dict):
        return []
    per_skill: dict[str, dict[str, Any]] = {}
    for work_item_id, route in skill_routes.items():
        if not isinstance(route, dict):
            continue
        for skill_id in route.get("allowed_skill_ids", []):
            stats = per_skill.setdefault(str(skill_id), {"activations": 0, "success": 0, "failure": 0, "tokens": []})
            stats["activations"] += 1
            status = _execution_status(execution_cache, str(work_item_id))
            if status == "completed":
                stats["success"] += 1
            elif status in {"blocked", "failed"}:
                stats["failure"] += 1
    for entry in token_ledger:
        if not isinstance(entry, dict):
            continue
        work_item_id = str(entry.get("work_item_id") or "")
        route = skill_routes.get(work_item_id)
        if not isinstance(route, dict):
            continue
        loaded_ids = [str(skill_id) for skill_id in route.get("allowed_skill_ids", [])]
        if not loaded_ids:
            continue
        per_skill_tokens = int(entry.get("skill_tokens_loaded") or 0) // max(1, len(loaded_ids))
        for skill_id in loaded_ids:
            per_skill.setdefault(skill_id, {"activations": 0, "success": 0, "failure": 0, "tokens": []})["tokens"].append(per_skill_tokens)
    return [
        SkillEvaluationReport(
            skill_id=skill_id,
            activation_precision=None,
            activation_recall=None,
            success_when_used=int(stats["success"]),
            failure_when_used=int(stats["failure"]),
            average_token_cost=int(mean(stats["tokens"])) if stats["tokens"] else 0,
            risk_incident_count=0,
            user_disable_rate=None,
        )
        for skill_id, stats in sorted(per_skill.items())
    ]


def _count_events_by_agent(events: list[RunEvent], event_type: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if event.type != event_type:
            continue
        agent_id = event.payload.get("agent_id")
        if not isinstance(agent_id, str):
            continue
        counts[agent_id] = counts.get(agent_id, 0) + 1
    return counts


def _blocked_counts(graph_run_cache: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    execution_cache = graph_run_cache.get("execution_cache") if isinstance(graph_run_cache, dict) else {}
    if isinstance(execution_cache, dict):
        for record in execution_cache.values():
            if not isinstance(record, dict) or record.get("status") != "blocked":
                continue
            agent_id = str(record.get("agent_id") or "")
            counts[agent_id] = counts.get(agent_id, 0) + 1
    return counts


def _call_counts(
    graph_run_cache: dict[str, Any],
    token_ledger: list[dict[str, Any]],
    workflow: AgentWorkflowSpec,
    events: list[RunEvent],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in token_ledger:
        if not isinstance(entry, dict):
            continue
        agent_id = str(entry.get("agent_id") or "")
        if agent_id:
            counts[agent_id] = counts.get(agent_id, 0) + 1
    execution_cache = graph_run_cache.get("execution_cache") if isinstance(graph_run_cache, dict) else {}
    if isinstance(execution_cache, dict):
        for record in execution_cache.values():
            if not isinstance(record, dict):
                continue
            agent_id = str(record.get("agent_id") or "")
            if agent_id and agent_id not in counts:
                counts[agent_id] = 1
    test_cache = graph_run_cache.get("test_cache") if isinstance(graph_run_cache, dict) else {}
    if isinstance(test_cache, dict):
        for records in test_cache.values():
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                agent_id = str(record.get("tester_agent_id") or "")
                if agent_id:
                    counts[agent_id] = counts.get(agent_id, 0) + 1
    planner_calls = sum(
        1
        for event in events
        if event.type in {"planner.order.produced", "planner.decision.produced", "round_summary.created"}
    )
    if planner_calls:
        counts[workflow.primary_planner_id] = counts.get(workflow.primary_planner_id, 0) + planner_calls
    for agent in workflow.agents:
        counts.setdefault(agent.id, 0)
    return counts


def _execution_status(execution_cache: Any, work_item_id: str) -> str | None:
    if not isinstance(execution_cache, dict):
        return None
    record = execution_cache.get(work_item_id)
    if not isinstance(record, dict):
        return None
    status = record.get("status")
    return str(status) if status else None


def _average_tokens(token_ledger: list[dict[str, Any]], agent_id: str, key: str) -> int:
    values = [
        int(entry.get(key) or 0)
        for entry in token_ledger
        if isinstance(entry, dict) and entry.get("agent_id") == agent_id
    ]
    return int(mean(values)) if values else 0


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
