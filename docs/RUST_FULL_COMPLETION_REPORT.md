# Rust Full Completion Report

## Final Status

- Rust v3 default product path: COMPLETE
- React default v3 API: COMPLETE
- Python v2 legacy quarantine: COMPLETE
- MCP execution baseline: COMPLETE
- Dense RAG feature-gated backend: COMPLETE
- Release/installer baseline: COMPLETE
- MIT migration: COMPLETE
- Normal CI without live APIs: COMPLETE

## Commit Range

Final blocker-closure work starts at `10db7dbe` and continues through this
report commit:

- `10db7dbe chore: quarantine legacy Python`
- `8f7e27cd feat: add MCP mock execution baseline`
- `be2d3c5e feat: add deterministic dense RAG backend`
- `ddc19d4e chore: add release and installer baseline`
- `208b9765 chore: migrate license to MIT`
- final verification/docs fix commit

## Completed Work

Rust v3 remains the default product path. The React API resolver defaults to v3;
v2 requires explicit override through env, query string, local storage, or legacy
fallback configuration.

Python/FastAPI v2 is physically quarantined under `legacy-python/`. The legacy
package remains installable and testable from that path for `/api/v2/*`
compatibility.

MCP now has a tested local mock server/client execution path:

- `GET /api/v3/mcp/servers`
- `POST /api/v3/mcp/servers/validate`
- `GET /api/v3/mcp/tools`
- `POST /api/v3/mcp/tools/invoke`

MCP calls are disabled by default and approval-required by default. Invocation
records approval, started, completed, failed, blocked, and evidence-ref events
when a `run_id` is supplied. Large output and failure evidence are blob-backed.

Dense RAG is implemented in Rust as a deterministic, config-selected backend.
`POST /api/v3/knowledge/retrieve` supports `lexical`, `dense_mock`, and
`hybrid`. Lexical remains the default. Dense/hybrid retrieval uses local
hash-vector scoring and requires no live embedding provider in CI.

Distribution now includes:

- GitHub release workflow for Linux, Windows, macOS x86_64, and macOS arm64
  archives.
- PowerShell and POSIX install scripts with dry-run mode.
- npm wrapper source under `packaging/npm`.
- Homebrew formula template under `packaging/homebrew`.
- CI installer dry-run job.

The repository license is MIT. Contributor history was checked with
`git shortlog -sne HEAD`; only owner identities were present.

## Verification Commands

Local verification completed on Windows:

- `cargo fmt --all --check`: PASS
- `cargo clippy --workspace --all-targets -- -D warnings`: PASS
- `cargo test --workspace`: PASS
- `cd legacy-python; python -m pip install -e ".[openhands,rag]"`: PASS
- `cd legacy-python; python -m unittest discover -s tests`: PASS, 704 tests
- `cd legacy-python; python -m compileall src tests`: PASS
- `cd frontend; npm.cmd ci`: PASS, npm reported 1 low-severity audit item
- `cd frontend; npm.cmd run test`: PASS
- `cd frontend; npm.cmd run build`: PASS
- `powershell -ExecutionPolicy Bypass -File .\scripts\smoke-rust-v3.ps1 -Store .tmp\smoke-rust-v3`: PASS
- `powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DryRun`: PASS
- `node packaging/npm/bin/coder-rust.js --dry-run`: PASS

`bash ./scripts/install.sh --dry-run` could not be run locally because `bash`
is not installed in this Windows environment. The command is covered by the
Ubuntu `installer-dry-run` CI job added in `.github/workflows/ci.yml`.

Live OpenHands tests were not run. They remain opt-in through:

```powershell
$env:CODER_RUN_LIVE_OPENHANDS_TESTS="1"
$env:OPENHANDS_SERVER_URL="http://127.0.0.1:8000"
cargo test -p coder-openhands openhands_real_server_contract_smoke -- --ignored
```

## CI State

Normal CI has explicit jobs for:

- Rust workspace
- Frontend build/test
- Legacy Python compatibility
- Installer dry-run

No normal CI job requires DeepSeek, OpenAI, Anthropic, Gemini, OpenHands live
server credentials, external embedding service credentials, npm publishing
tokens, or Homebrew tap write access.

## Remaining Non-Blocking Enhancements

- production embedding provider integrations
- published npm/Homebrew channels
- signed release artifacts and checksum verification
- richer MCP server compatibility matrix
- remote CI observation after pushing this final closure
