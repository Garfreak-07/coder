from __future__ import annotations

from collections import deque

from coder_workbench.agent_graph.schema import PlannerOrder
from coder_workbench.core import (
    AgentWorkflowSpec,
    AgentWorkflowValidationError,
    AgentWorkflowValidationIssue,
    AgentWorkflowValidationResult,
)


def validate_planner_order(agent_workflow: AgentWorkflowSpec, planner_order: PlannerOrder) -> AgentWorkflowValidationResult:
    issues: list[AgentWorkflowValidationIssue] = []
    agent_by_id = {agent.id: agent for agent in agent_workflow.agents}
    reachable_from_planner = _reachable_agent_ids(agent_workflow, agent_workflow.primary_planner_id)
    work_item_ids = {item.work_item_id for item in planner_order.plan_graph.work_items}
    merge_index_by_value: dict[int, str] = {}
    seen_work_items: set[str] = set()

    for item in planner_order.plan_graph.work_items:
        if item.work_item_id in seen_work_items:
            issues.append(
                _issue(
                    "duplicate_work_item_id",
                    f'PlannerOrder work_item_id "{item.work_item_id}" is duplicated.',
                    "work_item",
                    item.work_item_id,
                )
            )
        seen_work_items.add(item.work_item_id)
        if item.merge_index in merge_index_by_value:
            issues.append(
                _issue(
                    "duplicate_merge_index",
                    f'PlannerOrder merge_index {item.merge_index} is used by both "{merge_index_by_value[item.merge_index]}" and "{item.work_item_id}".',
                    "work_item",
                    item.work_item_id,
                )
            )
        else:
            merge_index_by_value[item.merge_index] = item.work_item_id
        if item.assignee_agent_id not in agent_by_id:
            issues.append(
                _issue(
                    "planner_order_assignee_not_found",
                    f'PlannerOrder assigns "{item.work_item_id}" to unknown Agent "{item.assignee_agent_id}".',
                    "work_item",
                    item.work_item_id,
                )
            )
        elif item.assignee_agent_id not in reachable_from_planner:
            issues.append(
                _issue(
                    "planner_order_assignee_not_reachable",
                    f'PlannerOrder assigns "{item.work_item_id}" to an Agent outside the Planner reachable graph.',
                    "work_item",
                    item.work_item_id,
                )
            )

        reachable_from_assignee = _reachable_agent_ids(agent_workflow, item.assignee_agent_id)
        for tester_id in item.tester_agent_ids:
            if tester_id not in agent_by_id:
                issues.append(
                    _issue(
                        "planner_order_tester_not_found",
                        f'PlannerOrder references unknown tester "{tester_id}".',
                        "work_item",
                        item.work_item_id,
                    )
                )
            elif tester_id not in reachable_from_assignee:
                issues.append(
                    _issue(
                        "planner_order_tester_not_connected",
                        f'Tester "{tester_id}" is not reachable from assignee "{item.assignee_agent_id}".',
                        "work_item",
                        item.work_item_id,
                    )
                )

        for upstream_id in item.depends_on:
            if upstream_id not in work_item_ids:
                issues.append(
                    _issue(
                        "planner_order_dependency_not_found",
                        f'Work item "{item.work_item_id}" depends on unknown work item "{upstream_id}".',
                        "work_item",
                        item.work_item_id,
                    )
                )

    dependency_cycle = _dependency_cycle(planner_order)
    if dependency_cycle:
        issues.append(
            _issue(
                "planner_order_dependency_cycle",
                f"PlannerOrder depends_on must form a DAG, but found cycle: {' -> '.join(dependency_cycle)}.",
                "plan_graph",
            )
        )

    return _validation_result(issues)


def assert_valid_planner_order(agent_workflow: AgentWorkflowSpec, planner_order: PlannerOrder) -> None:
    result = validate_planner_order(agent_workflow, planner_order)
    if result.status == "error":
        raise AgentWorkflowValidationError(result)


def _reachable_agent_ids(spec: AgentWorkflowSpec, start_id: str) -> set[str]:
    graph: dict[str, list[str]] = {}
    for edge in spec.edges:
        if edge.loop:
            continue
        graph.setdefault(edge.from_agent, []).append(edge.to_agent)
    reachable: set[str] = set()
    queue: deque[str] = deque(graph.get(start_id, []))
    while queue:
        agent_id = queue.popleft()
        if agent_id in reachable:
            continue
        reachable.add(agent_id)
        queue.extend(graph.get(agent_id, []))
    return reachable


def _dependency_cycle(planner_order: PlannerOrder) -> list[str]:
    item_by_id = {item.work_item_id: item for item in planner_order.plan_graph.work_items}
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(work_item_id: str) -> list[str]:
        if work_item_id in visiting:
            try:
                start = stack.index(work_item_id)
            except ValueError:
                start = 0
            return stack[start:] + [work_item_id]
        if work_item_id in visited:
            return []
        visiting.add(work_item_id)
        stack.append(work_item_id)
        item = item_by_id.get(work_item_id)
        if item is not None:
            for upstream_id in item.depends_on:
                if upstream_id not in item_by_id:
                    continue
                cycle = visit(upstream_id)
                if cycle:
                    return cycle
        stack.pop()
        visiting.remove(work_item_id)
        visited.add(work_item_id)
        return []

    for item in planner_order.plan_graph.work_items:
        cycle = visit(item.work_item_id)
        if cycle:
            return cycle
    return []


def _validation_result(issues: list[AgentWorkflowValidationIssue]) -> AgentWorkflowValidationResult:
    status = "error" if any(issue.level == "error" for issue in issues) else "pass"
    return AgentWorkflowValidationResult(status=status, issues=issues, summary={})


def _issue(
    code: str,
    message: str,
    target_type: str,
    target_id: str | None = None,
) -> AgentWorkflowValidationIssue:
    return AgentWorkflowValidationIssue(
        level="error",
        code=code,
        message=message,
        target_type=target_type,
        target_id=target_id,
    )
