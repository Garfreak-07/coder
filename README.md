# Coder

Planner-led local agent workflow workbench for controlled coding tasks.

Coder is built around an AgentGraph runtime where Planner owns global decisions,
Code Worker performs bounded implementation work, Tester returns evidence, and
the runtime passes compact structured artifacts instead of transcripts.

The current architecture target is v0.9:

```text
Ordinary Agent workflow UI
-> AgentRecipe / RuntimeProfileCompiler
-> AgentGraphRunner
-> ContextService
-> AgentRun
-> AgentEngineRegistry
-> CodeWorkerEngine / Tester / Planner paths
-> structured artifacts and PlannerDecision
```

Only Planner can ask the user. Non-Planner Agents return artifacts, blockers, or
evidence to Planner.

## Repository Layout

```text
src/coder_workbench/
  agent_model/       AgentRecipe, RuntimeProfileCompiler, runtime profiles
  agent_engine/      AgentEngine specs, registry, harness validation, engines
  agent_graph/       Planner-led graph runner, scheduling, cache, merge logic
  agent_harness/     Harness loops and shared ArtifactRepairService
  coding/            Repo intelligence, PatchService, CommandService, checks
  context/           ContextService, ContextPacketV2 and TokenLedger wiring
  core/              AgentWorkflowSpec, artifacts, authority, legacy compile
  extensions/        Extension manifests, plugin/skill routing and runtime
  runtime/           Legacy WorkflowSpec interpreter and run state
  server/            FastAPI app, storage, live run managers
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
-> GraphRunCache
-> AgentTaskEnvelope
-> ContextService
-> AgentRun
-> AgentEngine
-> execution_result / test_result
-> PlannerInputBundle
-> PlannerDecision
```

`WorkflowSpec` and `WorkflowRunner` are legacy compatibility paths for old saved
workflows and advanced preview only. Do not add new product behavior there.

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

Legacy artifacts `plan_artifact`, `patch_artifact`, and `review_artifact` are
retained only for old `WorkflowSpec` flows.

## Key Services

- `ContextService` builds `ContextPacketV2`, selects skill context, prepares
  coding context packets, and writes token ledger entries.
- `RuntimeProfileCompiler` converts ordinary Agent roles into internal engine,
  context, token, artifact, plugin, skill, memory, repair, and tool policies.
- `AgentRun` dispatches work through `AgentEngineRegistry`.
- `PatchService` owns proposed change validation, risk path blocking, patch
  preview, apply, and rollback.
- `CommandService` owns scoped cwd validation, command approval, timeouts, and
  output capture.
- `ArtifactRepairService` owns one-shot JSON artifact repair for model outputs.
- `ExtensionRouter` routes globally installed plugins and skills per work item.

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
- `POST /api/v2/live-agent-runs/{run_id}/planner-response`
- `GET /api/v2/extensions/plugins`
- `GET /api/v2/extensions/skills`
- `GET /api/v2/extensions/search`

Legacy `/api/v2/skills/*`, `/api/v2/live-runs`, and `WorkflowSpec` endpoints
remain for compatibility. New Agent product behavior should use the AgentGraph
and Extensions endpoints.

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
- Worker, Tester, and Final Tester must not ask the user directly.
- Product live Agent workflows must not compile into legacy `WorkflowSpec`.
- New patch and command behavior should go through `PatchService` and
  `CommandService`.
- New model-output repair behavior should go through `ArtifactRepairService`.
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

## Secrets

Do not commit API keys or local secrets. Copy `.env.example` to `.env` for local
model configuration. `.env` is ignored by Git.

Provider configuration is OpenAI-compatible and optional. Without credentials,
the runtime uses mock mode for safe local development.

## License

MIT. See [LICENSE](LICENSE).
