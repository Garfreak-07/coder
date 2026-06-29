# Local Cache And Resource Policy

Coder's local runtime uses disk and CPU for persistence, search, diffs, public
timeline projection, artifacts, and evidence. Plugin and skill discovery is
retained as a developer/debug surface while marketplace UI is deferred from the
core product path.

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
- Provider API keys must not be stored in cache directories.
- Environment variables are developer/headless fallback, not the normal user
  path.

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
- Future GPU use must be optional, provider-scoped, and fully CPU-fallbackable.
- Normal Planner Chat, OpenHands execution, tests, smoke checks, and release
  validation must not require GPU hardware.
