# Planner-First Product Loop

Coder's ordinary product loop starts with Planner conversation and only then
enters execution.

```text
User
-> Planner Chat in Discuss mode
-> structured PlanDraft and readiness
-> Work mode confirmation
-> WorkflowRunner
-> role-specific HarnessSpec
-> native Rust or OpenHands backend
-> events, approvals, evidence, patches, checks
-> evidence-backed final report
-> Planner-facing result summary
```

## Discuss Mode

Discuss mode is conversational and side-effect free.

It can:

- answer casual questions
- ask clarifying questions
- discuss scope, risks, assumptions, and acceptance criteria
- maintain a small plan draft
- mark readiness

It must not:

- write files
- run commands
- start a workflow
- claim execution happened

Backend contract:

- `PlannerConversationEngine::respond`
- `PlannerConversationRequest`
- `PlannerConversationResponse`
- `PlanDraft`

The deterministic engine is the no-credential fallback used by tests and local
offline development. The model-backed wrapper only attempts a live
OpenAI-compatible request when mock mode is disabled and a credential exists in
the environment.

## Work Mode

Work mode validates the current or newly generated plan. It blocks when open
questions remain. It starts execution only when readiness is `ready` and the
turn is explicitly confirmed.

The Work-mode run request carries:

- `original_user_request`
- `planner_conversation_summary`
- `plan_draft`
- `acceptance_criteria`
- `risks`
- `affected_paths`
- `selected_workflow_id`

`WorkflowRunner` records this plan context in run events, passes it into
harness backend context, projects it into OpenHands payloads, and includes plan
acceptance criteria in the final report checks.

## Important Files

- Backend Planner Chat: `crates/coder-server/src/lib.rs`
- Workflow execution: `crates/coder-workflow/src/lib.rs`
- Harness boundary: `crates/coder-config/src/lib.rs`,
  `crates/coder-harness/src/lib.rs`
- OpenHands client: `crates/coder-openhands/src/lib.rs`
- React Planner UI: `frontend/src/features/planner-chat/PlannerChatPage.tsx`
- React API adapter: `frontend/src/api.ts`
