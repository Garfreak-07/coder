# Focused Product Completion Report

Generated on 2026-06-30 from local branch `main`.

## Commit Summary

| Step | Commit | Summary |
| --- | --- | --- |
| 1 | `66cfa9e6` | Cleaned Planner Chat so the thread shows real user and assistant messages, with legacy planning/status UI removed. |
| 2 | `e1b73d76` | Made Provider Settings the user-facing DeepSeek/OpenAI-compatible API-key path with redaction and test support. |
| 3 | `9b0299e3` | Routed Planner Chat through the configured provider in product mode, with deterministic fallback limited to test/mock mode. |
| 4 | `0b422eb7` | Made Start Work the only execution boundary and passed Planner context into workflow execution. |
| 5 | `517234d5` | Added public Executor ReAct lifecycle events and deterministic fallback coverage. |
| 6 | `e711c8ce` | Refined the Codex-style work timeline around public progress items instead of raw backend state. |
| 7 | `7dda9bd8` | Hardened Review Changes and Undo with quiet empty state, persisted status, and conflict-safe reverse patches. |
| 8 | `d80ecfd8` | Hid Plugins & Skills marketplace UI from core navigation and kept it behind debug/developer surfaces. |
| 9 | `23e133dc` | Added optional live LLM smoke script and documented separation from mock CI plumbing. |
| 10 | `0d89f48a` | Documented the future Tauri desktop path without rewriting current web/API mode. |
| 11 | `071f4830` | Aligned docs around the focused Planner/Executor product path. |
| 12 | this report commit | Records final validation evidence and remaining known non-blocking items. |

## Final Validation

| Command | Result | Evidence summary |
| --- | --- | --- |
| `cargo fmt --all --check` | Passed | No formatting diff reported. |
| `cargo clippy --workspace --all-targets -- -D warnings` | Passed | Checked `coder-config`, `coder-workflow`, `coder-server`, and `coder-cli` with warnings denied. |
| `cargo test --workspace` | Passed | Workspace tests passed; the live OpenHands server contract smoke remained ignored by design. |
| `cd frontend; npm.cmd ci` | Passed | Installed/audited 90 packages; npm reported 1 low severity advisory. |
| `cd frontend; npm.cmd run test` | Passed | 19 frontend adapter/product-surface tests passed. |
| `cd frontend; npm.cmd run build` | Passed | TypeScript and Vite production build passed; 217 modules transformed. |
| `powershell -ExecutionPolicy Bypass -File .\scripts\smoke-rust-v3.ps1 -Store .tmp\smoke-rust-v3` | Passed | Returned `status: ok`, `health: ok`, 7 events, completed report, and `final-report.json`. |
| `powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DryRun` | Passed | Resolved Windows archive/install target and performed no download/install. |
| `node packaging/npm/bin/coder-rust.js --dry-run` | Passed | Resolved local packaged binary and PATH fallback. |
| `git diff --check` | Passed | No whitespace errors. |
| `bash ./scripts/install.sh --dry-run` | Not run | `where.exe bash` reported no local `bash` executable on this Windows host. |
| `powershell -ExecutionPolicy Bypass -File .\scripts\live-llm-smoke.ps1 -SkipIfMissingProvider` | Skipped | No `LLM_API_KEY`, `DEEPSEEK_API_KEY`, or `CODER_API_KEY` was present in the process environment. |

## Product Evidence

- Provider setup is user-driven through Settings. Environment variables remain developer/headless fallback only.
- Planner Chat is side-effect free and LLM-backed in product mode; missing provider credentials produce setup-required assistant text.
- Chat turns do not start runs. Start Work is the explicit execution boundary.
- Executor lifecycle is represented as public ReAct summaries, actions, tool results, observations, and terminal events.
- Timeline appears only after Start Work and projects public progress items, not raw chain-of-thought or raw backend JSON.
- Review Changes appears only for actual changes and Undo requires the current diff to match the recorded review diff.
- Plugins & Skills marketplace UI is hidden from core navigation and retained only as developer/debug surface.
- Mock tests prove deterministic plumbing. The optional live LLM smoke is the product-confidence path for real provider behavior.

## GitHub Actions

GitHub Actions is visible through `gh run list --repo Garfreak-07/Coder --branch main --limit 5`.
The latest completed visible `main` run at report time was green:

```text
completed success Split planner chat from execution CI main push 28391936472 2026-06-29T17:52:24Z
```

These local focused-product commits had not yet been pushed when this report
was written, so a post-push CI run was not available inside this report.

## Live LLM Smoke

The live LLM smoke was not run against DeepSeek or another paid provider. Exact
reason: the local process environment did not contain `LLM_API_KEY`,
`DEEPSEEK_API_KEY`, or `CODER_API_KEY`. The skip path was validated and returned
`status: skipped`.

## Known Non-Blocking Items

- `npm ci` reported 1 low severity npm advisory. It did not block tests or build.
- `bash ./scripts/install.sh --dry-run` was not run locally because `bash` is not installed on this Windows host.
- Live OpenHands matrix and live LLM provider smoke remain opt-in because they require external services/credentials.
- OS keychain storage for desktop provider secrets is still required before a public desktop release.

## Known Blockers

None from the final local validation suite.
