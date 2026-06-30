# Next Phase Architecture Audit

This audit is the Phase 0 checkpoint for the Planner-first product loop and
OpenHands-first harness work. It records the current Rust-only product surface
before behavior changes.

## Findings

1. Planner Chat implementation
   - Backend routes are registered in `crates/coder-server/src/lib.rs` through
     `/api/v3/planner-chat/sessions` and
     `/api/v3/planner-chat/sessions/{session_id}/turn`.
   - Backend session state is `PlannerChatSession`,
     `PlannerChatTurn`, `PlannerChatSessionCreateRequest`,
     `PlannerChatTurnRequest`, and `PlannerChatTurnResponse` in
     `crates/coder-server/src/lib.rs`.
   - Frontend chat calls are in `frontend/src/api.ts`:
     `createRustPlannerChatSession`, `sendRustPlannerChatTurn`,
     `mapRustPlannerSession`, and `mapRustPlannerTurn`.
   - UI rendering is in
     `frontend/src/features/planner-chat/PlannerChatPage.tsx`.
   - App-level state and handlers are in `frontend/src/App.tsx`:
     `plannerSession`, `sendPlannerTurn`, `startWorkFromPlannerSession`, and
     `runWorkflow`.

2. Discuss placeholder
   - The product placeholder is in `crates/coder-server/src/lib.rs`:
     `planner_chat_turn` returns
     `"Discuss mode recorded the turn without starting execution."`.
   - Work mode strings in the same handler are also status placeholders:
     `"Work mode is confirmed and ready for run creation."` and
     `"Work mode needs a ready task state and explicit confirmation before execution."`.
   - Frontend mapping in `frontend/src/api.ts` converts the backend boolean
     `ready` into a shallow `PlannerTaskState`; it does not preserve real open
     questions, plan steps, risks, or acceptance criteria from the backend.

3. Work mode implementation
   - Backend Work mode readiness is currently implemented inside
     `planner_chat_turn` using a string heuristic:
     user text containing `ready` sets `session.ready`.
   - Execution is not started by the backend Planner Chat endpoint. Instead,
     `frontend/src/api.ts` calls `/api/v3/runs` after a Planner turn if
     `execution_allowed` is true.
   - Run preview and run start are in `crates/coder-server/src/lib.rs`:
     `preview_run`, `run_workflow`, and `run_mock_workflow`.
   - Workflow execution is in `crates/coder-workflow/src/lib.rs`:
     `WorkflowRunner::run` dispatches nodes to `HarnessBackend`.

4. Planner task state and readiness representation
   - Frontend task state is represented by `PlannerTaskState` in
     `frontend/src/types.ts`, and it is carried inside the Planner session
     rather than through a separate user-facing planning flow.
   - Frontend task state type `PlannerTaskState` is in `frontend/src/types.ts`.
     It already has `goal`, `scope`, `success_criteria`, `open_questions`,
     `assumptions`, `risks`, `plan_steps`, and `readiness`.
   - Backend keeps structured plan state inside `PlannerChatSession`; the
     product path does not expose a separate planning screen.
   - Backend run requests accept `config`, `workflow_id`, and `task`; no plan
     context is passed into `WorkflowRunner` yet.

5. Endpoints powering Planner Chat UI
   - `/api/v3/planner-chat/sessions`
   - `/api/v3/planner-chat/sessions/{session_id}`
   - `/api/v3/planner-chat/sessions/{session_id}/turn`
   - `/api/v3/runs/preview`
   - `/api/v3/runs`
   - `/api/v3/runs/{run_id}`
   - `/api/v3/runs/{run_id}/events`
   - `/api/v3/runs/{run_id}/report/preview`
   - `/api/v3/runs/{run_id}/repo-evidence`
   - `/api/v3/repo-evidence/{ref_id}`
   - `/api/v3/blobs/sha256/{digest}`

6. React components and surfaces
   - Planner Chat conversation, Start Work control, timeline, and review link:
     `PlannerChatPage.tsx`.
   - App state, submit flow, Start Work flow, and run attachment:
     `App.tsx`.
   - Run timeline, artifact previews, externalized tool output, evidence refs,
     and final report preview: `runEvents.tsx`.
   - Run summary, approval prompt summary, patch panel, and run detail card:
     `App.tsx`.
   - Workflow canvas and workflow editing:
     `features/agent-workflow/AgentWorkflowPage.tsx`,
     `WorkflowSelector.tsx`, `WorkflowStructurePanel.tsx`, and
     `workflowGraph.ts`.
   - API client is centralized in `frontend/src/api.ts`; there is no live
     v2/Python API switch in the client.

7. Harness backends
   - `native-rust`: `NativeRustBackend` in `crates/coder-workflow/src/lib.rs`.
   - `native-mock`: `NativeMockBackend` in `crates/coder-workflow/src/lib.rs`.
   - `openhands`: `OpenHandsHarnessBackend` in
     `crates/coder-workflow/src/lib.rs`, using `coder-openhands`.
   - OpenHands client and event normalization are in
     `crates/coder-openhands/src/lib.rs`.
   - Harness boundary structs are `HarnessSpec`, `PermissionPolicy`,
     `VerificationPolicy`, and `OpenHandsHarnessConfig` in
     `crates/coder-config/src/lib.rs`, plus `HarnessRunRequest` and
     `HarnessRunResult` in `crates/coder-harness/src/lib.rs`.

8. Harness capability status
   - Real native capabilities exist for repo file listing, text search, file
     reads, file ranges, git status, git diff, command preview/run, patch
     preview/apply, bounded output, approval keys, and repo evidence refs in
     `crates/coder-tools/src/lib.rs`.
   - Real evidence storage and evidence-backed report construction exist in
     `crates/coder-store/src/lib.rs`.
   - Native Rust backend invokes those tools and emits evidence/report data in
     `NativeRustBackend`.
   - OpenHands backend creates/attaches conversations, sends the user message,
     triggers or starts a run, polls events until terminal or timeout,
     stores raw event refs, normalizes events, and builds an evidence-backed
     OpenHands report.
   - Placeholder or weak areas:
     - Planner Chat depends on a configured product provider for real replies.
     - Work readiness still needs stronger provider-backed task-state checks.
     - Workflow run context should continue to preserve structured Planner state.
     - Native Rust backend derives tool use from keywords in task text.
     - Approval UI shows requested approvals but has no product path to approve
       and resume a blocked action.
     - `native-mock`, MCP mock tools, and `/api/v3/runs/mock` are valid for CI
       and smoke tests but should not be presented as real product execution.

9. Mock-only public routes and surfaces
   - `/api/v3/runs/mock` is mock-only and should remain test/smoke-only.
   - `/api/v3/mcp/tools/invoke` currently invokes a local mock MCP baseline.
     It should be labeled as development/test capability until real MCP
     execution is wired.
   - Provider `mock_mode` is a local fallback setting and must not be described
     as a live model provider.
   - `MockWorkflowRunner` and `NativeMockBackend` should remain deterministic
     CI/dev helpers, not product backends.

10. Safe deletion or demotion candidates
   - Replace the Discuss placeholder and related Work placeholder strings in
     `planner_chat_turn`.
   - Remove or rewrite frontend adapter logic that fabricates Planner task
     state from a boolean when the backend returns structured Planner state.
   - Demote `/api/v3/runs/mock` from ordinary UI/product surfaces; keep it for
     smoke tests and CI.
   - Keep historical Python/FastAPI v2 docs only as archived historical docs;
     do not expose a v2 runtime switch.
   - Review `docs/RUST_FULL_COMPLETION_BLOCKERS.md`,
     `docs/RUST_FINAL_CLOSURE_CHECKLIST.md`, and other migration-completion
     docs after implementation for stale product claims.

## Keep List

- React frontend and the existing app structure.
- Rust API v3 as the only product backend.
- `WorkflowRunner` and `HarnessSpec` as the execution boundary.
- OpenHands backend as the preferred real coding-agent runtime when available.
- Native Rust backend for offline/local fallback, repo evidence, commands,
  patch preview/apply, and deterministic development.
- Run store, blob store, repo evidence, checkpoints, and final report builder.
- Workflow canvas, custom agents/workflows/harnesses, provider settings,
  memory/knowledge baseline, MCP baseline, install/release tooling, smoke
  tests, rust-only guard, MIT license, and historical v2 tag documentation.

## Delete Or Demote List

- Delete the product-facing Discuss placeholder response.
- Delete readiness-by-keyword as the product gate.
- Demote mock run and mock MCP execution from ordinary product positioning.
- Delete any new compatibility layer that only preserves placeholder contracts.
- Remove stale docs/checklists that say the current Planner-first loop is
  complete if they no longer match implementation after this phase.

## React Viability

React can complete the required UI responsibilities without framework
replacement. The current state is concentrated in `App.tsx`, `api.ts`,
`PlannerChatPage.tsx`, and `runEvents.tsx`; it needs contract cleanup and more
explicit plan/readiness/rendering fields, not a new framework.

## Implementation Direction

- Add a backend Planner conversation contract with deterministic fallback.
- Keep structured Planner task state inside Planner Chat session state.
- Make Discuss mode conversational and side-effect free.
- Make Work mode block on open questions and require confirmation.
- Pass structured plan context into workflow execution and harness context.
- Keep OpenHands as the preferred runtime for `backend = openhands`; Coder
  should build context, enforce policy, normalize events, and store evidence.
- Update React mappings to consume backend Planner state directly.
