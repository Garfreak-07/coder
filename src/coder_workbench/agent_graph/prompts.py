from __future__ import annotations

import json
from typing import Any

from coder_workbench.agent_graph.schema import AgentTaskEnvelope, PlannerInputBundle, WorkItem
from coder_workbench.core import AgentWorkflowAgent, AgentWorkflowSpec
from coder_workbench.skills.index import SkillIndex


def build_planner_order_prompt(
    *,
    request: str,
    agent_workflow: AgentWorkflowSpec,
    previous_bundle: PlannerInputBundle | None = None,
    previous_round_summary: dict[str, Any] | None = None,
    planner_human_response: dict[str, Any] | None = None,
    skill_index: SkillIndex | None = None,
    repo_intelligence: dict[str, Any] | None = None,
    round_number: int = 1,
) -> str:
    parts = [
        _json_only_header("planner_order"),
        "You are the primary Planner. Split the user request into a small AgentGraph plan.",
        "Only use Agents that exist in the supplied AgentWorkflow.",
        "depends_on is the only execution dependency. Do not use merge_index to force execution order.",
        "If work items can run independently, leave depends_on empty.",
        "merge_index is only the stable result presentation order returned to Planner.",
        "If previous PlannerInputBundle or RoundSummary exists, plan only remaining or corrective work.",
        "Do not repeat completed work unless necessary. New work_item_id values should be unique for this round.",
        "Use repo intelligence before creating work_items.",
        "Do not create vague work items.",
        "Assign work_items to reachable Agents only.",
        "Use depends_on only for real execution dependency.",
        "Use merge_index only for result presentation.",
        "Do not touch risk_files unless the RunContract allows it.",
        _planner_order_schema_notes(),
        "Round number:",
        str(round_number),
        "User request:",
        request,
        "AgentWorkflow JSON:",
        _compact_json(_workflow_summary(agent_workflow)),
    ]
    if repo_intelligence:
        parts.extend(
            [
                "RepoIndex summary JSON:",
                _compact_json(repo_intelligence.get("repo_index", {})),
                "CommandDiscovery summary JSON:",
                _compact_json(repo_intelligence.get("command_discovery", {})),
                "RiskMap summary JSON:",
                _compact_json(repo_intelligence.get("risk_map", {})),
                "SymbolIndex summary JSON:",
                _compact_json(_symbol_index_summary(repo_intelligence.get("symbol_index", {}))),
            ]
        )
    if skill_index and skill_index.skills:
        parts.extend(
            [
                "Installed SkillIndex JSON:",
                _compact_json(skill_index.model_dump(mode="json")),
                "Use the SkillIndex for capability awareness, but do not paste Skill bodies into PlannerOrder.",
            ]
        )
    if previous_bundle:
        parts.extend(["Previous PlannerInputBundle JSON:", _compact_json(previous_bundle.model_dump(mode="json", exclude_none=True))])
        debug_findings = _debug_findings_from_effects(previous_bundle.effects)
        if debug_findings:
            parts.extend(["Debug findings from previous round:", _debug_findings_text(debug_findings)])
    if previous_round_summary:
        parts.extend(["Previous RoundSummary JSON:", _compact_json(previous_round_summary)])
    if planner_human_response:
        parts.extend(["Planner human response JSON:", _compact_json(planner_human_response)])
    return "\n\n".join(parts)


def build_worker_execution_prompt(
    *,
    agent: AgentWorkflowAgent,
    item: WorkItem,
    envelope: AgentTaskEnvelope,
) -> str:
    return "\n\n".join(
        [
            _json_only_header("execution_result"),
            "You are an Executor Agent. Return execution facts only.",
            "Use the fixed lifecycle: inspect the WorkItem, execute only inside its scope, verify the result, then report.",
            "Do not ask the human. Do not make global continue/finish decisions.",
            "All file edits, commands, connector calls, and external effects must go through the runtime ActionGateway; do not claim a side effect happened unless the runtime evidence exists.",
            "The Executor may run allowed checks, but check/test evidence must be stored inside execution_result.verification.",
            "If you cannot safely complete the work item, return status=\"blocked\", "
            "needs_planner_decision=true, blocker_type, planner_question, candidate_options, "
            "remaining_work, verification, and continue_without_human_possible.",
            "Do not ask the human directly. Do not decide whether to continue the whole workflow.",
            "If changes are needed, describe them in proposed_changes; do not claim files were modified directly.",
            _execution_result_schema_notes(),
            "Assigned Agent JSON:",
            _compact_json(_agent_summary(agent)),
            "Work item JSON:",
            _compact_json(item.model_dump(mode="json")),
            "AgentTaskEnvelope JSON:",
            _compact_json(envelope.model_dump(mode="json")),
            "CodingContextPacket JSON:",
            _compact_json(envelope.coding_context_packet),
            "Selected Skill context JSON:",
            _compact_json(envelope.selected_skill_context),
        ]
    )


def build_planner_decision_prompt(
    *,
    planner: AgentWorkflowAgent,
    bundle: PlannerInputBundle,
    planner_human_response: dict[str, Any] | None = None,
) -> str:
    parts = [
        _json_only_header("planner_decision"),
        "You are the primary Planner. You are the only Agent that can decide continue, ask_human, finish, or stop.",
        "Use ask_human only when the next step requires user judgment or approval.",
        "If PlannerInputBundle contains interrupts, decide one of: continue when the problem can be handled within the existing user agreement; "
        "ask_human when it exceeds the agreed direction, requires user judgment, or cannot be safely decided; "
        "stop when continuing is unsafe or impossible; finish only if the task is complete. Do not ignore interrupts.",
        _planner_decision_schema_notes(),
        "Planner Agent JSON:",
        _compact_json(_agent_summary(planner)),
        "PlannerInputBundle JSON:",
        _compact_json(bundle.model_dump(mode="json", exclude_none=True)),
    ]
    debug_findings = _debug_findings_from_effects(bundle.effects)
    if debug_findings:
        parts.extend(
            [
                "Debug findings from previous round:",
                _debug_findings_text(debug_findings),
                "If debug finding is within RunContract, prefer continue/replan instead of ask_human.",
                "Ask human only if the fix exceeds boundary or the same error repeated.",
            ]
        )
    if planner_human_response:
        parts.extend(["Planner human response JSON:", _compact_json(planner_human_response)])
    return "\n\n".join(parts)


def schema_notes_for_artifact(artifact_type: str) -> str:
    if artifact_type == "planner_order":
        return _planner_order_schema_notes()
    if artifact_type == "execution_result":
        return _execution_result_schema_notes()
    if artifact_type == "planner_decision":
        return _planner_decision_schema_notes()
    return "Return a JSON object with artifact_type set to the expected type."


def _json_only_header(artifact_type: str) -> str:
    return (
        "Return JSON only. Do not include markdown, commentary, transcript, or code fences.\n"
        f"The JSON object must have artifact_type={artifact_type!r}."
    )


def _planner_order_schema_notes() -> str:
    return (
        "Required planner_order fields: artifact_type, round, round_goal, plan_graph.\n"
        "plan_graph.work_items is a list of objects with work_item_id, merge_index, assignee_agent_id, "
        "task_summary, depends_on.\n"
        "Do not include legacy review-agent workflow fields."
    )


def _execution_result_schema_notes() -> str:
    return (
        "Required execution_result fields: artifact_type, status, summary, verification.\n"
        "Allowed status values: completed, blocked. Never return failed for execution_result.\n"
        "verification.status must be one of pass, fail, blocked, skipped.\n"
        "Store all check/test evidence inside execution_result.verification.\n"
        "If verification.status is fail or blocked, execution_result.status must be blocked.\n"
        "If verification.status is skipped, include no_check_rationale or evidence_refs.\n"
        "Optional fields include proposed_changes, changed_files, created_files, deleted_files, patch_refs, "
        "outputs, unexpected_issues, out_of_contract, needs_planner_decision, blocker_type, "
        "planner_question, candidate_options, planner_options, continue_without_human_possible, "
        "attempted_actions, evidence_refs, remaining_work, no_op_rationale.\n"
        "Allowed blocker_type values: technical_blocker, ambiguity, scope_boundary, risk_boundary, "
        "dependency_missing, context_missing, plan_conflict, schema_validation_failed, permission_blocked, "
        "verification_failed, tool_error, unsafe_action, transient_error_exhausted, command_unavailable, "
        "patch_rejected, out_of_contract.\n"
        "candidate_options is a list of objects with option_id, summary, risk_level, and requires_human."
    )


def _planner_decision_schema_notes() -> str:
    return (
        "Required planner_decision fields: artifact_type, task_done, next_action, reason.\n"
        "Allowed next_action values: continue, ask_human, finish, stop.\n"
        "If next_action is ask_human, include human_message."
    )


def _workflow_summary(agent_workflow: AgentWorkflowSpec) -> dict[str, Any]:
    return {
        "id": agent_workflow.id,
        "primary_planner_id": agent_workflow.primary_planner_id,
        "agents": [_agent_summary(agent) for agent in agent_workflow.agents],
        "edges": [
            edge.model_dump(mode="json", by_alias=True, exclude_none=True)
            for edge in agent_workflow.edges
        ],
    }


def _agent_summary(agent: AgentWorkflowAgent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "model_tier": agent.model_tier,
        "capabilities": agent.capabilities,
        "can_talk_to_human": agent.can_talk_to_human,
    }


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)[:8000]


def _debug_findings_from_effects(effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        effect
        for effect in effects
        if isinstance(effect, dict) and effect.get("effect_type") == "debug_finding"
    ]


def _debug_findings_text(findings: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for finding in findings[:8]:
        likely_files = finding.get("likely_files")
        lines.append(
            "- work_item_id={work_item_id}; failure_summary={failure_summary}; likely_files={likely_files}; raw_output_ref={raw_output_ref}".format(
                work_item_id=str(finding.get("work_item_id") or ""),
                failure_summary=str(finding.get("failure_summary") or ""),
                likely_files=", ".join(str(item) for item in likely_files) if isinstance(likely_files, list) else "",
                raw_output_ref=str(finding.get("raw_output_ref") or finding.get("output_ref") or ""),
            )
        )
    return "\n".join(lines)


def _symbol_index_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    files = value.get("files") if isinstance(value.get("files"), list) else []
    return {
        "artifact_type": value.get("artifact_type", "symbol_index"),
        "parser": value.get("parser"),
        "languages": value.get("languages", []),
        "file_count": len(files),
        "files": [
            {
                "path": item.get("path"),
                "symbols": item.get("symbols", [])[:12],
            }
            for item in files[:40]
            if isinstance(item, dict)
        ],
    }
