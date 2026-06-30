# V1 Refocus Baseline

This inventory records the current `main` state before the v1 refocus work.
It is factual only and does not introduce product changes.

## Baseline Commit

- Current commit: `c9f7bc39346a1a2134d6067c10fbfcb6e8e7f15d`
- Working tree at inspection time: clean
- Supported runtime path: Rust API v3 plus React frontend
- Historical Python/FastAPI v2 path: removed from current `main` and preserved
  only in git history at tag `pre-rust-only-legacy-v2`

## User-Facing Navigation

Default sidebar sections from `frontend/src/components/AppSidebar.tsx` and
`frontend/src/App.tsx`:

- Planner Chat
- Agent Workflow
- Settings

`Plugins & Skills` is defined as an `extensions` section but is hidden by
default. It is only shown when the developer debug UI is enabled through
`?debug=1` or `localStorage.coder_debug_ui=1`.

The default active section is Planner Chat. The Agent Workflow canvas remains
in the primary navigation today, so it is still more visible than a v1 core user
path needs.

## Planner Chat Flow

Current frontend path:

- `frontend/src/App.tsx` creates and stores a `PlannerChatSession`.
- `frontend/src/features/planner-chat/PlannerChatPage.tsx` renders the Planner
  transcript, provider setup prompt, run settings, Planner strength, `Send`, and
  `Start Work`.
- Chat turns call `sendPlannerChatTurn` in `frontend/src/api.ts`, which maps to
  `POST /api/v3/planner-chat/sessions/{session_id}/turn`.
- Chat input is disabled while a request/run action is in flight through
  `runLoading`.
- Chat turns do not start execution directly in the normal UI path.

Current backend path:

- `POST /api/v3/planner-chat/sessions` creates a session with a resolved
  planner runtime.
- `POST /api/v3/planner-chat/sessions/{session_id}/turn` appends user and
  assistant turns, updates internal plan draft/readiness/open questions, and
  emits planner events.
- Product-mode provider behavior exists when `mock_mode` is false: missing live
  provider configuration returns a setup-required Planner message instead of a
  plan draft.
- The current DTOs still use legacy mode names `discuss` and `work` internally.

## Start Work Flow

Current frontend path:

- `Start Work` is enabled only when a Planner session exists, no run is active,
  and the session task state is `ready_to_execute`.
- `startPlannerSessionWork` calls
  `POST /api/v3/planner-chat/sessions/{session_id}/start-work`.
- On a started run, the UI loads timeline and change review state and keeps the
  user in Planner Chat.

Current backend path:

- `start_planner_chat_work` reloads the session, workflow config, and planner
  runtime.
- If no plan draft exists, readiness is not ready, or open questions remain, it
  appends a normal assistant clarification and returns no run.
- If provider configuration is missing in non-mock mode, it appends a provider
  setup assistant message and returns no run.
- If ready, it builds `plan_context`, derives a task from the plan, runs
  `WorkflowRunner`, stores the run, and returns event and timeline URLs.

## Timeline And Review Endpoints

Run and timeline endpoints currently exposed by `crates/coder-server/src/lib.rs`:

- `GET /api/v3/runs`
- `POST /api/v3/runs`
- `POST /api/v3/runs/mock`
- `GET /api/v3/runs/{run_id}`
- `GET /api/v3/runs/{run_id}/events`
- `GET /api/v3/runs/{run_id}/timeline`
- `GET /api/v3/runs/{run_id}/report/preview`
- `GET /api/v3/runs/{run_id}/artifacts/{artifact_name}`
- `GET /api/v3/runs/{run_id}/repo-evidence`

Review/undo endpoints:

- `GET /api/v3/runs/{run_id}/changes`
- `GET /api/v3/runs/{run_id}/changes/{change_set_id}/diff`
- `POST /api/v3/runs/{run_id}/changes/{change_set_id}/accept`
- `POST /api/v3/runs/{run_id}/changes/{change_set_id}/undo`

Frontend rendering:

- `frontend/src/features/work-timeline/WorkTimeline.tsx` renders public
  timeline items.
- `frontend/src/features/review-changes/ReviewChangesCard.tsx` renders changes,
  diffs, accept, and undo.
- Advanced event log/final report/evidence cards are debug-only.

Undo is conservative today: it compares the current git diff with the recorded
review diff and refuses to undo when they differ.

## Provider Settings Path

Normal UI path:

- Sidebar `Settings`
- `frontend/src/components/ProviderSettingsPanel.tsx`
- `frontend/src/hooks/useProviderSettings.ts`

Current fields/actions:

- provider select: `openai-compatible`, `deepseek`, `custom`
- model
- base URL
- password-style API key input
- mock-mode checkbox
- DeepSeek preset
- Save
- Test Provider
- Refresh

Backend endpoints:

- `GET /api/v3/providers/settings`
- `POST /api/v3/providers/settings`
- `GET /api/v3/providers/status`
- `POST /api/v3/providers/test`

Current secret handling:

- API keys are stored in server memory.
- `ProviderKeyState.secret` is skipped during serialization.
- Settings/status responses expose configured/source state, not plaintext keys.
- Environment fallback remains available through provider-specific env vars,
  `CODER_API_KEY`, and `LLM_API_KEY`.

Important current caveat:

- `ProviderSettings::default()` has `mock_mode: true`. The UI still shows a
  setup-required banner when default credentials are missing, but backend
  Planner turns can use deterministic fallback while mock mode is enabled.

## Plugins And Skills UI Status

The React Plugins & Skills page exists under:

- `frontend/src/features/plugins/`
- `frontend/src/features/skills/`

The page is not in the default sidebar. It is debug-only through the
`extensions` section when the debug UI flag is enabled.

Backend APIs remain available for experimental/developer use:

- extension/plugin list and validation
- plugin marketplace list/add/remove/upgrade
- installed plugin reads
- skill install/update/enable/disable/pin/remove/rollback
- skill extra roots
- hooks
- cache status

`docs/PLUGIN_AND_SKILLS_PAGE.md` already states that the marketplace UI is
deferred from the core Planner/Executor path.

## Mock Vs Live Tests

CI currently runs:

- Rust fmt, clippy, and workspace tests
- frontend tests and build
- installer dry-runs
- `scripts/check-rust-only-main.js`

Mock/plumbing coverage:

- `scripts/smoke-rust-v3.ps1` starts the Rust server and exercises workflow
  save/load, preview, `/api/v3/runs/mock`, events, report preview, artifact
  fetch, and repo evidence.
- Rust tests cover deterministic Planner sessions, mock run behavior, MCP mock
  baselines, timeline projection, and review/undo round trips.

Live/product-path coverage:

- `scripts/live-llm-smoke.ps1` is opt-in and uses a configured provider key.
- Rust tests include an OpenAI-compatible local test server for Planner provider
  behavior and a no-provider product-mode block case.
- No paid/live DeepSeek or live OpenHands smoke is required by default CI.

## Old Python And Legacy Remnants

Current `main` does not contain the removed Python/FastAPI v2 implementation.
The guard script checks for:

- `legacy-python`
- root `pyproject.toml`
- frontend v2 API switch strings
- legacy Python CI references

Remaining legacy/prototype markers are mostly documentation and naming:

- historical docs describe the removed Python/FastAPI v2 path
- frontend and backend DTOs still use `discuss`/`work` Planner mode names
- `/api/v3/runs/mock` remains for CI/smoke plumbing
- `NativeMockBackend` and local mock MCP operations remain for deterministic
  tests

## Core For V1

- Provider setup through the Settings UI
- Planner Chat as conversation and planning surface
- explicit Start Work action
- Executor work through harness-controlled WorkflowRunner
- Codex-style timeline
- Review Changes with conservative undo
- evidence-backed final reports
- Rust-only local/server runtime
- opt-in live provider smoke

## Non-Core For V1

- plugin/skill marketplace UI in the ordinary navigation
- remote marketplace sharing or publishing
- paid marketplace or cloud auth
- workflow editor as the default starting point
- mock Planner behavior as product proof
- live OpenHands compatibility matrix
- desktop packaging beyond documented plan/skeleton work
- OS keychain/local secret store beyond the documented TODO
- production embedding provider integration
