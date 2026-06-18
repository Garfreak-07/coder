# Default Workflow Status

The default workflow is currently a safe planning and validation loop, not a fully autonomous patch writer.

## What works now

```text
intake -> scan_repo -> module_map -> plan -> approval -> execute(dry-run) -> check -> review
```

The Web UI can pass the basic run settings needed for this loop:

- target scope
- allowed write paths
- check command
- approval flag for dry-run execution
- max iterations

This means the default workflow can now complete a full safe run from the UI when the user approves execution.

## Current limitation

`execute_node` is still deliberately dry-run. It records that execution was approved but does not modify source files.

That is the right safety default until patch application has these pieces:

1. Snapshot before mutation.
2. Exact allowed-path enforcement.
3. Patch preview and human confirmation.
4. Deterministic patch application.
5. Check command execution after patch.
6. Reviewer gate before final status.
7. Rollback support.

## Next implementation target

The next useful step is a scoped patch executor:

```text
planner target files
  -> read allowed files
  -> executor proposes unified diff
  -> show diff
  -> user approves
  -> apply patch
  -> run checks
  -> reviewer approves or blocks
```

Do not skip the approval and rollback pieces. Without them, the product becomes another opaque coding agent instead of a controlled local workflow.
