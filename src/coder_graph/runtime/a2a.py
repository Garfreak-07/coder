from __future__ import annotations

from collections import defaultdict

from coder_graph.models import A2AMessage, AgentCard


class A2ARouter:
    """Local inbox/outbox router for agent-to-agent messages."""

    def __init__(self, agents: list[AgentCard] | None = None) -> None:
        self.agents: dict[str, AgentCard] = {}
        self.inbox: dict[str, list[A2AMessage]] = defaultdict(list)
        self.outbox: dict[str, list[A2AMessage]] = defaultdict(list)
        if agents:
            self.register_agents(agents)

    def register_agents(self, agents: list[AgentCard]) -> None:
        for agent in agents:
            self.agents[agent.id] = agent
            self.inbox.setdefault(agent.id, [])
            self.outbox.setdefault(agent.id, [])

    def route(self, message: A2AMessage) -> A2AMessage:
        self.outbox[message.sender].append(message)
        self.inbox[message.recipient].append(message)
        return message

    def dump(self) -> dict:
        agent_ids = sorted(set(self.agents) | set(self.inbox) | set(self.outbox))
        return {
            agent_id: {
                "inbox": [message.model_dump(mode="json") for message in self.inbox.get(agent_id, [])],
                "outbox": [message.model_dump(mode="json") for message in self.outbox.get(agent_id, [])],
            }
            for agent_id in agent_ids
        }
