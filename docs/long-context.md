# Long-Context Model

Coder keeps context construction Planner-led and AgentGraph-native.

## Primary Path

- `ContextService` is the public work-item context construction entrypoint.
- Private projection inside `ContextService` chooses hot, warm, and cold inputs.
- `ContextCompactor` shrinks selected context fields.
- `ContextBudget` owns token limits.
- `TokenLedgerEntry` records the projected and compacted model-facing size.

Do not introduce a public `ContextProjector` module unless private projection in
`ContextService` is no longer sufficient.

## Projection

Projection happens before compaction:

- Hot context: current request, current work item, planner order ref, direct
  upstream refs, direct snippets, and current blocker evidence.
- Warm context: previous round summaries, planner decisions, completed work
  item summaries, changed-file summaries, and unresolved blockers.
- Cold context: full tool outputs, full artifacts, old context packets, full
  diffs, and old event logs.

Hot and warm context may enter the model-facing packet. Cold context should be
represented as summaries and refs.

## Compaction

`ContextCompactor` decides which selected fields are too large, which keys must
be preserved, and what preview text the model sees. It writes externalized text
through a BlobStore-compatible callback and returns values shaped like:

```json
{
  "blob_id": "sha256:<digest>",
  "ref_type": "context",
  "field_path": "included_snippets.0.content",
  "preview": "preview text",
  "original_chars": 123456,
  "media_type": "text/plain; charset=utf-8"
}
```

## Tool Results

Large command and check output is budgeted before future context reuse. The
replacement record is stored in run data as `tool_result_replacements`, and the
full text is persisted through `BlobStore`:

```json
{
  "kind": "tool-result",
  "result_id": "cmd:result.output",
  "blob_id": "sha256:<digest>",
  "replacement": "<persisted-output ...>preview</persisted-output>",
  "original_chars": 123456,
  "preview_chars": 2000
}
```

Resume should reuse the same replacement record instead of making a new
replacement choice for the same output.
