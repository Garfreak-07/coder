# Legacy Deletion Record

The goal is one ordinary AgentGraph product path. The old workflow runtime has
now been physically removed from product code after product references were
migrated and tests locked the boundary.

## Order

1. Architecture boundary tests were added.
2. Product calls to old runtime paths were removed.
3. Product UI was moved away from runtime JSON editing.
4. Patch/check/repair/context code moved behind `ActionGateway`.
5. Planner/Executor/Tester execution moved behind `AgentEngineRegistry`.
6. Old schema, compile, runner, node executor, context, condition, artifact
   recorder, and server manager modules were deleted.

## Current Boundary

The removed old runtime files are locked by `tests/test_no_legacy_workflow_runtime.py`.
Product code does not export or import the removed old workflow symbols.

Product live Agent runs use:

```text
AgentWorkflowSpec
-> PlannerOrder.plan_graph
-> RunController
-> RunGuard
-> BudgetBroker round preflight
-> GraphRunCache
-> AgentGraphRunner
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

They must not compile into the removed old workflow schema, run through a
fallback runner, or construct `AgentGraphExecutor` from the product runner path.

The product default AgentWorkflow response no longer includes legacy preview
fields:

```text
workflow
runtime_boundary
runtime_type
deprecated
```

The old compile and live-run endpoints are removed from the product API. Product
AgentGraph runs use `/api/v2/live-agent-runs`, and creation responses return
`live-agent-runs` event/result URLs.

## Artifact Boundary

Product AgentGraph runs use:

- `planner_order`
- `execution_result`
- `test_result`
- `planner_decision`
- `round_summary`
- coding diagnostics such as `patch_preview`, `check_result`, and
  `debug_finding`

Old plan/patch/review artifact production is not part of the product runtime.

## v0.9.7 Boundary Rules

- Ordinary user workflows remain AgentGraph-first.
- `RunController` replaces inline PlannerDecision loop handling.
- `BudgetBroker` replaces ad hoc pre-execution resource checks.
- `ActionGateway` replaces direct product calls to context, patch, command,
  sandbox, plugin, MCP, repo intelligence, artifact validation, and repair
  services.
- Declared `ActionSpec` action types must be implemented by `ActionGateway`;
  direct `load_skill` is not a product runtime action.
- Plugin and MCP execution must read registry `ToolCapability` before runtime
  dispatch; unknown or approval-gated operations must not execute silently.
- Unknown executor-requested runtime actions must create failed `runtime_action`
  artifacts, not disappear from Planner-visible effects.
- Blocked plugin/MCP runtime actions must preserve `approval_key`, policy,
  original `ActionSpec`, and `work_item_id`; approved replay must use
  `ActionGateway` without rerunning executor model output generation.
- `AgentRun` and `AgentEngineRegistry` own product Agent execution;
  `AgentGraphExecutor` is a compatibility adapter only.
- Coding auto-loop effects keep patch preview, sandbox apply, check result,
  requested runtime action, and DebugFinding artifact refs in
  `PlannerInputBundle.effects`.
- Partitioned stores are the explicit write path for metadata, results, events,
  artifacts, blobs, ledgers, contexts, tool results, live runs, extensions, and
  cache data.
- Old workflow preview is deleted; new product behavior must not depend on the
  removed old workflow runtime symbols or endpoints.
