from __future__ import annotations

from typing import Any

from coder_graph_v2.core import AgentSpec, ContextPolicy
from coder_graph_v2.runtime.state import RunState, summarize_value


def build_agent_context(agent: AgentSpec, state: RunState) -> dict[str, Any]:
    """Build a compact, structured prompt context for an agent.

    Token efficiency rule: pass selected fields and summaries by default. Full
    outputs and event history are opt-in per agent.
    """

    policy = agent.context or ContextPolicy()
    keys = policy.input_keys or list(state.data.keys())
    context: dict[str, Any] = {
        "request": state.request,
        "repo_root": state.repo_root,
        "state_summaries": {},
        "state": {},
    }

    for key in keys:
        if key not in state.data:
            continue
        value = state.data[key]
        context["state_summaries"][key] = state.summaries.get(key) or summarize_value(value)
        context["state"][key] = _compact_value(value, policy)

    for key in policy.summary_keys:
        if key in state.summaries:
            context["state_summaries"][key] = state.summaries[key]

    if policy.include_event_history:
        context["events"] = [
            {"type": event.type, "node_id": event.node_id, "message": event.message}
            for event in state.events[-20:]
        ]

    return context


def estimate_tokens(value: Any) -> int:
    # Conservative approximation. The important property is consistency so the
    # runtime can compare nodes and enforce budgets.
    return max(1, len(str(value)) // 4)


def _compact_value(value: Any, policy: ContextPolicy) -> Any:
    if policy.include_full_outputs:
        return value
    if isinstance(value, str):
        return value[: policy.max_chars_per_value]
    if isinstance(value, list):
        return value[: policy.max_items_per_key]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= policy.max_items_per_key:
                break
            compact[key] = _compact_value(item, policy)
        return compact
    return value
