# v1.0-rc.1 Release Notes

## Scope

v1.0-rc.1 is the Planner-led AgentGraph release candidate. It freezes the
v1.0 runtime contract around the ordinary product path:

```text
AgentWorkflowSpec
-> PlannerOrder.plan_graph
-> RunController / RunGuard
-> BudgetBroker round preflight
-> GraphRunCache
-> ActionGateway
-> ContextService
-> AgentRun
-> PlannerStrategy
-> AgentEngineRegistry
-> Engines
-> PlannerInputBundle
-> PlannerDecision
-> RunController
```

The release candidate tag is:

```text
v1.0-rc.1 -> 938aac3 test: lock legacy isolation gate
```

## Guarantees

- User interaction remains `User <-> Planner`.
- Worker, Tester, Synthesizer, and Final Tester agents return artifacts,
  blockers, or evidence only.
- Product runtime effects enter through `ActionGateway`.
- Runtime actions are audited as `runtime_action` effects with output refs.
- Unknown requested runtime actions fail visibly instead of disappearing.
- Blocked plugin/MCP runtime actions preserve approval metadata for replay.
- Approved runtime action replay goes through `ActionGateway` without rerunning
  worker model output generation.
- Coding eval accounts for patch preview, sandbox apply, check result,
  debug finding, and runtime action evidence.
- Failed check/debug evidence drives Planner replan before finish.
- Product live AgentGraph does not compile or run legacy `WorkflowSpec` /
  `WorkflowRunner` paths.
- Product server and UI no longer expose legacy runtime create/edit/execute
  paths; stored AgentGraph run read APIs remain available for evidence review.
- Legacy endpoints remain explicit compatibility paths and are marked
  deprecated.

## Known Limitations

- The Starlette/httpx deprecation warning in tests is non-blocking for rc.1.
- Real external MCP servers, external account flows, and secret-backed provider
  integrations remain outside the release candidate validation.
- The current release gates cover the local product path and built-in registry
  behavior, not a remote plugin marketplace.

## Post-1.0 Exclusions

The following are intentionally excluded from v1.0:

- WeChat, Bilibili, and literature workflows.
- GitHub PR automation.
- Complex MCP marketplace flows.
- Large UI redesigns.
- Multi-user cloud sync.
- Dedicated ResearchWorkerEngine and DraftWorkerEngine packages.

## Validation

Release validation run from `F:\bbb\coder` after publishing `v1.0-rc.1`
and completing the first legacy deletion pass:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall src tests

cd frontend
npm.cmd run build
```

Results:

- `unittest discover -s tests`: 268 tests OK.
- `compileall src tests`: OK.
- `npm.cmd run build`: OK.
- Local API smoke: `POST /api/v2/live-agent-runs` completed the default
  Planner-led AgentGraph path, returned a `stored_run_id`, and the stored run
  was readable through `/api/v2/runs/{run_id}`, `/events?cursor=0`, and
  `/artifacts/{artifact_id}`.
- Legacy live-run detail for the AgentGraph run returned `410` with migration
  links to `/api/v2/live-agent-runs/{run_id}`.
