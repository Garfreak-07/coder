# Legacy Python v2 Compatibility Path

Python/FastAPI v2 is no longer the default product path.
It is retained for `/api/v2/*` compatibility and regression coverage.

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

## Run Legacy Tests

```powershell
cd legacy-python
python -m pip install -e ".[openhands,rag]"
python -m unittest discover -s tests
python -m compileall src tests
```
