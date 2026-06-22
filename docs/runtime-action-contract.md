# Runtime Action Contract

This v1.0 contract defines how runtime effects are requested, audited, blocked,
and replayed in the Planner-led AgentGraph product path.

Runtime actions are low-level effects requested by executor artifacts and executed
only through `ActionGateway`. They are compact, auditable records for Planner,
not a direct executor-to-tool escape hatch.

## Request Shape

Executor artifacts may include `requested_actions` entries with:

- `action_type`: one of `repo_index`, `call_plugin`, `call_mcp`, or another
  requested operation that must be recorded as failed if unsupported.
- `operation_id`: plugin operation id, or the MCP target operation when relevant.
- `args`: operation arguments.
- `risk_level`: `low`, `medium`, or `high`.
- `requires_permission` / `requires_approval`: explicit executor-side risk hints.
- `work_item_id`: filled from the execution artifact when omitted.

## RuntimeActionRecord

Each request produces one Planner-visible runtime action effect:

- `artifact_type`: `runtime_action`
- `effect_type`: `runtime_action`
- `action_type`
- `status`: `ok`, `blocked`, or `failed`
- `work_item_id`
- `artifact_ref`
- `output_ref`
- `tool_result_ref`
- `requires_planner_replan`
- `reason`
- `error_code`
- `operation_id`
- `approval_key` for blocked approval-gated plugin/MCP actions
- `policy` for plugin/MCP capability decisions
- `action_spec` containing the original `ActionSpec`
- `action` containing the gateway completion payload

The associated output is stored in `GraphRunCache.hidden_effect_outputs` under
`output_ref`.

## Unknown Requests

Unknown `requested_actions` are not ignored. They produce a failed
`runtime_action` artifact with the original request and an `unknown_action_type`
or equivalent error code. Planner receives the ref in `PlannerInputBundle.effects`
and must decide whether to replan, narrow the work, or ask the user.

## Approval And Replay

Approval-gated plugin and MCP actions are recorded as `blocked` runtime actions.
The record must preserve `approval_key`, policy, original `ActionSpec`, and
`work_item_id`.

When Planner receives a user approval, the next run can include
`approved_runtime_actions`. Replay uses the preserved `ActionSpec` and calls
`ActionGateway` again. Replay must not re-run the executor model that originally
requested the action.

## Boundaries

- No product path may bypass `ActionGateway`, `BudgetBroker`, `ContextService`,
  `AgentRun`, or `AgentEngineRegistry`.
- The removed old workflow runtime and old artifacts are not valid product
  runtime-action paths.
- Runtime action details are backend artifacts. Ordinary UI must not expose raw
  runtime JSON, context policy, token budget, manual capability checklists, or
  planner strategy controls.
