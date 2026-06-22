# Coder

Planner-led local AgentGraph workbench for controlled coding tasks.

Coder keeps the ordinary product path small:

```text
User request
-> Planner
-> Executor
-> Tester
-> Planner decision
```

The Planner owns global decisions and is the only agent that can ask the user.
Executors perform bounded implementation work. Testers return evidence. The
runtime passes structured artifacts instead of transcript-sized context.

## Runtime Hardening

The AgentGraph runtime now includes a hardened execution layer while preserving
the same Planner -> Executor -> Tester -> Planner authority model:

- `ActionGateway` can route low-level tool effects through an internal
  `ToolExecutionService` with ordered results, conservative concurrency,
  per-action timeout handling, structured execution events, and large result
  budgeting.
- Context construction supports artifact-aware compaction with recoverable
  external refs for oversized snippets, artifacts, and tool outputs.
- Executor and Tester harnesses support bounded self-checks and multi-stage
  artifact repair. Invalid model output becomes a Planner-visible blocked
  artifact instead of an unstructured runtime crash.
- `WaveExecutor` records per-work-item attempts, timeout/cancel evidence,
  conservative retry diagnostics, partial results, and wave-level summaries.
- Live AgentGraph runs expose pause, resume, cancel, and heartbeat control for
  long/background execution.

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
  the basic Planner -> Executor -> Tester shape, save, save as a new copy,
  import, and export.
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
  agent_engine/      Planner, code-worker, and tester engine boundary
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
  --workflow examples\workflows\coding-workbench.json `
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
- Executor and Tester agents must not ask the user directly.
- Product live Agent workflows must run through AgentGraph.
- New context, patch, command, repair, validation, plugin, and MCP behavior
  should enter through `ActionGateway`.
- Budget-affecting work should use `BudgetBroker` preflight and reservations.
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
