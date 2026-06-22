# Agent Engines

Agents do not call tools directly. Runtime compiles each Agent into a runtime
profile and dispatches work through `AgentRun` and `AgentEngineRegistry`.

Current default execution path:

```text
AgentGraphRunner
-> AgentRun
-> AgentEngineRegistry
-> PlannerEngine / CodeWorkerEngine / TesterEngine
-> structured artifact
```

The product runner does not construct `AgentGraphExecutor`. Do not add prompt
building, repair logic, mock payload construction, or artifact-specific
execution there.

Registered default engines:

- `planner-engine`: creates `PlannerOrder` and `PlannerDecision`.
- `code-worker-engine`: runs bounded coding work through `CodeWorkerHarness`.
- `tester-engine`: creates per-work-item `test_result` artifacts.

Agent engines receive prepared envelopes. They should not call `ContextService`,
`PatchService`, `CommandService`, artifact validation, or repair services
directly. New low-level work enters through `ActionGateway`, which reserves
budget through `BudgetBroker` first.

`AgentEngineSpec` and `HarnessGraph` define installable engine structure without
exposing it in ordinary UI.

`HarnessValidator` enforces core boundaries:

- context builder, artifact validator, and output artifact are required
- loops require max steps
- executor and tester engines cannot ask the human
- tester engines cannot write files
- external effects require preview metadata
- plugin operations require permission metadata

Model calls inside the default AgentGraph engines reserve model budget before
invocation when a real model is configured. Mock-mode execution does not consume
model-call budget.

## v1.0 Boundary

- Ordinary users choose Agents; engine graphs remain hidden runtime internals.
- `RunController` controls whether engine output can lead to another round.
- `BudgetBroker` gates model calls and low-level engine actions.
- `ActionGateway` is the approved bridge from engine/runtime intent to context,
  patch, sandbox apply/check, command, plugin, MCP, artifact validation, and
  repair services. Registry `ToolCapability` is enforced before plugin/MCP
  dispatch.
- `AgentRun` is the only product facade for Planner, Executor, Tester, and
  PlannerDecision execution.
- Partitioned stores write engine metadata, results, events, artifacts, blobs,
  ledgers, contexts, tool results, live runs, and cache data.
- There is no fallback old workflow runner or legacy engine path in the product
  runtime.
