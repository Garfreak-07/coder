# Local Cache And Resource Policy

Coder's local runtime uses disk and CPU for persistence, search, diffs, timeline
projection, plugin and skill discovery, artifacts, and evidence.

Preferred local layout:

```text
.coder/
  runs/
  sessions/
  timeline/
  blobs/
  artifacts/
  checkpoints/
  changesets/
  repo-index/
  plugin-cache/
  skill-cache/
  openhands-events/
  logs/
  tmp/
```

Rules:

- Event logs are append-only JSONL.
- Large raw backend payloads should be stored as blob refs.
- Timeline responses should project public summaries, not raw payloads.
- Patch diffs and reverse-patch data belong to review/change artifacts.
- Repo index, plugin cache, and skill cache are disposable.
- CPU scans must be bounded by file size, binary detection, and cancellation.
- Long scans should move to background tasks and report progress.
- GPU is not part of the core runtime.

Cache endpoints:

```text
GET    /api/v3/cache/status
POST   /api/v3/cache/clear
POST   /api/v3/cache/reindex
GET    /api/v3/cache/tasks
DELETE /api/v3/cache/tasks/{task_id}
```

GPU policy:

- No GPU scheduler in core Coder.
- Future GPU use must be optional and provider-scoped.
- Normal Planner Chat, OpenHands execution, tests, smoke checks, and release
  validation must not require GPU hardware.
