# Coder

Planner-led local coding workbench with a React frontend, a Rust v3 control
plane, and a Python/FastAPI v2 legacy compatibility path.

## Current Product Path

The default local product path is Rust v3. Start the Rust server, run the React
frontend, and the app uses `/api/v3/*` unless v2 is explicitly requested:

```text
User request
-> Planner Chat
-> Rust API v3 run preview / confirmation
-> WorkflowRunner
-> native Rust or OpenHands harness backend
-> stored events / evidence-backed final_report
```

The frontend keeps chat, workflow editing, extensions, and settings separate.
Planning Chat Discuss mode never starts execution. Work mode can start a Rust
run only after readiness and confirmation gates pass.

Rust v3 covers the ordinary product surface behind the same React UI:
health/capabilities, role cards, workflow validation/import/export, library
workflow storage, Planner Chat sessions and run preview/confirmation, stored
run inspection, evidence-backed reports, repo/command/patch tools,
memory/knowledge import and lexical retrieval, skills/extensions/MCP lifecycle
baselines, and provider settings without secret leakage. Python/FastAPI v2 is
kept for explicit legacy fallback and compatibility tests.

## Install

Requires Rust, Node.js, and Python 3.12 or newer for legacy compatibility
tests.

```powershell
git clone https://github.com/Garfreak-07/Coder.git
cd Coder
cd frontend
npm install
cd ..
```

Legacy Python compatibility install:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

Optional RAG dependencies:

```powershell
pip install -e .[rag]
```

OpenHands SDK compatibility tools are optional for local runtime use but are
installed for the full Python compatibility test suite:

```powershell
pip install -e .[openhands]
```

## Run Locally

Start the Rust API server on the Vite proxy port:

```powershell
cargo run -p coder-cli --bin coder-rust -- server --host 127.0.0.1 --port 8876
```

Start the frontend:

```powershell
cd frontend
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api/*` to
`http://127.0.0.1:8876`. The frontend defaults to Rust API v3.

To force the legacy Python/FastAPI v2 path for one session, start the Python
server and set one explicit v2 override:

```powershell
.\.venv\Scripts\coder-api.exe --host 127.0.0.1 --port 8876
cd frontend
$env:VITE_CODER_API_VERSION="v2"
npm.cmd run dev
```

Equivalent v2 overrides are `CODER_USE_RUST_API=0`, query string
`?coder_api_version=v2`, or browser local storage key `coder_api_version=v2`.

## Test

Python:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[openhands]"
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall src tests
```

Rust:

```powershell
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Frontend:

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
```

## Rust Track

The Rust workspace owns the default Coder control plane. The Python tree is
retained as a legacy compatibility path and is not part of the ordinary local
product run path.

Current Rust stabilization includes:

- `coder-openhands` defaults to the documented OpenHands Agent Server contract:
  `POST /conversations`, `GET/POST /conversations/{conversation_id}/events`,
  websocket `/conversations/{conversation_id}/events/socket`, and
  `Authorization: Bearer <session key>`.
- Legacy SDK-style OpenHands servers remain supported through explicit
  `openhands.api_paths` and `openhands.run_start_strategy` config.
- `coder-workflow::WorkflowRunner` dispatches `WorkflowSpec` nodes through a
  harness backend registry with native/mock and OpenHands-unavailable paths
  covered by tests.
- The React workflow adapter has tests for legacy canvas export/import through
  Rust `WorkflowSpec` data.
- The React API adapter targets Rust API v3 by default for workflow/library, run
  inspection, reports/artifacts/blobs, provider settings, skills/extensions,
  Planner Chat sessions, and run preview/confirmation while preserving explicit
  v2 fallback.

Useful Rust commands:

```powershell
cargo run -p coder-cli --bin coder-rust -- doctor
cargo run -p coder-cli --bin coder-rust -- config validate --path examples\coder.yaml
cargo run -p coder-cli --bin coder-rust -- workflow preview planner-led "summarize this repo"
cargo run -p coder-cli --bin coder-rust -- workflow run --mock planner-led "summarize this repo"
cargo run -p coder-cli --bin coder-rust -- server --host 127.0.0.1 --port 8766
```

The Rust CLI/distribution baseline is documented in
[`docs/distribution.md`](docs/distribution.md).

Use `VITE_CODER_API_VERSION=v2`, `CODER_USE_RUST_API=0`, or
`?coder_api_version=v2` only when testing the legacy Python compatibility path.

## OpenHands

OpenHands is an optional runtime provider. Without credentials or the runtime
flag, local development can use the internal fallback provider or Rust mock
workflow path.

For local OpenHands smoke tests, prefer environment variables rather than
committed files:

```powershell
$env:CODER_LLM_PROVIDER_PROFILE="deepseek-default"
$env:DEEPSEEK_API_KEY="..."
$env:LLM_API_KEY=$env:DEEPSEEK_API_KEY
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-v4-flash"
$env:CODER_ENABLE_OPENHANDS_RUNTIME="1"
```

`examples/coder.yaml` shows the explicit compatibility profile for older
SDK-style OpenHands servers.

## Migration Guardrails

- Keep the ordinary product path Planner-led and AgentGraph-based.
- Keep user interaction in `User <-> Planner`.
- Executors must not ask the user directly, commit, push, deploy, publish
  externally, or write long-term memory directly.
- Product live Agent workflows must run through AgentGraph.
- Current code facts must be grounded in repo evidence: native search/read,
  tests, logs, or diffs.
- Rust v3 is the default product path; keep v2/Python available only as an
  explicit compatibility fallback while replacement coverage is completed.
- Do not physically quarantine or delete Python until compatibility tests are
  replaced or retired and CI remains green.
- Do not migrate the license to MIT without explicit ownership/contributor
  approval in a separate license-only change.

More detailed design notes live under `docs/`.

## Secrets

Do not commit API keys or local secrets. Copy `.env.example` to `.env` for
local model configuration. `.env`, `.env.local`, and `.local-env.ps1` are
ignored by Git.

## License

License: AGPL-3.0-or-later. See [LICENSE](LICENSE).
