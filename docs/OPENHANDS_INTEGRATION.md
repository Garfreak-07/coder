# OpenHands Integration

OpenHands is the preferred backend for full executor tool loops when an
OpenHands harness is configured. Coder owns the workflow boundary around that
backend:

- build the OpenHands conversation payload from Coder workflow, agent, harness,
  model, permission, memory, verification, and plan context
- trigger or attach to an OpenHands conversation
- poll or stream OpenHands events until a terminal status or timeout
- store raw OpenHands payloads as blob refs
- publish normalized public Coder events for the Start Work timeline
- produce an evidence-backed final report

## Raw Events

Raw OpenHands event payloads are persisted through `RunStore` large-text blob
refs. Public events carry `raw_ref` and an `openhands.raw_event` ref, but the
ordinary timeline does not include the raw JSON payload by default.

This keeps secret-like OpenHands fields and backend-specific event shapes out of
the normal chat and timeline UI while still preserving replay/debug evidence.

## Public ReAct Events

`OpenHandsHarnessBackend` maps raw events into the same public executor event
contract used by the native fallback:

- `executor.reasoning_summary`
- `executor.action_selected`
- `tool.started`
- `tool.completed`
- `observation.recorded`
- `executor.next_step`
- `executor.completed`
- `executor.blocked`
- `executor.failed`

Each public event includes workflow, node, agent, harness, backend, step, and
summary/status fields. The RunStore event envelope remains the source of the
canonical event timestamp.

## Timeline Projection

OpenHands command-shaped events also emit command timeline events:

- `command.previewed` for selected shell or terminal actions before result data
- `command.completed` for command observations with successful result data
- `command.failed` for non-zero, failed, timeout, or error statuses

OpenHands file or patch-shaped events emit `patch.applied` with a sanitized
`files` list. The server timeline projector turns these into public
`command_execution` and `file_change` items.

## Test Boundary

Normal CI uses fake OpenHands event shapes and does not require a live
OpenHands server. Live compatibility checks should remain opt-in because they
need external services and credentials.

## Optional Live Smoke

Use `scripts/live-openhands-smoke.ps1` only when a real OpenHands server is
available. The script is gated by `OPENHANDS_LIVE_SMOKE=1`; without that flag it
can report `skipped` and will not contact OpenHands.

```powershell
$env:OPENHANDS_LIVE_SMOKE="1"
$env:OPENHANDS_AGENT_SERVER_URL="http://127.0.0.1:8000"
$env:OPENHANDS_SESSION_API_KEY="..."
powershell -ExecutionPolicy Bypass -File .\scripts\live-openhands-smoke.ps1
```

The smoke creates a temporary git repository under `.tmp/`, runs a
documentation-only task through the configured `openhands` harness, and checks:

- OpenHands server health
- public ReAct timeline events such as executor, tool, command, or patch events
- raw OpenHands event refs in the run store
- final report summary
- Review Changes when the temporary repository has file changes

If the live run changes no files, Review Changes is not required. CI must keep
using fake adapter tests and must not require this live smoke.
