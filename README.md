# Coder

Local-first agent workflow workbench for controlled coding tasks.

Coder is moving from a fixed LangGraph prototype to a JSON-driven v2 runtime:
users define agents, nodes, edges, approvals, scopes, and context policy in a
workflow document, then run it through a FastAPI backend and React workbench UI.

Default behavior is conservative. The current v2 slice supports inspection,
planning, approval gates, dry-run patch previews, checks, event logs, and scoped
project indexing. Real file mutation is intentionally deferred until patch
proposal, approval, snapshot, apply, and rollback are implemented.

## Current v2 capabilities

- JSON workflow schema for agents, nodes, edges, and conditions.
- React + TypeScript workflow workbench with canvas, inspector, JSON editor,
  library save/load, live run launcher, and run timeline.
- FastAPI v2 runtime API with synchronous runs, live background runs, SSE
  events, file-backed run storage, and local agent/workflow library storage.
- Human approval gates with same-run approval resume:
  `POST /api/v2/live-runs/{run_id}/approve`.
- Token-conscious agent context policy and estimated token tracking.
- Project scope selection and path guard enforcement for v2 tools.
- Built-in v2 tools:
  - `project_index`
  - `recommend_modules`
  - `dry_run_patch`
  - `run_check`
- Compatibility path for the older `langgraph-coder` CLI and module map.

See [docs/requirements.md](docs/requirements.md) for the product direction and
roadmap.

## Install

```powershell
cd F:\bbb\coder
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

Frontend dependencies are in `frontend/`:

```powershell
cd frontend
npm install
```

## Run the v2 API

```powershell
coder-v2-api --host 127.0.0.1 --port 8876
```

If `frontend/dist` exists, the API serves it from:

```text
http://127.0.0.1:8876
```

## Run the frontend in development

```powershell
cd frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Vite proxies `/api/*` to the v2 API on port `8876`.

## Run a v2 workflow from the CLI

```powershell
langgraph-coder --repo . `
  --scope src `
  --v2-workflow examples\workflows_v2\coding-workbench.json `
  --request "Inspect runtime safety"
```

Use `--v2-approve` to pre-approve human gates for CLI/debug runs.

## API keys and local secrets

Do not commit API keys or local secrets. Copy `.env.example` to `.env` for local
model configuration. `.env` is ignored by Git.

Supported provider configuration is OpenAI-compatible and remains optional; when
credentials are missing, the v2 runtime uses a mock executor for safe local
testing.

## Legacy compatibility commands

Generate the older clickable module map:

```powershell
langgraph-coder --repo "D:\projects\some-app" --map-only --scope src
```

Serve the older single-file UI:

```powershell
coder-ui
```

The long-term product contract is the v2 JSON workflow runtime, not the old
hard-coded LangGraph flow.

## License

MIT. See [LICENSE](LICENSE).
