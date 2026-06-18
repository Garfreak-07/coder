# Architecture

Coder is evolving from a fixed coding assistant into a small local agent workflow workbench.

## Layers

```text
UI
  project graph
  agent canvas
  runtime timeline
  diff / rollback view

Protocol models
  AgentCard
  WorkflowSpec
  WorkflowEdge
  A2AMessage
  RuntimeEvent

Runtime
  LangGraph
  deterministic guards
  A2A-style internal messages
  human gates

Tools
  project index
  file reader
  patch generator
  check runner
  snapshot / rollback

Safety
  tool allowlist
  scope guard
  snapshot before mutation
  approval rules
```

## Why this structure

Existing tools provide useful lessons:

- AutoGen Studio: declarative agents and visual workflow editing.
- LangGraph Studio: graph-state runtime visibility.
- OpenHands: sandboxing, lifecycle control, and visible workspace matter.
- Agentless: simple localization, repair, and validation can beat over-complex agent systems.
- Flowise/Dify-style builders: node canvases are useful, but arbitrary executable nodes are a security risk.

Coder should borrow the useful parts without becoming a heavy no-code platform.

## Current protocol stance

Coder uses A2A-style internal messages first:

```json
{
  "sender": "planner",
  "recipient": "reviewer",
  "type": "plan.proposed",
  "payload": {},
  "requires_user": false
}
```

This gives the UI a clean event/message stream while keeping the runtime small. A formal A2A adapter can come later.

