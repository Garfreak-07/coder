# Coder v1.0 Release Plan

This plan freezes the product contract for the v0.9.7 convergence release and
defines the work required for a v1.0-rc.1 candidate.

## Target

v0.9.7 is the v1.0 Release Plan / Contract Freeze milestone. It keeps the
Planner-led AgentGraph workbench as the only ordinary product path and narrows
the remaining work to runtime action replay, coding evaluation gates, capability
matrix coverage, and legacy runtime deletion validation.

The v1.0-rc.1 candidate is ready when the acceptance tests in
`docs/1.0-acceptance-tests.md` pass without changing the architecture contract.

## Frozen Product Path

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

User interaction remains `User <-> Planner`. Executor and Tester agents return
structured artifacts, blockers, or evidence to Planner and never ask the user
directly.

## Release Gates

- Runtime actions use the schema in `docs/runtime-action-contract.md`.
- Unknown requested runtime actions produce failed `runtime_action` artifacts
  instead of being silently dropped.
- Approval-gated plugin and MCP runtime actions retain `approval_key`, policy,
  original `ActionSpec`, and `work_item_id` for Planner-visible replay.
- Approved runtime action replay goes back through `ActionGateway` and does not
  re-run the executor model.
- Capability matrix tests cover repo indexing, plugin risk levels, MCP default
  approval, argv sandbox commands, shell approval boundaries, and unknown
  operations.
- Coding evaluation reports account for `patch_preview`, `sandbox_apply`,
  `check_result`, `debug_finding`, and `runtime_action` evidence.
- Failed checks or debug findings force Planner replan before finish.
- Product live AgentGraph runs do not compile through the removed old workflow
  schema, run a fallback runner, or emit old runtime artifacts.

## Out Of Scope For v1.0

- WeChat, Bilibili, literature workflows, GitHub PR automation, complex MCP
  marketplace flows, major UI redesigns, and multi-user cloud sync.
- Ordinary UI exposure of runtime JSON, context policy, `TokenBudget`, manual
  capability checklists, or planner strategy knobs.

## Milestones

1. v0.9.7 contract freeze: document the release contract and acceptance gates.
2. Runtime action audit/replay: close silent drops and add Planner-approved
   replay without executor re-execution.
3. Capability matrix: lock plugin, MCP, repo, command, and unknown-operation
   boundaries.
4. Coding eval gate: make eval evidence drive Planner replan rather than direct
   finish on failed checks.
5. Legacy deletion: remove old workflow runtime modules and endpoints while
   product runs stay on AgentGraph.
6. v1.0-rc.1: all unit, compile, architecture, and acceptance gates pass.
