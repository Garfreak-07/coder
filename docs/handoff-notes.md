# Coder handoff notes

Use this file when starting a fresh conversation so the next agent does not
repeat solved environment/debugging work.

## Current branch and PR

- Branch: `codex-patch-safety-workbench`
- Remote branch is pushed to `origin/codex-patch-safety-workbench`
- PR: <https://github.com/Garfreak-07/Coder/pull/1>
- Latest relevant commits:
  - `5a85f93 add patch safety workflow`
  - `edd1403 remove legacy run script`

## Implemented in this branch

- Added patch tools:
  - `propose_patch`
  - `apply_patch`
  - `rollback_patch`
- Patch apply creates snapshots under `.coder_history/snapshots/<id>`.
- Rollback restores files from the snapshot manifest.
- Scope/path guard is still enforced for patch targets.
- Runtime `node.completed` events now include structured `result` payloads.
- Human approvals are gate-specific:
  - resume sets `<blocked_node_id>_approved`
  - `preapprove_all` is only for explicit full preapproval
- Frontend run panel now extracts structured event payloads and shows:
  - patch preview / diff
  - patch apply status / snapshot
  - rollback button
  - check result output
- Default coding workflow now runs:

```text
project_index
  -> recommend_modules
  -> planner agent
  -> implementation approval
  -> executor agent
  -> propose_patch
  -> patch approval
  -> apply_patch
  -> run_check
  -> reviewer agent
  -> finish
```

- `run.ps1` was deleted because it referenced the old `coder_graph` package and
  obsolete workflow files.

## Validation already run

From `F:\bbb\coder`:

```powershell
.\.venv\Scripts\python.exe -m compileall src
npm.cmd run build
```

Patch smoke test was run manually with:

- create temp file
- `propose_patch`
- `apply_patch`
- `rollback_patch`
- assert content restored

CLI workflow was run with:

```powershell
.\.venv\Scripts\coder.exe --repo . --scope src --workflow examples\workflows\coding-workbench.json --request "Inspect runtime safety" --approve
```

Browser demo was verified at:

```text
http://127.0.0.1:8876
```

No browser console errors were observed.

## Known environment pitfalls

### PowerShell blocks `npm`

`npm run build` fails in this environment because PowerShell blocks `npm.ps1`.
Use:

```powershell
npm.cmd run build
```

### GitHub DNS/login issue

At one point `github.com` resolved to:

```text
127.0.0.1
::1
```

`hosts` did not contain that mapping. Public DNS `1.1.1.1` resolved GitHub
correctly. The machine has a local proxy configured:

```text
127.0.0.1:7890
```

Use proxy env vars for `gh` commands:

```powershell
$env:HTTPS_PROXY='http://127.0.0.1:7890'
$env:HTTP_PROXY='http://127.0.0.1:7890'
```

If `gh auth status` says the token is invalid even after login, clear the stale
entry first:

```powershell
gh auth logout -h github.com -u Garfreak-07
gh auth login -h github.com -p https -w
```

In the Codex sandbox, reading/writing
`C:\Users\aixdl\AppData\Roaming\GitHub CLI\hosts.yml` may require escalated
permissions.

### Starting the local API

`Start-Process` can fail in this environment with duplicate `Path`/`PATH`
environment-key errors. Starting the demo server through a Node detached process
worked. Simpler foreground command:

```powershell
.\.venv\Scripts\coder-api.exe --host 127.0.0.1 --port 8876
```

Health check:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8876/api/v2/health
```

Expected tools include:

```text
apply_patch
dry_run_patch
project_index
propose_patch
recommend_modules
rollback_patch
run_check
```

## Recommended next work

Continue from `docs/requirements.md`, specifically the current near-term
roadmap:

1. Harden patch apply with conflict detection, expected-before checks, and
   binary-file rejection/handling.
2. Add command-specific approval and persisted approval audit records.
3. Add MCP tool adapter.
4. Expand provider-specific executor adapters beyond the current
   OpenAI-compatible config path.
5. Add durable run recovery for long background runs.

For the next implementation pass, start with item 1. The current patch apply
writes full file contents safely within scope, but it does not yet detect stale
base content or concurrent edits.
