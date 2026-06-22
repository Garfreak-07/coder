from __future__ import annotations

from typing import Any, Callable

from coder_workbench.core.schema import AgentSpec, NodeSpec, WorkflowSpec
from coder_workbench.executors import AgentExecutor
from coder_workbench.runtime.artifact_recorder import record_agent_artifact
from coder_workbench.runtime.conditions import evaluate_condition
from coder_workbench.runtime.context import build_agent_context, build_context_packet, fit_context_to_token_budget
from coder_workbench.runtime.state import RunState, summarize_value
from coder_workbench.tools import ToolRegistry


BlockRun = Callable[[RunState, str, str | None], None]


class RuntimeNodeExecutor:
    def __init__(
        self,
        workflow: WorkflowSpec,
        nodes: dict[str, NodeSpec],
        agents: dict[str, AgentSpec],
        agent_executor: AgentExecutor,
        tools: ToolRegistry,
        block_run: BlockRun,
    ) -> None:
        self.workflow = workflow
        self.nodes = nodes
        self.agents = agents
        self.agent_executor = agent_executor
        self.tools = tools
        self.block_run = block_run

    def run_agent_node(self, state: RunState, node_id: str) -> dict[str, Any]:
        node = self.nodes[node_id]
        assert node.agent_id
        if state.agent_calls >= self.workflow.max_agent_calls:
            self.block_run(state, "max_agent_calls reached", "max_agent_calls")
            return {"status": "blocked"}
        agent = self.agents[node.agent_id]
        policy_violations = self.agent_tool_policy_violations(agent)
        if policy_violations:
            state.status = "failed"
            state.status_reason = "agent tool policy violation"
            state.status_code = "agent_tool_policy_violation"
            return {
                "status": "failed",
                "error": "agent tool policy violation",
                "policy_violations": policy_violations,
            }
        context = build_agent_context(agent, state)
        budget_remaining = state.token_budget - state.estimated_tokens_used if state.token_budget else None
        context, estimated, original_estimated, reductions = fit_context_to_token_budget(context, budget_remaining)
        projected_tokens = state.estimated_tokens_used + estimated
        packet = build_context_packet(
            agent,
            state,
            node_id=node_id,
            context=context,
            estimated_tokens=estimated,
            original_estimated_tokens=original_estimated,
            context_reductions=reductions,
        )
        state.emit(
            "agent.context_packet",
            f"Context packet for agent {agent.id}",
            node_id=node_id,
            packet=packet,
        )
        if reductions:
            state.emit(
                "budget.warning",
                "Context compacted before agent call",
                node_id=node_id,
                estimated_tokens_used=state.estimated_tokens_used,
                original_estimated_tokens=original_estimated,
                estimated_tokens=estimated,
                projected_tokens_used=projected_tokens,
                token_budget=state.token_budget,
                context_reductions=reductions,
            )
        if state.token_budget and projected_tokens > state.token_budget:
            state.emit(
                "budget.warning",
                "Estimated token budget exceeded after compaction; agent call blocked",
                node_id=node_id,
                estimated_tokens_used=state.estimated_tokens_used,
                projected_tokens_used=projected_tokens,
                estimated_tokens=estimated,
                original_estimated_tokens=original_estimated,
                token_budget=state.token_budget,
                context_reductions=reductions,
            )
            self.block_run(state, "token budget exceeded", "token_budget_exceeded")
            return {
                "status": "blocked",
                "reason": "token budget exceeded",
                "estimated_tokens": estimated,
                "projected_tokens_used": projected_tokens,
                "token_budget": state.token_budget,
            }
        state.estimated_tokens_used = projected_tokens
        state.agent_calls += 1
        state.emit("agent.called", f"Agent {agent.id} called", node_id=node_id, estimated_tokens=estimated)
        result = self.agent_executor.run(agent, context)
        artifact_result = record_agent_artifact(
            state,
            node_id,
            result,
            expected_type=agent.artifact_type,
            block_run=lambda run_state, reason: self.block_run(
                run_state,
                reason,
                "artifact_validation_failed",
            ),
        )
        if artifact_result is not None:
            result = artifact_result
            if state.status == "blocked":
                return {
                    "status": "blocked",
                    "reason": "artifact validation failed",
                }
        state.set_value(node.output_key or agent.output_key or node.id, result)
        return result

    def run_loop_node(self, state: RunState, node_id: str) -> dict[str, Any]:
        node = self.nodes[node_id]
        mode = node.loop_mode or "retry_until"
        max_iterations = node.max_iterations or 3
        loop_state = dict(state.loop_states.get(node_id, {}))
        iteration = int(loop_state.get("iteration", 0)) + 1
        current_item: Any | None = None
        should_continue = True
        break_reason: str | None = None

        if iteration == 1:
            state.emit("loop.started", f"Loop {node_id} started", node_id=node_id, mode=mode, max_iterations=max_iterations)

        if iteration > max_iterations:
            should_continue = False
            break_reason = "max_iterations"
            iteration = max_iterations
        elif mode == "for_each":
            items = state.data.get(node.items_key or "", [])
            if not isinstance(items, list):
                items = []
            if iteration > len(items):
                should_continue = False
                break_reason = "items_exhausted"
                iteration = max(0, iteration - 1)
            else:
                current_item = items[iteration - 1]
                state.set_value(node.item_key or f"{node_id}_item", current_item)
        elif node.condition:
            condition_passed = evaluate_condition(node.condition, state.data)
            if mode == "while" and not condition_passed:
                should_continue = False
                break_reason = "condition_false"
                iteration = max(0, iteration - 1)
            if mode == "retry_until" and condition_passed:
                should_continue = False
                break_reason = "condition_satisfied"
                iteration = max(0, iteration - 1)

        state.set_value(node.iteration_key or f"{node_id}_iteration", iteration)
        result = {
            "mode": mode,
            "iteration": iteration,
            "continue": should_continue,
            "should_continue": should_continue,
            "break_reason": break_reason,
            "max_iterations": max_iterations,
            "current_item": current_item,
        }
        state.loop_states[node_id] = result
        state.set_value(node.output_key or node.id, result)

        if should_continue:
            state.emit("loop.iteration.started", f"Loop {node_id} iteration {iteration} started", node_id=node_id, **result)
        else:
            state.emit("loop.completed", f"Loop {node_id} completed: {break_reason}", node_id=node_id, **result)
        return result

    def run_tool_node(self, state: RunState, node_id: str) -> dict[str, Any]:
        node = self.nodes[node_id]
        assert node.tool
        if state.tool_calls >= self.workflow.max_tool_calls:
            self.block_run(state, "max_tool_calls reached", "max_tool_calls")
            return {"status": "blocked"}
        state.tool_calls += 1
        args = self.resolve_inputs(node.input, state)
        tool_name = "mcp_call" if node.type == "mcp_tool" else node.tool
        capability = self.tools.capability(tool_name)
        if capability is None:
            message = f"Tool {node.tool!r} is not registered."
            state.status = "failed"
            state.status_reason = message
            state.status_code = "unknown_tool"
            return {"status": "failed", "error": message}
        if node.type == "mcp_tool":
            args = dict(args)
            args.setdefault("__mcp_tool", node.tool)
        state.emit("tool.called", f"Tool {node.tool} called", node_id=node_id, args=args, capability=capability.to_dict())
        result = self.tools.run(
            tool_name,
            args,
            {
                "repo_root": state.repo_root,
                "request": state.request,
                "data": state.data,
                "scopes": state.data.get("scopes", []),
                "node_id": node_id,
                "run_id": state.data.get("run_id"),
            },
        )
        state.emit(
            "tool.result",
            f"Tool {node.tool} returned",
            node_id=node_id,
            tool=node.tool,
            result=result,
            result_summary=summarize_value(result),
            result_status=result.get("status") if isinstance(result, dict) else None,
            result_keys=sorted(result.keys()) if isinstance(result, dict) else None,
            result_size_chars=len(str(result)),
        )
        state.set_value(node.output_key or node.id, result)
        if result.get("blocked"):
            approval_payload = dict(result)
            approval_payload.pop("message", None)
            state.emit(
                "approval.required",
                str(result.get("message") or result.get("output") or "Tool requires approval"),
                node_id=node_id,
                **approval_payload,
            )
            self.block_run(
                state,
                str(result.get("message") or "tool approval required"),
                str(result.get("approval_type") or "tool_approval_required"),
            )
        return result

    def run_human_gate(self, state: RunState, node_id: str) -> dict[str, Any]:
        node = self.nodes[node_id]
        approved = bool(
            state.data.get(f"{node_id}_approved", False)
            or state.data.get("preapprove_all", False)
            or node.input.get("auto_approve", False)
        )
        result = {
            "approved": approved,
            "reason": node.approval_reason or "Human approval gate",
            "approval_type": "human_gate",
        }
        state.set_value(node.output_key or node.id, result)
        if not approved:
            state.emit("approval.required", "Workflow paused for approval", node_id=node_id, **result)
            self.block_run(state, "approval required", "approval_required")
        return result

    def agent_tool_policy_violations(self, agent: Any) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        for tool_name in agent.tools:
            capability = self.tools.capability(tool_name)
            if capability is None:
                violations.append(
                    {
                        "code": "agent_unknown_tool",
                        "agent_id": agent.id,
                        "tool": tool_name,
                        "message": f"Agent {agent.id} declares unknown tool {tool_name!r}.",
                    }
                )
                continue
            missing = [
                permission
                for permission in capability.permissions
                if not bool(getattr(agent.permissions, permission, False))
            ]
            if missing:
                violations.append(
                    {
                        "code": "agent_tool_permission_denied",
                        "agent_id": agent.id,
                        "tool": tool_name,
                        "missing_permissions": missing,
                        "message": f"Agent {agent.id} lacks permissions for {tool_name!r}: {', '.join(missing)}.",
                    }
                )
            if capability.requires_approval and not agent.permissions.requires_approval:
                violations.append(
                    {
                        "code": "agent_tool_requires_approval",
                        "agent_id": agent.id,
                        "tool": tool_name,
                        "message": f"Agent {agent.id} declares approval-gated tool {tool_name!r} without requiring approval.",
                    }
                )
        return violations

    def resolve_inputs(self, value: Any, state: RunState) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            return state.data.get(value[1:])
        if isinstance(value, dict):
            return {key: self.resolve_inputs(item, state) for key, item in value.items()}
        if isinstance(value, list):
            return [self.resolve_inputs(item, state) for item in value]
        return value
