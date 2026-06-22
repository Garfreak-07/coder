# Coder

Planner-led local agent workflow workbench for controlled coding tasks.

Coder is built around an AgentGraph runtime where Planner owns global decisions,
Executor performs bounded implementation work, Tester returns evidence, and the
runtime passes compact structured artifacts instead of transcripts.

The current architecture target is v0.9.7 v1.0 convergence plan / contract freeze:

```text
Ordinary Agent workflow UI
-> AgentWorkflowSpec
-> PlannerOrder.plan_graph
-> RunController / RunGuard
-> BudgetBroker round preflight
-> GraphRunCache
-> ActionGateway
-> ContextService
-> AgentRun
-> PlannerStrategy
-> AgentEngineRegistry
-> PlannerEngine / CodeWorkerEngine / TesterEngine
-> PlannerInputBundle
-> PlannerDecision
-> RunController
```

Only Planner can ask the user. Non-Planner Agents return artifacts, blockers, or
evidence to Planner.

## Repository Layout

```text
src/coder_workbench/
  agent_model/       AgentRecipe, RuntimeProfileCompiler, runtime profiles
  actions/           ActionSpec and ActionGateway for controlled effects
  agent_engine/      AgentEngine specs, registry, harness validation, engines
  agent_graph/       Planner-led graph runner, scheduling, cache, merge logic
  agent_harness/     Harness loops and JSON artifact repair implementation
  budget/            BudgetBroker reservations before model/tool/context work
  coding/            Repo intelligence, PatchService, CommandService, checks
  context/           ContextService, ContextPacketV2 and TokenLedger wiring
  core/              AgentWorkflowSpec, artifacts, authority, role cards
  extensions/        Extension manifests, plugin/skill routing and runtime
  observability/     TraceSpan and TraceContext models
  runtime/           Run event/result/state compatibility models
  runtime_kernel/    RunController, RunGuard, round state, plan fingerprinting
  server/            FastAPI app, storage, live run managers
  server/stores/     Partitioned run events, artifacts, blobs, ledgers, cache
  skills/            Installed skill store, registry client, skill router
  tools/             Compatibility tool registry and low-level tool wrappers
frontend/
  src/               React + TypeScript workbench
tests/               Python unittest suite
docs/                Architecture and migration notes
```

## Runtime Boundary

Product Agent workflow runs use:

```text
AgentWorkflowSpec
-> PlannerOrder.plan_graph
-> RunController / RunGuard
-> BudgetBroker round preflight
-> GraphRunCache
-> ActionGateway
-> ContextService
-> AgentRun
-> PlannerStrategy
-> AgentEngineRegistry
-> Engines
-> PlannerInputBundle
-> PlannerDecision
-> RunController
```

The old workflow runtime has been physically removed from product code. Product
execution does not compile through old workflow schemas, does not run a fallback
runner, and does not expose old workflow preview endpoints. Normal product
execution uses AgentGraph directly.

## Core Artifacts

Default AgentGraph artifacts:

- `run_contract`
- `planner_order`
- `execution_result`
- `test_result`
- `planner_decision`
- `round_summary`

Coding diagnostics:

- `repo_index`
- `command_discovery`
- `risk_map`
- `symbol_index`
- `coding_context_packet`
- `patch_preview`
- `check_result`
- `debug_finding`
- `coding_evaluation_report`

Old `plan_artifact`, `patch_artifact`, and `review_artifact` outputs are not
emitted by product AgentGraph runs.

## Key Services

- `ContextService` builds `ContextPacketV2`, selects skill context, prepares
  coding context packets, and writes token ledger entries.
- `RunController` owns PlannerDecision loop control, max rounds, and repeated
  plan fingerprint guards. It also maps round budget preflight denials into
  blocked run decisions and writes run diagnostics.
- `BudgetBroker` can dry-run an upcoming round budget before scheduling executor
  waves, then reserves model, tool, and context budgets before execution.
  Preflight, reservation, and usage diagnostics are written to run results.
- `ActionGateway` is the runtime entry point for context construction, patch
  preview, sandbox patch apply, sandbox command checks, plugin, MCP, repo
  intelligence, and artifact repair/validation actions. Declared `ActionSpec`
  types must either be implemented by `ActionGateway` or absent from
  `ACTION_TYPES`. Plugin and MCP actions merge caller risk with registry
  `ToolCapability`; approval-gated or unknown operations are blocked or failed
  before execution unless explicitly approved. Executor-requested runtime actions
  are recorded as `runtime_action` effects and are never silently dropped.
- `RuntimeProfileCompiler` converts ordinary Agent roles into internal engine,
  context, token, artifact, plugin, skill, memory, repair, and tool policies.
- `RuntimeProfileCache` avoids recompiling identical workflow/extension/profile
  combinations.
- `AgentRun` dispatches PlannerOrder, Executor, Tester, and PlannerDecision work
  through `AgentEngineRegistry`.
- `PlannerStrategy` provides backend-only local planning modes: `full` uses
  `PlannerEngine`, `simple` and `single_executor` synthesize valid local
  Planner artifacts, and `replay` consumes supplied Planner artifacts.
- `PatchService` owns proposed change validation, risk path blocking, patch
  preview, apply, and rollback behind `ActionGateway`.
- `CommandService` owns scoped cwd validation, argv-based checks, shell command
  policy, command approval, timeouts, and output capture behind
  `ActionGateway`. Shell commands remain supported for compatibility but
  require approval outside sandboxed execution.
- Model-output validation and repair enter through `ActionGateway` actions;
  the repair service remains behind that gateway boundary.
- `ExtensionRouter` routes globally installed plugins and skills per work item.
- `TraceContext` attaches `trace_id`, `span_id`, and `parent_span_id` to run
  events.
- `PartitionedRunStores` provides the metadata, result, event, artifact, blob,
  ledger, context, tool-result, live-run, extension, and cache write path over
  the `.coder` layout.

## Install

Requires Python 3.11 or newer.

```powershell
git clone https://github.com/Garfreak-07/Coder.git
cd Coder
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

Install frontend dependencies:

```powershell
cd frontend
npm install
```

## Run Locally

Start the API:

```powershell
.\.venv\Scripts\coder-api.exe --host 127.0.0.1 --port 8876
```

Start the frontend dev server:

```powershell
cd frontend
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:5173
```

Vite proxies `/api/*` to `http://127.0.0.1:8876`.

If `frontend/dist` exists, the API can serve the built frontend from:

```text
http://127.0.0.1:8876
```

## CLI Example

```powershell
.\.venv\Scripts\coder.exe --repo . `
  --workflow examples\workflows\coding-workbench.json `
  --request "Build the smallest Planner-led loop"
```

Use `--approve` only for workflows that include explicit human gates or local
effects that should be preapproved.

## API Surface

Common development endpoints:

- `GET /api/v2/health`
- `GET /api/v2/agent-role-cards`
- `POST /api/v2/agent-workflows/validate`
- `POST /api/v2/agent-workflows/runtime-profiles`
- `POST /api/v2/live-agent-runs`
- `GET /api/v2/live-agent-runs/{run_id}`
- `GET /api/v2/live-agent-runs/{run_id}/events`
- `POST /api/v2/live-agent-runs/{run_id}/planner-response`
- `GET /api/v2/extensions/plugins`
- `GET /api/v2/extensions/skills`
- `GET /api/v2/extensions/search`

Old workflow create/compile/live-run endpoints are removed from the product API.
Product clients use `POST /api/v2/live-agent-runs`,
`POST /api/v2/agent-workflows/validate`, and
`POST /api/v2/agent-workflows/runtime-profiles`.

## Testing

Backend:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall src tests
```

Frontend:

```powershell
cd frontend
npm.cmd run build
```

Focused architecture boundary tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_architecture_boundaries
```

## Development Rules

- Keep the ordinary product path Agent-first.
- User interaction must remain `User <-> Planner` only.
- Executor and Tester must not ask the user directly.
- Product live Agent workflows must run through AgentGraph only.
- New context, patch, command, repair, and validation behavior should enter
  through `ActionGateway`; services such as `ContextService`, `PatchService`,
  and `CommandService` stay behind that boundary.
- Budget-affecting work should run `BudgetBroker` round preflight before
  scheduler creation, then reserve through `BudgetBroker` before execution.
- Local planner modes must still produce `planner_order`, `planner_input_bundle`,
  and `planner_decision` artifacts through the normal AgentGraph control plane;
  ordinary UI must not expose planner strategy knobs.
- New model-output validation and repair behavior should go through
  `ActionGateway` `validate_artifact` and `repair_artifact` actions.
- New Planner, Executor, Tester, and PlannerDecision execution behavior should
  enter through `AgentRun` and `AgentEngineRegistry`.
- Coding auto-loop behavior should preserve the path:
  `proposed_changes -> patch_preview -> sandbox_apply/check_result -> DebugFinding -> PlannerDecision`,
  with structured artifact refs carried in `PlannerInputBundle.effects`.
- Executor artifacts may request low-level runtime actions through
  `requested_actions`; plugin, MCP, and repo-index outputs are recorded as
  `runtime_action` effects with `tool_result_ref` / `output_ref`. Blocked
  plugin/MCP actions preserve `approval_key`, policy, original `ActionSpec`, and
  `work_item_id`; approved replay goes through `ActionGateway` without rerunning
  the executor model.
- Extensions are globally installed and routed per work item.
- Ordinary UI should not expose runtime JSON, harness graphs, context policies,
  token budgets, or manual capability checklists.

## Documentation

Architecture notes:

- [docs/architecture.md](docs/architecture.md)
- [docs/extensions.md](docs/extensions.md)
- [docs/agent-recipes.md](docs/agent-recipes.md)
- [docs/agent-engines.md](docs/agent-engines.md)
- [docs/coding-kernel.md](docs/coding-kernel.md)
- [docs/deletion-plan.md](docs/deletion-plan.md)
- [docs/release-1.0-plan.md](docs/release-1.0-plan.md)
- [docs/runtime-action-contract.md](docs/runtime-action-contract.md)
- [docs/1.0-acceptance-tests.md](docs/1.0-acceptance-tests.md)

## Secrets

Do not commit API keys or local secrets. Copy `.env.example` to `.env` for local
model configuration. `.env` is ignored by Git.

Provider configuration is OpenAI-compatible and optional. Without credentials,
the runtime uses mock mode for safe local development.

## License

MIT. See [LICENSE](LICENSE).
