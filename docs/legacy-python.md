# Legacy Python Compatibility

Python/FastAPI v2 remains available as an explicit compatibility path. It is
not the default local product runtime.

## When To Use It

Use Python v2 only for:

- older API clients that still call `/api/v2/*`,
- compatibility regression tests,
- investigating behavior that has not yet been retired or ported to Rust v3.

## Run Legacy v2

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e ".[openhands]"
.\.venv\Scripts\coder-api.exe --host 127.0.0.1 --port 8876
```

Then force the frontend to use v2:

```powershell
cd frontend
$env:VITE_CODER_API_VERSION="v2"
npm.cmd run dev
```

Equivalent overrides are `CODER_USE_RUST_API=0`,
`?coder_api_version=v2`, or local storage key `coder_api_version=v2`.

## Test Legacy Python

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall src tests
```

The `openhands` extra is installed in CI because legacy OpenHands custom tool
tests import `openhands.sdk.*`. Live OpenHands and LLM credentials are still
optional and must remain environment-gated.

## Quarantine Criteria

The Python tree can move to a physical `legacy-python/` layout only after the
remaining v2-only behavior has equivalent Rust/frontend coverage or has been
retired with an explicit CI/docs contract.
