# Agent Recipes

`AgentRecipe` is the ordinary user-facing Agent definition:

```text
id
name
role
purpose
behavior_notes
preferred_extension_ids
```

Supported recipe roles:

- `planner`
- `do_work`
- `check_result`
- `organize`
- `research`
- `write_draft`

`RuntimeProfileCompiler` compiles each recipe into an internal
`AgentRuntimeProfile` with engine id, context profile, token budget, artifact
policy, plugin policy, skill policy, memory policy, repair policy, and tool
policy.

The compatibility `AgentWorkflowAgent.capabilities` field may still exist in
saved workflows, but ordinary creation can omit it. Defaults are derived from
the Agent role or role card.
