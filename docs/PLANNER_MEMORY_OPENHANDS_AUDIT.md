# Planner Memory OpenHands Audit

Status: complete for the local release gate.

This audit records the evidence for the Planner-first product loop, the
Planner-only long-term memory boundary, and the OpenHands-first executor
boundary.

## Planner Chat Evidence

- Planner Chat resolves runtime through
  `workflow_id -> planner node -> AgentSpec -> HarnessSpec -> model profile` in
  `crates/coder-server/src/lib.rs`:
  `resolve_planner_runtime`, `resolve_planner_node`, and
  `ensure_planner_conversation_harness`.
- The default planner node binds to `planner-conversation` with backend
  `planner-model` in `examples/coder.yaml`.
- `ensure_planner_conversation_harness` requires read-only permissions: file
  reads are allowed, while writes, commands, network, secrets, publish, commit,
  push, and deploy are denied.
- Product mode does not silently fake intelligence when the provider is missing.
  `planner_chat_product_mode_requires_configured_model_provider` proves the
  configuration-required error.
- Planner Chat turns are side-effect free and cannot start work.
  `planner_chat_discuss_mode_never_allows_execution` and
  `planner_chat_turn_does_not_start_run_and_start_work_does` prove no workflow
  run is started from chat turns.

## Planner Memory Boundary Evidence

- Project memory read requires `requested_by_role = planning_chat` in
  `load_project_memory`; `workflow_agents_cannot_read_project_memory` proves
  task execution is rejected.
- Project memory proposal requires `proposed_by_role = planning_chat` in
  `propose_project_memory_write`;
  `workflow_agents_cannot_propose_project_memory_write` proves task execution
  is rejected.
- Project memory confirmation requires `confirmed_by_role = planning_chat` in
  `confirm_project_memory_write`;
  `workflow_agents_cannot_confirm_project_memory_write` proves workflow
  supervisor and task execution roles are rejected.
- Long-term memory confirmation is also enforced in `coder-memory` by
  `ensure_memory_write_allowed`; test
  `only_planning_chat_can_confirm_long_term_memory_write` covers the library
  boundary.
- `PlanDraft.memory_proposals` is a proposal surface only. Planner Chat returns
  proposal DTOs and React displays them; persistence still requires the
  planner-only propose/confirm endpoints.
- Execution agents and execution harnesses are now config-limited to
  `workflow`/`run` memory scopes. `coder-config` tests
  `non_planner_agents_cannot_request_long_term_memory_scopes` and
  `execution_harnesses_cannot_request_long_term_memory_scopes` prevent
  reintroducing long-term scopes into non-Planner execution paths.

## Start Work Evidence

- Start Work is blocked until a structured `PlanDraft` is ready and open
  questions are resolved. Test
  `planner_chat_turn_does_not_start_run_and_start_work_does` covers the split
  between chat turn and explicit execution action.
- The run endpoint passes `plan_context` into `WorkflowRunner`;
  `run_endpoint_uses_workflow_runner_and_plan_context` covers the server
  endpoint.
- `WorkflowRunner` writes `plan_context` into `run.started`, backend context,
  OpenHands payloads, and final report checks. The final report includes
  `plan_context` summary and acceptance-criteria checks through
  `plan_context_summary` and `plan_acceptance_criteria`.
- The report preview path also reconstructs plan evidence from
  `run.started.plan_context`; `evidence_report_includes_plan_context_from_run_started`
  covers the UI-visible report preview path.

## OpenHands Boundary Evidence

- OpenHands remains the preferred execution backend when configured.
  `examples/coder.yaml` binds executor work to `openhands-code-edit`.
- Coder sends workflow, node, agent, harness, selected tools, permissions,
  memory-scope names, model refs, and plan context into the OpenHands
  conversation payload without embedding secret values.
  `openhands_payload_projects_coder_specs_without_secret_values` proves this.
- Native Rust remains fallback/preflight/evidence support. Test
  `openhands_backend_prefers_context_payload_and_has_minimal_fallback` proves
  OpenHands uses the Coder-provided context payload and only has a minimal
  fallback payload shape.
- OpenHands raw events are normalized and stored by reference rather than
  injected into reports wholesale. `openhands_backend_polls_until_terminal_and_stores_raw_refs`
  covers raw event ref persistence.

## React Path Evidence

- React exports Planner Chat as `planner-conversation` / `planner-model`, and
  task execution as OpenHands or native fallback with only `workflow`/`run`
  memory scopes. Covered by `frontend/src/workflowSpecAdapter.test.ts`.
- React sends the current workflow config to Planner Chat through
  `createRustPlannerChatSession` and per-turn config updates through
  `sendRustPlannerChatTurn`.
- React displays Planner transcript, Start Work, Codex-style timeline, Review
  Changes, approval request events, evidence-backed final summaries, and debug
  event details only behind the debug UI. Covered by the frontend source tests
  and the Vite build.
- A local API-level Planner loop smoke covered Planner Chat, Start Work,
  run events, and report preview plan-context evidence against a real
  `coder-rust server` process.

## Live Dependencies

- Live OpenHands server execution is not required for the local release gate.
  The adapter tests use local stub servers and the release checklist records a
  live OpenHands compatibility matrix as non-blocking.
- Real provider credentials are not required for deterministic CI. Product mode
  fails clearly when provider credentials are absent; mock/test mode keeps
  deterministic Planner responses for local smoke and CI.
