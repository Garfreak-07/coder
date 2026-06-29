# Next Phase Deletion Report

## Removed

| Removed path or symbol | Why unused or stale | Replacement | Validation |
|---|---|---|---|
| `docs/codeworker_harness_tool_loop.md` | Described an old `CODER_ENABLE_CODE_WORKER_TOOL_LOOP` product path that is not present in current Rust-only code. It conflicted with the OpenHands-first boundary by advertising a parallel provider-neutral execution loop. | `docs/HARNESS_CODEX_STANDARD.md` and the actual `NativeRustBackend` / `OpenHandsHarnessBackend` docs. | `rg "CODER_ENABLE_CODE_WORKER_TOOL_LOOP|CodeWorkerHarness"` now finds no product code path. |
| Planner placeholder string in `planner_chat_turn` | Product Discuss mode returned a non-conversational placeholder. | `PlannerConversationEngine`, deterministic fallback, and optional model wrapper. | Rust tests assert Discuss does not return the placeholder and never starts execution. |
| `/api/v3/runs` mock implementation path | Product run endpoint delegated to `MockWorkflowRunner`. | `/api/v3/runs` now uses `WorkflowRunner`; `/api/v3/runs/mock` remains for CI/smoke. | Rust test `run_endpoint_uses_workflow_runner_and_plan_context`. |

## Demoted

| Surface | Demotion | Reason | Validation |
|---|---|---|---|
| `/api/v3/runs/mock` | Test/smoke-only | Deterministic CI helper, not real execution. | Existing smoke script still uses it explicitly. |
| `NativeMockBackend` | CI/dev helper | Deterministic backend for tests. | Existing workflow tests use it intentionally. |
| local mock MCP operations | CI/dev baseline | Mock operations simulate MCP safety and approval behavior. | MCP tests cover disabled and approval-gated behavior. |

## Kept

- React frontend
- Workflow canvas
- custom agents/workflows/harnesses
- OpenHands backend
- native Rust backend
- memory/knowledge/RAG baseline
- MCP validation and mock baseline
- provider settings
- release/install tooling
- MIT license
- smoke tests
- rust-only guard
- historical Python/FastAPI v2 tag documentation
