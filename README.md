# Coder

Planner-led local AgentGraph workbench for controlled coding tasks.

Coder keeps the ordinary product path small:

```text
User request
-> Planner
-> Execution Engine
-> Planner decision
```

The Planner owns global decisions and is the only agent that can ask the user.
The Execution Engine performs bounded implementation work, runs allowed checks,
and returns structured verification evidence. The runtime passes structured
artifacts instead of transcript-sized context.

## Runtime Hardening

The AgentGraph runtime now includes a hardened execution layer while preserving
the Planner -> Execution Engine -> Planner authority model:

- `ActionGateway` can route low-level tool effects through an internal
  `ToolExecutionService` with ordered results, conservative concurrency,
  per-action timeout handling, structured execution events, and large result
  budgeting.
- Context construction supports artifact-aware projection and compaction.
  Oversized snippets, artifacts, and tool outputs are represented as previews
  plus `sha256:<digest>` BlobStore refs.
- The executor harness supports bounded self-checks, verification checks, and
  multi-stage artifact repair. Invalid model output becomes a Planner-visible
  blocked artifact instead of an unstructured runtime crash.
- `WaveExecutor` records per-work-item attempts, timeout/cancel evidence,
  conservative retry diagnostics, completed/blocked outcomes, and wave-level
  summaries.
- Consecutive blocked rounds are promoted to a blocked run result so the Planner
  does not loop indefinitely on the same unresolved execution blocker.
- Live AgentGraph runs expose pause, resume, cancel, and heartbeat control for
  long/background execution.

## Long Context, Storage, And Recovery

Coder uses one durable path for large text:

- `BlobStore` stores full large strings by `sha256:<digest>` id.
- Context packets live in `ContextPacketStore`; tool results live in
  `ToolResultStore`.
- Events store summary, id/ref, status, and size, not full packets or large
  tool output.
- `ContextService` remains the public context construction entrypoint. Its
  private projection chooses hot/warm/cold context before `ContextCompactor`
  shrinks selected fields.
- `RunResult.resume_checkpoint` is the active recovery path for interrupted
  AgentGraph runs. Reloaded queued/running live runs with checkpoint data are
  marked `blocked` with `status_code="resume_available"`.
- `run_group_id`, `parent_run_id`, `continued_from_run_id`, and `turn_index`
  provide lightweight multi-run continuity without a parallel session store.

See [docs/runtime-storage.md](docs/runtime-storage.md) and
[docs/long-context.md](docs/long-context.md) for contributor notes.

Most low-level runtime behavior is feature-flagged during rollout:

```powershell
CODER_ENABLE_TOOL_EXECUTION_SERVICE=1
CODER_ENABLE_CONTEXT_COMPACTION=1
CODER_ENABLE_HARNESS_SELF_CHECK=1
CODER_ENABLE_WAVE_RETRY=1
```

## Current Product Surface

The app uses a ChatGPT-style left sidebar and keeps chat separate from workflow
editing:

- `Planner Chat`: send a request to the Planner, continue `ask_human` replies
  in the same composer, and inspect run status, evidence, patches, checks, and
  event logs.
- `Agent Workflow`: load saved Agent workflows, load the default workflow, edit
  the basic Planner -> Executor loop, save, save as a new copy, import, and
  export.
- `Extensions`: manage installed plugins and skills.
- `Runs`: inspect live and stored AgentGraph runs.
- `Settings`: configure the local model provider.

The ordinary product UI does not expose runtime JSON editors, workflow IDs,
agent inspectors, manual edge labels, engine settings, harness controls, or
legacy runtime previews.

## Repository Layout

```text
src/coder_workbench/
  actions/           ActionSpec and ActionGateway for controlled effects
  agent_engine/      Planner and execution engine boundary
  agent_graph/       Planner-led graph runner, scheduling, cache, merge logic
  agent_harness/     Harness loops and JSON artifact repair implementation
  budget/            BudgetBroker reservations and round preflight
  coding/            Repo intelligence, patching, command checks, diagnostics
  context/           Context packet and skill-context construction
  core/              AgentWorkflowSpec, artifacts, authority, role cards
  extensions/        Plugin and skill manifests, routing, runtime
  runtime_kernel/    RunController, RunGuard, round state, fingerprints
  server/            FastAPI app, storage, live run managers
  skills/            Installed skill store and registry client
frontend/
  src/               React + TypeScript Workbench
tests/               Python unittest suite
examples/            Example Agent workflow payloads
```

## Install

Requires Python 3.11 or newer and Node.js for the frontend.

```powershell
git clone https://github.com/Garfreak-07/Coder.git
cd Coder
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
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
  --agent-workflow examples\workflows\coding-workbench.json `
  --request "Inspect this project and propose the next safe step"
```

Use `--approve` only when you intentionally want to preapprove local effects for
a trusted run.

## API Surface

Common development endpoints:

- `GET /api/v2/health`
- `GET /api/v2/agent-role-cards`
- `GET /api/v2/agent-workflows/default`
- `POST /api/v2/agent-workflows/validate`
- `POST /api/v2/agent-workflows/runtime-profiles`
- `GET /api/v2/library`
- `POST /api/v2/library/agent-workflows`
- `GET /api/v2/library/agent-workflows/{workflow_id}`
- `POST /api/v2/live-agent-runs`
- `GET /api/v2/live-agent-runs/{run_id}`
- `GET /api/v2/live-agent-runs/{run_id}/events`
- `POST /api/v2/live-agent-runs/{run_id}/planner-response`
- `POST /api/v2/live-agent-runs/{run_id}/pause`
- `POST /api/v2/live-agent-runs/{run_id}/resume`
- `POST /api/v2/live-agent-runs/{run_id}/cancel`
- `GET /api/v2/live-agent-runs/{run_id}/heartbeat`
- `GET /api/v2/extensions/plugins`
- `GET /api/v2/extensions/skills`
- `GET /api/v2/extensions/search`

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

## Development Rules

- Keep the ordinary product path Planner-led and AgentGraph-only.
- User interaction must remain `User <-> Planner`.
- Executors must not ask the user directly.
- Executor results must include `execution_result.verification` with pass,
  skipped, failed, or blocked evidence for the Planner to judge.
- Product live Agent workflows must run through AgentGraph.
- New context, patch, command, repair, validation, plugin, and MCP behavior
  should enter through `ActionGateway`.
- Budget-affecting work should use `BudgetBroker` preflight and reservations.
- Large text should be persisted through `BlobStore`; do not add another durable
  context or tool-result ref format.
- The ordinary UI should not expose runtime JSON, engine knobs, harness graphs,
  context policies, token budgets, manual capability checklists, or advanced
  edge editing.

## Secrets

Do not commit API keys or local secrets. Copy `.env.example` to `.env` for local
model configuration. `.env` is ignored by Git.

Provider configuration is OpenAI-compatible and optional. Without credentials,
the runtime uses mock mode for safe local development.

## License

MIT. See [LICENSE](LICENSE).
