# Agent Engines

Agents do not call tools directly. Runtime compiles each Agent into a runtime
profile and dispatches work through `AgentRun` and `AgentEngineRegistry`.

Current default worker path:

```text
AgentGraphExecutor.create_execution_result
-> AgentRun
-> RuntimeProfileCompiler
-> AgentEngineRegistry
-> CodeWorkerEngine
-> CodeWorkerHarness
```

`AgentEngineSpec` and `HarnessGraph` define installable engine structure without
exposing it in ordinary UI.

`HarnessValidator` enforces core boundaries:

- context builder, artifact validator, and output artifact are required
- loops require max steps
- worker and tester engines cannot ask the human
- tester engines cannot write files
- external effects require preview metadata
- plugin operations require permission metadata
