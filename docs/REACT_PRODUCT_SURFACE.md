# React Product Surface

React remains the product UI. The current architecture can support the
Planner-first loop without replacing the framework.

## Primary Surfaces

Planner Chat:

- `frontend/src/features/planner-chat/PlannerChatPage.tsx`
- shows user and Planner messages
- keeps a single chat composer
- exposes Start Work only when the Planner session is ready
- does not show plan draft forms or readiness cards by default

API adapter:

- `frontend/src/api.ts`
- calls Rust API v3 directly
- maps backend Planner sessions and turns into frontend task state
- sends chat turns to `/planner-chat/sessions/{id}/turn`
- starts execution only through `/planner-chat/sessions/{id}/start-work`
- contains no v2/Python runtime switch

Work timeline and review:

- `frontend/src/features/work-timeline/WorkTimeline.tsx`
- `frontend/src/features/review-changes/ReviewChangesCard.tsx`
- renders public timeline items, final summary, changed files, diff, checks,
  accept, and undo

Debug evidence:

- `frontend/src/App.tsx`
- keeps raw event replay, run evidence cards, and patch panel behind
  `?debug=1` or `coder_debug_ui=1`

Workflow canvas:

- `frontend/src/features/agent-workflow/*`
- keeps Agent and workflow editing as a simple user-facing canvas
- maps canvas state to Rust `ProjectConfig`, `AgentSpec`, `HarnessSpec`, and
  `WorkflowSpec`

## UI Boundary

Ordinary UI should show user-language concepts:

- Planner
- Executor
- Start Work
- Work timeline
- Review Changes
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
