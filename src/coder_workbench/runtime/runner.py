from __future__ import annotations

from typing import Any

from coder_workbench.core import WorkflowSpec
from coder_workbench.executors import AgentExecutor, DefaultAgentExecutor
from coder_workbench.runtime.conditions import evaluate_condition
from coder_workbench.runtime.node_executor import RuntimeNodeExecutor
from coder_workbench.runtime.state import RunEvent, RunResult, RunState, summarize_value
from coder_workbench.tools import ToolRegistry, default_tool_registry


class WorkflowRunner:
    """Small JSON-driven workflow interpreter.

    The runner owns lifecycle and routing. RuntimeNodeExecutor owns the details
    of executing agent, tool, loop, and human-gate nodes.
    """

    def __init__(
        self,
        workflow: WorkflowSpec,
        agent_executor: AgentExecutor | None = None,
        tools: ToolRegistry | None = None,
        event_sink: Any | None = None,
        runtime_settings: Any | None = None,
    ) -> None:
        self.workflow = workflow
        self.nodes = workflow.node_by_id()
        self.agents = workflow.agent_by_id()
        self.agent_executor = agent_executor or DefaultAgentExecutor(runtime_settings=runtime_settings)
        self.tools = tools or default_tool_registry()
        self.event_sink = event_sink
        self.node_executor = RuntimeNodeExecutor(
            workflow=self.workflow,
            nodes=self.nodes,
            agents=self.agents,
            agent_executor=self.agent_executor,
            tools=self.tools,
            block_run=lambda state, reason, code=None: self._block(state, reason, code=code),
        )

    def run(
        self,
        request: str,
        repo_root: str,
        initial_data: dict[str, Any] | None = None,
        resume_checkpoint: dict[str, Any] | None = None,
        prior_events: list[RunEvent] | None = None,
        resume_after_node: str | None = None,
    ) -> RunResult:
        state = self._create_state(request, repo_root, initial_data, resume_checkpoint, prior_events)
        if self.event_sink:
            state.set_event_sink(self.event_sink)
        state.emit("run.started", f"Workflow {self.workflow.id} {'resumed' if resume_after_node else 'started'}")

        if resume_after_node and self.nodes[resume_after_node].type == "human_gate":
            queue = self._next_nodes(state, resume_after_node)
        elif resume_after_node:
            queue = [resume_after_node]
        else:
            queue = [node.id for node in self.workflow.nodes if node.type == "start"]

        try:
            while queue and state.status == "running":
                if sum(state.visited_nodes.values()) >= self.workflow.max_steps:
                    self._block(state, "max_steps reached", code="max_steps")
                    break

                node_id = queue.pop(0)
                node = self.nodes[node_id]
                state.current_node = node_id
                state.visited_nodes[node_id] = state.visited_nodes.get(node_id, 0) + 1
                state.emit("node.started", f"Node {node_id} started", node_id=node_id, node_type=node.type)

                result = self._execute_node(state, node_id)
                state.emit(
                    "node.completed",
                    f"Node {node_id} completed",
                    node_id=node_id,
                    result_summary=summarize_value(result),
                    result_status=result.get("status") if isinstance(result, dict) else None,
                    result_keys=sorted(result.keys()) if isinstance(result, dict) else None,
                    result_size_chars=len(str(result)),
                )

                if state.status != "running":
                    break
                queue.extend(self._next_nodes(state, node_id))

            if state.status == "running":
                state.status = "completed"
            state.emit(f"run.{state.status}", f"Workflow {state.status}")
        except Exception as exc:  # pragma: no cover - boundary safety
            state.status = "failed"
            state.status_reason = str(exc)
            state.status_code = "runtime_exception"
            state.emit("run.failed", f"Workflow failed: {exc}", error=str(exc))

        return RunResult(
            status=state.status,
            data=state.data,
            summaries=state.summaries,
            artifacts=state.artifacts,
            events=state.events,
            estimated_tokens_used=state.estimated_tokens_used,
            agent_calls=state.agent_calls,
            tool_calls=state.tool_calls,
            blocked_node_id=state.current_node if state.status == "blocked" else None,
            resume_checkpoint=self._checkpoint(state) if state.status == "blocked" else None,
            status_reason=state.status_reason,
            status_code=state.status_code,
        )

    def _create_state(
        self,
        request: str,
        repo_root: str,
        initial_data: dict[str, Any] | None,
        resume_checkpoint: dict[str, Any] | None,
        prior_events: list[RunEvent] | None,
    ) -> RunState:
        state = RunState(
            workflow_id=self.workflow.id,
            request=request,
            repo_root=repo_root,
            data=dict(initial_data or {}),
            token_budget=self.workflow.token_budget,
        )
        if resume_checkpoint:
            state.data.update(resume_checkpoint.get("data", {}))
            state.summaries.update(resume_checkpoint.get("summaries", {}))
            state.visited_nodes.update(resume_checkpoint.get("visited_nodes", {}))
            state.traversed_edges.update(resume_checkpoint.get("traversed_edges", {}))
            state.loop_states.update(resume_checkpoint.get("loop_states", {}))
            state.estimated_tokens_used = int(resume_checkpoint.get("estimated_tokens_used", 0))
            state.agent_calls = int(resume_checkpoint.get("agent_calls", 0))
            state.tool_calls = int(resume_checkpoint.get("tool_calls", 0))
            state.current_node = resume_checkpoint.get("current_node")
        if prior_events:
            state.events.extend(prior_events)
        return state

    def _execute_node(self, state: RunState, node_id: str) -> dict[str, Any]:
        node = self.nodes[node_id]
        if node.type == "start":
            return {"status": "started"}
        if node.type == "end":
            state.status = "completed"
            return {"status": "completed"}
        if node.type == "agent":
            return self.node_executor.run_agent_node(state, node_id)
        if node.type in {"tool", "mcp_tool"}:
            return self.node_executor.run_tool_node(state, node_id)
        if node.type == "condition":
            result = {"passed": evaluate_condition(node.condition, state.data)}
            state.set_value(node.output_key or node.id, result)
            return result
        if node.type == "loop":
            return self.node_executor.run_loop_node(state, node_id)
        if node.type == "human_gate":
            return self.node_executor.run_human_gate(state, node_id)
        raise ValueError(f"Unsupported node type: {node.type}")

    def _next_nodes(self, state: RunState, node_id: str) -> list[str]:
        candidates = sorted(
            [edge for edge in self.workflow.edges if edge.from_node == node_id],
            key=lambda edge: edge.priority,
            reverse=True,
        )
        selected: list[str] = []
        for edge in candidates:
            edge_key = f"{edge.from_node}->{edge.to_node}:{edge.when or ''}"
            traversals = state.traversed_edges.get(edge_key, 0)
            if edge.max_traversals is not None and traversals >= edge.max_traversals:
                continue
            if not evaluate_condition(edge.when, state.data):
                continue
            state.traversed_edges[edge_key] = traversals + 1
            if edge.to_node in self.nodes and self.nodes[edge.to_node].type == "loop":
                loop_state = state.loop_states.get(edge.to_node)
                if loop_state and loop_state.get("continue"):
                    state.emit(
                        "loop.iteration.completed",
                        f"Loop {edge.to_node} iteration {loop_state.get('iteration')} completed",
                        node_id=edge.to_node,
                        **loop_state,
                    )
            selected.append(edge.to_node)
            state.emit(
                "edge.selected",
                f"{edge.from_node} -> {edge.to_node}",
                from_node=edge.from_node,
                to_node=edge.to_node,
                when=edge.when,
            )
        return selected

    def _block(self, state: RunState, reason: str, *, code: str | None = None) -> None:
        state.status = "blocked"
        state.status_reason = reason
        state.status_code = code or _status_code_from_reason(reason)
        state.emit("run.blocked", reason, node_id=state.current_node, reason=reason, code=state.status_code)

    def _checkpoint(self, state: RunState) -> dict[str, Any]:
        return {
            "data": state.data,
            "summaries": state.summaries,
            "visited_nodes": state.visited_nodes,
            "traversed_edges": state.traversed_edges,
            "loop_states": state.loop_states,
            "estimated_tokens_used": state.estimated_tokens_used,
            "agent_calls": state.agent_calls,
            "tool_calls": state.tool_calls,
            "current_node": state.current_node,
        }


def _status_code_from_reason(reason: str) -> str:
    normalized = reason.strip().lower().replace(" ", "_").replace("-", "_")
    if not normalized:
        return "blocked"
    return "".join(char for char in normalized if char.isalnum() or char == "_")[:80]


def run_workflow(
    workflow: WorkflowSpec,
    request: str,
    repo_root: str,
    initial_data: dict[str, Any] | None = None,
    event_sink: Any | None = None,
    resume_checkpoint: dict[str, Any] | None = None,
    prior_events: list[RunEvent] | None = None,
    resume_after_node: str | None = None,
    runner_factory: Any | None = None,
) -> RunResult:
    runner = runner_factory(workflow) if runner_factory else WorkflowRunner(workflow, event_sink=event_sink)
    if event_sink is not None:
        runner.event_sink = event_sink
    return runner.run(
        request=request,
        repo_root=repo_root,
        initial_data=initial_data,
        resume_checkpoint=resume_checkpoint,
        prior_events=prior_events,
        resume_after_node=resume_after_node,
    )