from __future__ import annotations

from typing import Any

from coder_workbench.core import AgentWorkflowAgent, AgentWorkflowSpec, assert_valid_agent_workflow
from coder_workbench.runtime.state import RunEvent, RunResult, summarize_value


class AgentGraphRunner:
    """Phase 1 AgentWorkflow runtime boundary.

    This runner deliberately does not compile AgentWorkflowSpec into WorkflowSpec.
    Phase 2 will replace the deterministic mock plan with real PlanGraph/cache
    execution.
    """

    def __init__(
        self,
        agent_workflow: AgentWorkflowSpec,
        *,
        event_sink: Any | None = None,
        runtime_settings: Any | None = None,
    ) -> None:
        self.agent_workflow = agent_workflow
        self.event_sink = event_sink
        self.runtime_settings = runtime_settings

    def run(
        self,
        request: str,
        repo_root: str,
        initial_data: dict[str, Any] | None = None,
        resume_checkpoint: dict[str, Any] | None = None,
        prior_events: list[RunEvent] | None = None,
        resume_after_node: str | None = None,
    ) -> RunResult:
        events = list(prior_events or [])
        data = dict(initial_data or {})

        def emit(event_type: str, message: str, **payload: Any) -> None:
            event = RunEvent(type=event_type, message=message, payload=payload)
            events.append(event)
            if self.event_sink:
                self.event_sink(event)

        try:
            if resume_checkpoint or resume_after_node:
                raise ValueError("AgentGraphRunner resume is not implemented in Phase 1")

            assert_valid_agent_workflow(self.agent_workflow)
            workflow_payload = self.agent_workflow.model_dump(mode="json", by_alias=True, exclude_none=True)
            data["agent_workflow"] = workflow_payload

            emit(
                "agent_graph.run.started",
                f"Agent graph {self.agent_workflow.id} started",
                workflow_id=self.agent_workflow.id,
                repo_root=repo_root,
                request=request,
            )
            emit(
                "agent_graph.round.started",
                "Agent graph round 1 started",
                workflow_id=self.agent_workflow.id,
                round=1,
                primary_planner_id=self.agent_workflow.primary_planner_id,
            )

            planner_order = self._mock_planner_order(request)
            data["planner_order"] = planner_order
            emit(
                "planner.order.produced",
                "Planner produced a Phase 1 mock PlanGraph",
                artifact_type="planner_order",
                round=1,
                planner_order=planner_order,
            )
            emit(
                "planner.plan_cached",
                "Planner order stored in the graph run cache",
                round=1,
                work_items=len(planner_order["plan_graph"]["work_items"]),
            )

            planner_input_bundle = self._mock_planner_input_bundle(planner_order)
            data["planner_input_bundle"] = planner_input_bundle
            emit(
                "planner.input_bundle.created",
                "Compact PlannerInputBundle created",
                artifact_type="planner_input_bundle",
                round=1,
                items=len(planner_input_bundle["items"]),
            )

            round_summary = self._mock_round_summary(planner_order)
            data["round_summary"] = round_summary
            emit(
                "round_summary.created",
                "Round summary created",
                artifact_type="round_summary",
                round=1,
                plan_status=round_summary["plan_status"],
            )

            planner_decision = {
                "artifact_type": "planner_decision",
                "round": 1,
                "task_done": True,
                "next_action": "finish",
                "reason": "Phase 1 AgentGraphRunner mock-mode completed the graph boundary check.",
            }
            data["planner_decision"] = planner_decision
            emit(
                "planner.decision.produced",
                "Planner decision produced",
                artifact_type="planner_decision",
                round=1,
                next_action="finish",
            )
            emit("agent_graph.run.completed", f"Agent graph {self.agent_workflow.id} completed")
            status = "completed"
            status_reason = None
            status_code = None
        except Exception as exc:  # pragma: no cover - boundary safety
            status = "failed"
            status_reason = str(exc)
            status_code = "agent_graph_runtime_exception"
            emit("agent_graph.run.failed", f"Agent graph failed: {exc}", error=str(exc))

        return RunResult(
            status=status,
            data=data,
            summaries={key: summarize_value(value) for key, value in data.items()},
            artifacts={},
            events=events,
            estimated_tokens_used=0,
            agent_calls=0,
            tool_calls=0,
            status_reason=status_reason,
            status_code=status_code,
        )

    def _mock_planner_order(self, request: str) -> dict[str, Any]:
        work_items = []
        testers = [agent for agent in self.agent_workflow.agents if _is_tester(agent)]
        workers = [
            agent
            for agent in self.agent_workflow.agents
            if agent.id != self.agent_workflow.primary_planner_id and not _is_tester(agent)
        ]
        tester_ids = [agent.id for agent in testers]
        for index, agent in enumerate(workers, start=1):
            work_items.append(
                {
                    "work_item_id": f"{_safe_id(agent.id)}-work",
                    "order_index": index,
                    "assignee_agent_id": agent.id,
                    "task_summary": f"Phase 1 mock task for {agent.name or agent.id}.",
                    "depends_on": [],
                    "tester_agent_ids": tester_ids,
                }
            )
        return {
            "artifact_type": "planner_order",
            "round": 1,
            "round_goal": request,
            "plan_graph": {
                "work_items": work_items,
                "final_tester_agent_id": tester_ids[-1] if len(tester_ids) > 1 else None,
            },
        }

    def _mock_planner_input_bundle(self, planner_order: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_type": "planner_input_bundle",
            "round": 1,
            "planner_order_ref": "memory:planner_order:round-1",
            "plan_status": "completed",
            "items": [
                {
                    "work_item_id": item["work_item_id"],
                    "order_index": item["order_index"],
                    "task_summary": item["task_summary"],
                    "execution_status": "completed",
                    "execution_summary": "Phase 1 mock execution completed.",
                    "test_status": "pass" if item["tester_agent_ids"] else "not_requested",
                    "test_summary": "Phase 1 mock test evidence recorded." if item["tester_agent_ids"] else "",
                    "refs": [],
                }
                for item in sorted(planner_order["plan_graph"]["work_items"], key=lambda value: value["order_index"])
            ],
        }

    def _mock_round_summary(self, planner_order: dict[str, Any]) -> dict[str, Any]:
        ordered_state = [
            {
                "work_item_id": item["work_item_id"],
                "order_index": item["order_index"],
                "status": "completed",
                "summary": "Phase 1 mock item completed.",
                "refs": [],
            }
            for item in sorted(planner_order["plan_graph"]["work_items"], key=lambda value: value["order_index"])
        ]
        return {
            "artifact_type": "round_summary",
            "round": 1,
            "planner_order_ref": "memory:planner_order:round-1",
            "plan_status": "completed",
            "completed_count": len(ordered_state),
            "failed_count": 0,
            "blocked_count": 0,
            "ordered_state": ordered_state,
            "remaining_work": [],
            "carry_forward_constraints": [],
        }


def _is_tester(agent: AgentWorkflowAgent) -> bool:
    return agent.role in {"tester", "reviewer"} or any("test" in capability for capability in agent.capabilities)


def _safe_id(value: str) -> str:
    safe = "".join(char if char.isalnum() or char == "_" else "_" for char in value.strip())
    return safe or "agent"
