# Coder Architecture

Coder is an ordinary-user-first, Planner-led AgentGraph system for coding work.
The product surface is Agents, workflows, plugins, skills, and Planner
conversation. Runtime internals are compiled from those choices.

## Layers

1. Runtime Kernel: AgentGraph scheduling, dependency waves, cache, artifacts,
   context packets, token ledger, permissions, replay, and diagnostics.
2. Agent Layer: Agent identity, ordinary role card, workflow position, purpose,
   performance history, and compiled runtime profile.
3. Extensions: plugins, skills, and AgentEngine packages routed per work item.

## Human Channel

Only Planner can talk to the user. Workers, Testers, Final Testers, and other
non-Planner Agents return structured artifacts or blockers to Planner.

## Runtime Flow

```text
User goal -> Planner -> RunContract / PlannerOrder.plan_graph
AgentGraphRunner -> ContextService -> AgentRun -> AgentEngineRegistry
AgentEngine -> artifact -> PlannerInputBundle -> PlannerDecision
```

Legacy `WorkflowSpec` remains only as a compatibility and advanced preview
boundary. Product live Agent workflows use `AgentGraphRunner`.
