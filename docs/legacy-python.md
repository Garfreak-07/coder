# Legacy Python v2 Compatibility Path

Python/FastAPI v2 is no longer the default product path.
It is retained for `/api/v2/*` compatibility and regression coverage.

The legacy package is physically quarantined under `legacy-python/`:

```text
legacy-python/
  pyproject.toml
  src/coder_workbench/
  tests/
  README.md
  .env.example
```

Use Python v2 only for:

- older API clients that still call `/api/v2/*`,
- compatibility regression tests,
- investigating behavior that has not yet been retired or ported to Rust v3.

## Run Legacy Server

```powershell
cd legacy-python
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e ".[openhands]"
.\.venv\Scripts\coder-api.exe --host 127.0.0.1 --port 8876
```

## Run Frontend In v2 Compatibility Mode

```powershell
cd frontend
$env:VITE_CODER_API_VERSION="v2"
npm.cmd run dev
```

Equivalent overrides are `CODER_USE_RUST_API=0`,
`?coder_api_version=v2`, or local storage key `coder_api_version=v2`.

## Test Legacy Python

```powershell
cd legacy-python
python -m pip install -e ".[openhands,rag]"
python -m unittest discover -s tests
python -m compileall src tests
```

The `openhands` and `rag` extras are installed in CI because the legacy
compatibility suite imports OpenHands SDK/tools and optional local RAG
dependencies. Live OpenHands and LLM credentials are still optional and must
remain environment-gated.
