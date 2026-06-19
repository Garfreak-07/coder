from __future__ import annotations

import json
from typing import Any, Protocol

from coder_graph.config import load_runtime_config
from coder_graph.llm import create_chat_model
from coder_graph_v2.core import AgentSpec


class AgentExecutor(Protocol):
    def run(self, agent: AgentSpec, context: dict[str, Any]) -> dict[str, Any]:
        ...


class DefaultAgentExecutor:
    """Token-conscious agent adapter.

    If credentials are available, this uses the existing OpenAI-compatible chat
    adapter. Otherwise it returns deterministic structured output so workflow
    routing can be developed and tested without spending tokens.
    """

    def run(self, agent: AgentSpec, context: dict[str, Any]) -> dict[str, Any]:
        config = load_runtime_config()
        if agent.provider:
            # Keep provider overrides explicit for future adapters. The current
            # v2 slice still uses the project's global OpenAI-compatible adapter.
            pass
        if not config.has_llm_credentials:
            return self._mock(agent, context)

        model = create_chat_model(config)
        prompt = self._build_prompt(agent, context)
        response = model.invoke(prompt)
        content = getattr(response, "content", str(response))
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict):
            return parsed
        return {
            "summary": content[:1200],
            "raw": content,
            "status": "completed",
        }

    def _build_prompt(self, agent: AgentSpec, context: dict[str, Any]) -> str:
        return "\n\n".join(
            [
                f"Role: {agent.role}",
                f"Goal: {agent.goal}",
                "Instructions:",
                agent.instructions or "Return concise structured JSON.",
                "Token policy: use the supplied summaries first. Ask for only the minimum extra context needed.",
                "Context JSON:",
                json.dumps(context, ensure_ascii=False, indent=2),
                "Return JSON only.",
            ]
        )

    def _mock(self, agent: AgentSpec, context: dict[str, Any]) -> dict[str, Any]:
        request = context.get("request", "")
        summaries = context.get("state_summaries", {})
        return {
            "status": "completed",
            "agent_id": agent.id,
            "summary": f"{agent.role} completed a dry-run response for: {request}",
            "used_summaries": sorted(summaries.keys()),
            "needs_human": agent.permissions.requires_approval and agent.permissions.edit_files,
            "recommendation": "Continue to the next workflow node if routing conditions allow.",
        }


def _try_parse_json(value: str) -> Any:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
