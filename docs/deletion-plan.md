# Legacy Deletion Plan

The goal is one ordinary AgentGraph product path. Legacy runtime pieces are
removed only after product references are gone and tests protect the boundary.

## Order

1. Add architecture boundary tests.
2. Stop new product calls to legacy runtime paths.
3. Keep `WorkflowSpec` / `WorkflowRunner` only for compatibility preview.
4. Migrate product UI away from runtime JSON editing.
5. Migrate patch/check/repair/context code to shared services.
6. Move or delete legacy modules once no product tests or endpoints depend on
   them.

## Legacy Artifacts

`plan_artifact`, `patch_artifact`, and `review_artifact` are compatibility
artifacts for old saved workflows. New product AgentGraph runs use:

- `planner_order`
- `execution_result`
- `test_result`
- `planner_decision`
- `round_summary`
- coding diagnostics such as `patch_preview`, `check_result`, and
  `debug_finding`
