# Coder vNext Main Audit

Date: 2026-06-25

This audit records the baseline state of `main` before implementing the
Planner-led shared-state vNext work. It is based on the two local strategic
planning documents supplied by the user and the local-only handoff notes in
`.codex/handoff-notes.md`.

Do not commit or publish `.codex/handoff-notes.md`; it is local context only.

## Baseline Verification

Commands run from `F:\bbb\coder`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall src tests
```

Results:

- Backend tests: 259 tests passed.
- Python compile check: passed.

Command run from `F:\bbb\coder\frontend`:

```powershell
npm.cmd run build
```

Result:

- TypeScript/Vite build: passed.

Git state:

- Current branch: `main`.
- Working tree: clean before this audit file was added.

## Current Product And Handoff Constraints

The repository is already on the v0.4 AgentWorkflow builder track:

- Planner-led orchestrator.
- Structured artifact handoff.
- Agent-only workflow UI.
- Hidden runtime graph by default.

The current local handoff instructions require:

- Stay on `main`.
- Do not split work into multiple PRs.
- Do not open PRs unless explicitly requested.
- Commit completed work directly on `main` and push `origin/main`.
- Keep source UI text in English except translation files.

## Current Runtime Shape

The default engine registry is still intentionally small:

- `PlannerEngine`
- `CodeWorkerEngine`

Key files and entrypoints:

- `src/coder_workbench/agent_engine/registry.py`
  - `AgentEngineRegistry`
  - `default_agent_engine_registry`
- `src/coder_workbench/agent_engine/runtime.py`
  - `PlannerEngine.run_planner_order`
  - `PlannerEngine.run_planner_decision`
  - `CodeWorkerEngine.run_execution`
- `src/coder_workbench/agent_graph/agent_run.py`
  - `AgentRun.run_planner_order`
  - `AgentRun.run_execution`
  - `AgentRun.run_planner_decision`
- `src/coder_workbench/agent_graph/runner.py`
  - `AgentGraphRunner.run`
  - `AgentGraphRunner._run_round`
  - `AgentGraphRunner._start_work_item`
  - `AgentGraphRunner._record_execution_artifact`
  - `AgentGraphRunner._block_for_planner_human`
  - `AgentGraphRunner._block_for_controller`
- `src/coder_workbench/agent_graph/cache.py`
  - `GraphRunCache`
  - `GraphRunCache.as_runtime_payload`
- `src/coder_workbench/agent_graph/merge.py`
  - `build_planner_input_bundle`
  - `build_round_summary`
- `src/coder_workbench/agent_harness/execution_verification.py`
  - `ensure_execution_verification`
- `src/coder_workbench/agent_graph/memory.py`
  - `PlannerMemoryStore.record_round`
- `src/coder_workbench/actions/gateway.py`
  - `ActionGateway.run`
- `src/coder_workbench/actions/tool_execution.py`
  - `ToolExecutionService`
- `src/coder_workbench/context/service.py`
  - `ContextService`
- `src/coder_workbench/context/compaction.py`
  - `ContextCompactor`

## Existing Artifact Protocol

Currently supported normal artifact types:

- `run_contract`
- `planner_order`
- `execution_result`
- `planner_decision`
- `round_summary`

`final_report` is not present yet in:

- `PlannerArtifactType`
- `PLANNER_ARTIFACT_MODELS`
- `ArtifactType`
- `ARTIFACT_MODELS`
- frontend artifact rendering

## Current Planner Decision Semantics

`PlannerNextAction` currently allows:

- `continue`
- `ask_human`
- `finish`
- `stop`

The runner and controller still contain ordinary branches for:

- `ask_human`
- `stop`
- controller `blocked`

The normal loop also still tracks:

- `consecutive_blocked_rounds`
- `planner_human_prompt`
- `planner_human_response`

These are candidates for later normalization after `final_report` exists.

## Current Blocked Execution Semantics

`ExecutionResultArtifact` requires a blocked artifact to include:

- `blocker_type`
- at least one diagnostic signal such as unexpected issues, attempted actions,
  evidence, remaining work, checks, planner question, or candidate options

The current blocker taxonomy is legacy-oriented:

- `technical_blocker`
- `ambiguity`
- `scope_boundary`
- `risk_boundary`
- `dependency_missing`
- `context_missing`
- `plan_conflict`
- `schema_validation_failed`
- `permission_blocked`
- `verification_failed`
- `tool_error`
- `unsafe_action`
- `transient_error_exhausted`
- `command_unavailable`
- `patch_rejected`
- `out_of_contract`

The vNext blocked contract is not implemented yet.

## Current Data Plane

Good existing foundations:

- `BlobStore` for large strings.
- `ToolResultStore` for tool results.
- `ContextPacketStore` for context packets.
- compact artifact events through `AgentGraphArtifactRecorder`.
- `ContextCompactor` externalizes oversized snippets, artifacts, and tool
  outputs.

Remaining raw/internal data still appears in run result data:

- `data["graph_run_cache"] = cache.as_runtime_payload()`
- `data["token_ledger"]`

These should become debug/internal surfaces after the final report and
SharedRunState paths are available.

## Current Frontend Surface

Normal sections are:

- Planner Chat
- Agent Workflow
- Extensions
- Runs
- Settings

Planner Chat currently renders a Planner status card and an evidence area. It
does not have first-class `final_report` rendering yet.

`runEvents.tsx` can render artifact previews for:

- `run_contract`
- `planner_order`
- `execution_result`
- `planner_decision`
- `round_summary`
- legacy `plan_artifact`, `patch_artifact`, `review_artifact`

The Runs page and raw event/detail views are still in ordinary navigation and
should be hidden or made debug-only after the normal final report path exists.

## Phase 1 Entry Point

The safest first behavior change is adding `final_report` without deleting old
runtime paths:

1. Add `FinalReportArtifact` and related models.
2. Add `agent_graph/final_report.py`.
3. Build and record a final report in `AgentGraphRunner.finalize_result`.
4. Emit a compact `final_report.created` event.
5. Render `final_report` in Planner Chat and artifact previews.
6. Add tests for artifact validation, report building, runner storage, and
   compact event shape.

This preserves current passing behavior while creating the target user-facing
output path needed for later planner decision and UI simplification.
