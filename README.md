# Coder

Planner-led local coding workbench with a Python/FastAPI backend, React
frontend, and an additive Rust runtime track.

## Current Product Path

The working product path is still the Python application:

```text
User request
-> Planner Chat
-> AgentGraphRunner / RunController
-> HarnessRuntimeManager
-> OpenHandsRuntimeProvider or InternalFallbackProvider
-> final_report
```

The frontend keeps chat, workflow editing, extensions, and settings separate.
Planning Chat Discuss mode never starts execution. Work mode can start a live
AgentGraph run only after the Planner has a ready task state.

## Install

Requires Python 3.12 or newer and Node.js.

```powershell
git clone https://github.com/Garfreak-07/Coder.git
cd Coder
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
cd frontend
npm install
```

Optional RAG dependencies:

```powershell
pip install -e .[rag]
```

## Run Locally

Start the API:

```powershell
.\.venv\Scripts\coder-api.exe --host 127.0.0.1 --port 8876
```

Start the frontend:

```powershell
cd frontend
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api/*` to
`http://127.0.0.1:8876`.

## Test

Python:

```powershell
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

The Rust workspace is additive and does not replace the Python/FastAPI product
path yet.

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

Useful Rust commands:

```powershell
cargo run -p coder-cli --bin coder-rust -- doctor
cargo run -p coder-cli --bin coder-rust -- config validate --path examples\coder.yaml
cargo run -p coder-cli --bin coder-rust -- workflow preview planner-led "summarize this repo"
cargo run -p coder-cli --bin coder-rust -- workflow run --mock planner-led "summarize this repo"
cargo run -p coder-cli --bin coder-rust -- server --host 127.0.0.1 --port 8766
```

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
- Rust work should remain additive until the replacement path is explicitly
  validated.
- Do not move the frontend default product path to Rust by default.

More detailed design notes live under `docs/`.

## Secrets

Do not commit API keys or local secrets. Copy `.env.example` to `.env` for
local model configuration. `.env`, `.env.local`, and `.local-env.ps1` are
ignored by Git.

## License

License: AGPL-3.0-or-later. See [LICENSE](LICENSE).
