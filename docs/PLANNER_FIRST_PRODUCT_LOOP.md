# Planner-First Product Loop

Coder's ordinary product loop starts with Planner conversation and only then
enters execution.

```text
User
-> Planner Chat
-> internal PlanDraft/readiness
-> explicit Start Work action
-> WorkflowRunner
-> role-specific HarnessSpec
-> planner-model, native Rust, or OpenHands backend
-> Codex-style timeline, approvals, evidence, file changes, checks
-> review changes / undo
-> evidence-backed final report
-> Planner-facing result summary
```

## Planner Chat

Planner Chat is conversational and side-effect free.

It can:

- answer casual questions
- ask clarifying questions
- discuss scope, risks, assumptions, and acceptance criteria
- maintain a small plan draft
- propose user/project memory updates for review
- mark readiness

It must not:

- write files
- run commands
- start a workflow
- silently write global memory
- claim execution happened

Backend contract:

- `PlannerConversationEngine::respond`
- `PlannerConversationRequest`
- `PlannerConversationResponse`
- `PlanDraft`
- `POST /api/v3/planner-chat/sessions/{id}/turn` never starts a run

Planner Chat resolves runtime from the workflow:

```text
workflow_id -> planner node -> AgentSpec -> HarnessSpec -> model profile
```

The planner node must bind to the read-only `planner-model` HarnessSpec. The
deterministic engine is only used in mock/test mode. In product mode, missing
model provider configuration returns:

```text
Configure a provider in Settings before I can plan or execute work.
```

PlanDraft includes `memory_proposals`. These are not writes. Durable project
memory requires an explicit `memory.write.proposed` event followed by a
`memory.write.confirmed` request with `confirmed_by_role = planning_chat`.
Project long-term memory reads also require `requested_by_role =
planning_chat`. Workflow supervisor and task execution roles cannot read,
propose, or confirm project long-term memory through these endpoints. The
default execution agents and execution harnesses are also config-limited to
`workflow` and `run` memory scopes; evidence-backed repo context is delivered
through tool events, evidence refs, and plan context rather than durable
project/global memory reads.

## Start Work

Start Work validates the current Planner session. It blocks when no plan exists
or open questions remain. It starts execution only when readiness is `ready` and
the user explicitly invokes:

```text
POST /api/v3/planner-chat/sessions/{id}/start-work
```

The Start Work run request carries:

- `original_user_request`
- `planner_conversation_summary`
- `plan_draft`
- `acceptance_criteria`
- `risks`
- `affected_paths`
- `selected_workflow_id`

`WorkflowRunner` records this plan context in run events, passes it into
harness backend context, projects it into OpenHands payloads, and includes plan
summary and acceptance criteria in the final report checks.

## Timeline And Review

Run events are projected through:

```text
GET /api/v3/runs/{run_id}/timeline
```

The timeline emits public items such as plan updates, executor steps, tool
calls, command execution, file changes, approvals, verification, and final
summary. It does not expose raw chain-of-thought or raw backend JSON by default.

Code changes are reviewed through:

```text
GET  /api/v3/runs/{run_id}/changes
GET  /api/v3/runs/{run_id}/changes/{change_set_id}/diff
POST /api/v3/runs/{run_id}/changes/{change_set_id}/accept
POST /api/v3/runs/{run_id}/changes/{change_set_id}/undo
```

Undo applies a reverse patch only when the current diff still matches the
recorded review diff.

## Important Files

- Backend Planner Chat: `crates/coder-server/src/lib.rs`
- Workflow execution: `crates/coder-workflow/src/lib.rs`
- Harness boundary: `crates/coder-config/src/lib.rs`,
  `crates/coder-harness/src/lib.rs`
- OpenHands client: `crates/coder-openhands/src/lib.rs`
- React Planner UI: `frontend/src/features/planner-chat/PlannerChatPage.tsx`
- React API adapter: `frontend/src/api.ts`
