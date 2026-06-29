# Next Phase Completion Report

## Summary

This phase moved Coder toward the Planner-first product loop:

- Discuss mode now returns real Planner conversation responses.
- Planner Chat stores structured plan draft, readiness, open questions,
  acceptance criteria, and risks.
- Work mode blocks on open questions and starts only after readiness and
  confirmation.
- `/api/v3/runs` now uses `WorkflowRunner` instead of the mock runner.
- Work mode sends structured plan context into workflow and harness execution.
- OpenHands payloads include AgentSpec, HarnessSpec, workflow/model metadata,
  permissions, memory, verification, and plan context.
- Final reports include plan acceptance criteria as report checks.
- React renders Planner readiness, open questions, acceptance criteria, risks,
  approval requests, events, evidence, and final reports.

## Deleted Or Demoted

Deleted:

- product-facing Planner placeholder response
- stale `docs/codeworker_harness_tool_loop.md`
- mock-only implementation behind `/api/v3/runs`

Demoted:

- `/api/v3/runs/mock` to test/smoke-only
- `NativeMockBackend` to deterministic CI/dev helper
- mock MCP invocation to CI/dev baseline

## Intentionally Kept

- React UI
- Rust API v3
- `WorkflowRunner`
- `HarnessSpec`
- native Rust fallback backend
- OpenHands backend
- workflow canvas
- memory/knowledge/RAG baseline
- MCP baseline
- provider settings
- run store, blob store, repo evidence, checkpoints, and final reports
- release/install tooling

## Planner Discuss Behavior

Discuss mode can answer casual questions, ask clarifying questions, and draft a
small plan. It never sets `should_start_workflow` to true. Tests assert that the
old placeholder response is absent and Discuss does not start execution.

## Work Mode Behavior

Work mode uses the current or generated plan. It blocks when open questions
remain. It starts only when readiness is `ready` and the user confirms the turn.
The run request includes original user request, Planner summary, plan draft,
acceptance criteria, risks, affected paths, and selected workflow.

## Harness Standard Coverage

Native Rust backend:

- repo find/search/read/range
- git status/diff
- command preview/run with approval
- patch preview/apply with approval
- bounded output and repo evidence refs
- evidence-backed report fields

OpenHands backend:

- receives full Coder context and plan context
- triggers/attaches conversations through external OpenHands APIs
- polls events until terminal or timeout
- stores raw OpenHands events as blob refs
- normalizes raw events into Coder events
- produces evidence-backed final reports

## React Viability

React remains viable. The work required contract cleanup and state rendering,
not a new framework. The frontend now consumes structured Planner state and
sends plan context with Work-mode execution.

## Validation

Final local validation:

- `cargo check --workspace`: passed
- `cargo fmt --all --check`: passed
- `cargo clippy --workspace --all-targets -- -D warnings`: passed
- `cargo test --workspace`: passed, with the live OpenHands smoke test still
  ignored unless explicitly enabled by environment
- `cd frontend; npm.cmd ci`: passed, with npm reporting one low-severity audit
  finding
- `cd frontend; npm.cmd run test`: passed
- `cd frontend; npm.cmd run build`: passed
- `powershell -ExecutionPolicy Bypass -File .\scripts\smoke-rust-v3.ps1 -Store .tmp\smoke-rust-v3`:
  passed with health `ok`, 7 events, and completed final report preview
- `powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DryRun`:
  passed
- `node packaging/npm/bin/coder-rust.js --dry-run`: passed
- `node scripts/check-rust-only-main.js`: passed
- `git diff --check`: passed

Not run locally:

- `bash ./scripts/install.sh --dry-run`: Bash is not available in the current
  Windows shell; keep this covered by a Unix-like local shell or CI.

## Known Limitations

- The deterministic Planner is intentionally heuristic and conservative.
- The model-backed Planner currently uses environment credentials only; saved
  provider settings store secret references but not plaintext keys.
- Approval requests render in the UI, but approve/resume action handling still
  needs a product endpoint.
- Native Rust backend is an offline/fallback execution path, not a full
  OpenHands replacement.
- Live OpenHands tests remain opt-in and environment-gated.

## Release-Hardening Tasks

- Add approve/reject/resume endpoints for pending command and patch approvals.
- Add browser-level frontend tests for the complete Discuss -> Work -> run
  timeline path.
- Improve model Planner JSON parsing when live providers are enabled.
- Add more granular final report mapping from OpenHands terminal events.
