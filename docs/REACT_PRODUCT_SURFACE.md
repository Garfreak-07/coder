# React Product Surface

React remains the product UI. The current architecture can support the
Planner-first loop without replacing the framework.

## Primary Surfaces

Planner Chat:

- `frontend/src/features/planner-chat/PlannerChatPage.tsx`
- shows user and Planner messages
- supports Discuss and Work mode
- displays readiness, goal, open questions, acceptance criteria, risks, and
  plan draft confirmation

API adapter:

- `frontend/src/api.ts`
- calls Rust API v3 directly
- maps backend Planner sessions and turns into frontend task state
- sends plan context into `/api/v3/runs`
- contains no v2/Python runtime switch

Run timeline and evidence:

- `frontend/src/runEvents.tsx`
- renders events, artifacts, tool results, blob-backed output, and final report
  artifacts

Run summary and approval prompts:

- `frontend/src/App.tsx`
- recognizes `approval.requested` and `approval.required`
- shows blocked run state, approval type, command preview when present, and
  run details

Workflow canvas:

- `frontend/src/features/agent-workflow/*`
- keeps Agent and workflow editing as a simple user-facing canvas
- maps canvas state to Rust `ProjectConfig`, `AgentSpec`, `HarnessSpec`, and
  `WorkflowSpec`

## UI Boundary

Ordinary UI should show user-language concepts:

- Planner
- Executor
- Work mode
- permissions summary
- readiness
- evidence
- checks
- final report

It should not foreground internal runtime IDs, raw OpenHands events, provider
internals, token budgets, or raw backend JSON unless the user opens evidence or
debug detail.

## Current Decision

Keep React. The needed work is contract cleanup and clearer state rendering,
not a framework replacement.
