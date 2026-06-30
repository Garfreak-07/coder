# Runtime Storage Model

Coder stores completed runs through `RunStore` and the partitioned stores under
`.coder/runs/<run_id>/`.

## Ownership

- `RunStore` owns stored run lifecycle and index metadata.
- `PartitionedRunStores` is the facade for result, event, artifact, context
  packet, tool result, blob, ledger, and live-run files.
- `BlobStore` is the only durable full-text storage path for large strings.
- `RunEventStore` stores slim event payloads: summary, id/ref, status, and size.
- `ContextPacketStore` stores full context packets separately from events.
- `ToolResultStore` stores full tool result objects separately from events.

## Large Text

Durable large text must use `sha256:<digest>` blob ids. New code must not create
`context:<run_id>:...` or `tool_result:<run_id>:...` durable refs.

Context compaction and tool-result budgeting may stage full content in
`pending_blob_writes` while a run is active. `RunStore.save()` writes those
records to `BlobStore` and replaces the pending field with `persisted_blob_refs`
that do not contain full content.

## Events

Events should not become an implicit database. Large event types are stored as
summary plus id/ref:

- `agent.context_packet`
- `agent.context_packet_v2`
- `agent.coding_context_packet`
- `agent.context_compaction.applied`
- `tool.result`

Full context packets are opened through the context packet endpoint. Full tool
results are opened through the tool result endpoint. Full blob content is opened
through the blob endpoint.

## Recovery And Continuity

`RunResult.resume_checkpoint` is the active recovery path. Interrupted live
runs that reload with checkpoint data become `blocked` with
`status_code="resume_available"`. Queued or running live runs without checkpoint
data become failed with `interrupted_without_checkpoint`.

Multi-run execution continuity is metadata on runs:

- `run_group_id`
- `parent_run_id`
- `continued_from_run_id`
- `turn_index`

Planner Chat lifecycle continuity is stored separately as append-only,
metadata-only JSONL under `.coder/sessions/<session_id>.jsonl`. Session JSONL
links planning turns to runs but does not replace run metadata or store raw
planner conversation text.
