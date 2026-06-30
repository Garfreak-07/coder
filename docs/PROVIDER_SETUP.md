# Provider Setup

Normal users configure model access in the app UI:

1. Open `Settings`.
2. Choose one provider:
   - provider: `deepseek`
   - provider: `openai-compatible`
   - provider: `custom`
3. For DeepSeek, use:
   - base URL: `https://api.deepseek.com`
   - model: `deepseek-v4-flash`
4. Paste the provider API key into `API Key`.
5. Click `Save`.
6. Click `Test Provider`.

`deepseek-v4-pro` is also supported when the account has access to that model.
The `DeepSeek preset` button fills the DeepSeek-compatible base URL and model;
users still provide their own API key.

Planner Chat uses the configured provider in product mode. If provider
credentials are missing, the Planner returns a setup-required assistant message
instead of using a fake product response.

Mock mode is for CI and developer debugging only. It is hidden from the normal
Settings path and is not product-mode Planner behavior.

API keys are accepted by the Rust server and kept in server memory for this MVP.
The settings response only returns whether a key is configured and where it came
from. Plaintext keys must not be written into repository files, run events,
timeline items, evidence blobs, reports, debug exports, or screenshots.

Use `Clear API Key` in Settings to remove the current provider key from the
server's in-memory settings. Leaving the API key field blank during `Save`
keeps the existing key.

TODO: replace the in-memory key store with an OS keychain or local secret store
before public desktop release.

## Developer Fallback

Environment variables remain for CI, smoke tests, and headless development.
They are fallback paths, not the normal user setup path:

```powershell
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_API_KEY="..."
$env:LLM_MODEL="deepseek-v4-flash"
```

Provider-specific variables such as `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, or
`CODER_API_KEY` may also be used by developer tooling. They are fallback paths,
not the normal user setup path.

## Optional Live LLM Smoke

Mock tests prove CI-safe plumbing only. The live smoke proves the product
Planner path can call a real OpenAI-compatible provider without making CI
depend on paid credentials:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\live-llm-smoke.ps1 -SkipIfMissingProvider
```

The script starts a temporary Rust API v3 server, configures Provider Settings
in server memory, sends two Planner Chat turns, verifies chat turns do not
start execution, and calls Start Work. It returns `skipped` when no provider key
is available and `-SkipIfMissingProvider` is set.

For DeepSeek, set one of these first:

```powershell
$env:DEEPSEEK_API_KEY="..."
# or
$env:LLM_API_KEY="..."
```

The key is passed only through the current process environment or in-memory
provider settings for the temporary server. The script does not write plaintext
keys to repository files or print them.

For OpenAI or another OpenAI-compatible service, pass the provider, base URL,
model, and key env name explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\live-llm-smoke.ps1 `
  -Provider openai `
  -BaseUrl https://api.openai.com/v1 `
  -Model gpt-5.5 `
  -ApiKeyEnv OPENAI_API_KEY
```
