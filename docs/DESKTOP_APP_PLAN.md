# Desktop App Plan

Coder's first desktop app should be a thin local shell around the existing
Planner/Executor product path. The target is Tauri because Coder is Rust-first
and already has a React frontend plus Rust API v3 runtime.

## First Version

The first desktop build should bundle:

- React production build from `frontend`.
- Rust API v3 runtime as an embedded process or sidecar.
- Local `.coder/` data directory.
- Provider Settings UI.
- OS keychain or local secret store for provider API keys.
- Optional OpenHands connection settings.

Normal users should not run `cargo`, run `npm`, or set environment variables.
Opening the desktop app should start the Rust runtime automatically, load the
React UI, and keep the same core flow:

```text
Provider Settings
-> Planner Chat
-> Start Work
-> Executor through harness/OpenHands or native fallback
-> Work Timeline
-> Review Changes / Undo
-> Final Summary
```

## Runtime Shape

The first version may keep a localhost sidecar:

```text
Tauri window
-> bundled React assets
-> local Rust API v3 sidecar on 127.0.0.1
-> repository workspace and .coder/ data
```

This avoids rewriting every HTTP API into Tauri commands before the product loop
is stable. A future version may replace selected HTTP calls with direct Tauri
commands when there is a clear reliability or packaging benefit.

Current web development mode remains supported:

```powershell
cargo run -p coder-cli --bin coder-rust -- server --host 127.0.0.1 --port 8876

cd frontend
npm.cmd run dev
```

## Local Data

Desktop data should live under a local `.coder/` directory owned by the app and
the selected workspace. The expected layout is:

```text
.coder/
  runs/
  sessions/
  timeline/
  blobs/
  artifacts/
  checkpoints/
  changesets/
  repo-index/
  plugin-cache/
  skill-cache/
  openhands-events/
  logs/
  tmp/
```

Runtime data must remain disposable where possible. Reports, artifacts,
changesets, checkpoints, and evidence refs are durable user-facing records.
Temporary files, cache data, and transient OpenHands payloads can be rebuilt or
pruned.

## Secrets

Desktop release is blocked until provider API keys use OS keychain or an
equivalent local secret store. The current server-memory MVP is acceptable for
development and local smoke tests only.

Rules:

- Do not write plaintext API keys into `.coder/`.
- Do not include keys in run events, timeline items, evidence, logs, reports,
  debug exports, screenshots, or crash reports.
- Environment variables remain developer/headless fallback only.
- Provider Settings is the normal user path.

## Scope Boundaries

In scope for the first desktop path:

- start and stop local Rust runtime automatically
- load bundled React assets
- configure provider and optional OpenHands connection
- store Planner sessions and runs under `.coder/`
- preserve current localhost web dev mode

Out of scope for the first desktop path:

- broad plugin marketplace UI
- remote account sync
- cloud auth
- replacing all HTTP APIs with Tauri commands
- requiring GPU or local model acceleration
