# V1 Validation Results

Recorded: 2026-07-01 02:08:25 +08:00

Validation base commit before this results record: `6fc62728`.

## Required Local Commands

| Command | Result | Notes |
| --- | --- | --- |
| `cargo fmt --all --check` | Passed | Re-run after clippy cleanup. |
| `cargo clippy --workspace --all-targets -- -D warnings` | Passed | Initial run found two clippy warnings; both were fixed, then clippy passed. |
| `cargo test --workspace` | Passed | Workspace tests passed after clippy cleanup. |
| `cd frontend; npm.cmd ci` | Passed | First attempts were blocked by Windows file locks on esbuild/Rollup files. After stopping the project-local locking processes, `npm ci` passed. |
| `cd frontend; npm.cmd run test` | Passed | Frontend product-surface tests passed. |
| `cd frontend; npm.cmd run build` | Passed | TypeScript and Vite production build passed. |
| `powershell -ExecutionPolicy Bypass -File .\scripts\smoke-rust-v3.ps1 -Store .tmp\smoke-rust-v3` | Passed | Returned `status: ok`, `validation: plumbing`, `provider_test: mock`, 4 turns, completed run, 37 timeline items, completed report, 1 review changeset, and `undo_status: undone`. |
| `powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DryRun` | Passed | Windows target resolved to `x86_64-pc-windows-msvc`; no download/install performed. |
| `node packaging/npm/bin/coder-rust.js --dry-run` | Passed | Resolved local packaged binary and PATH fallback. |
| `git diff --check` | Passed | No whitespace errors. |

## Conditional Local Commands

| Command | Result | Notes |
| --- | --- | --- |
| `bash ./scripts/install.sh --dry-run` | Not run locally | `where.exe bash` reported no local bash executable on this Windows host. This remains covered by the Ubuntu `installer-dry-run` CI job. |
| `node scripts/check-rust-only-main.js` | Passed | Rust-only guard passed. |

## GitHub Actions

Latest visible `main` branch Actions result from `gh run list --repo Garfreak-07/Coder --branch main --limit 5`:

```text
completed success Record focused product validation CI main push 28403441290 1m19s 2026-06-29T21:20:25Z
```

This was the latest visible remote `main` run at validation time. The local
commits after that run had not yet been pushed when this file was written.

## Optional Live Tests

| Live test | Result | Notes |
| --- | --- | --- |
| DeepSeek live smoke | Passed | Ran with `.local-env.ps1`, `DEEPSEEK_API_KEY`, and proxy `http://127.0.0.1:7890`. Result: `status: ok`, provider `deepseek`, model `deepseek-v4-flash`, provider test `live`, 4 Planner turns, Start Work returned `needs_clarification` without starting a run. |
| OpenHands live smoke | Skipped | `scripts/live-openhands-smoke.ps1 -SkipIfMissingOpenHands` returned `status: skipped` because `OPENHANDS_LIVE_SMOKE=1` was not set. This is not a live OpenHands pass. |

## npm Audit Note

`npm.cmd ci` reported `1 low severity vulnerability` and suggested
`npm audit fix`. This did not block frontend tests or build.

## Known Blockers

No required local validation blocker remains after the clippy cleanup and npm
file-lock retry.

Known non-blocking items remain tracked in `docs/NON_BLOCKING_ENHANCEMENTS.md`.
