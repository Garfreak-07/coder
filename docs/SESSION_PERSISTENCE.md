# Session Persistence

Coder keeps local, inspectable run and planner-session history under the
repo-local `.coder/` directory. These files are local runtime state, not cloud
sync state.

## Layout

```text
.coder/
  sessions/
  runs/
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

`RunStore::ensure_local_layout()` creates the layout. The cache status endpoint
reports real recursive file counts and byte totals for the cache buckets it
exposes.

## Append-Only Logs

- Run events are stored as append-only JSONL at
  `.coder/runs/<run_id>/events.jsonl`.
- Planner session lifecycle records are stored as append-only JSONL at
  `.coder/sessions/<session_id>.jsonl`.
- Session records store public lifecycle metadata such as mode, readiness,
  turn counts, and linked run ids. They do not store raw user messages or raw
  model messages.

Timeline responses should be projections over run/session state. `.coder/timeline/`
is reserved for projection caches and must not become a second source of truth.

## Large Payloads

Large raw backend payloads should be stored through content-addressed blob refs
under `.coder/blobs/<prefix>/<sha256>`. JSONL payloads should store slim
summaries and references instead of full large strings.

## Cleanup Policy

Generic cache cleanup may remove disposable directories:

- `.coder/repo-index/`
- `.coder/plugin-cache/`
- `.coder/skill-cache/`
- `.coder/tmp/`

Generic cleanup must not delete durable history or review data:

- `.coder/sessions/`
- `.coder/runs/`
- `.coder/timeline/`
- `.coder/blobs/`
- `.coder/artifacts/`
- `.coder/checkpoints/`
- `.coder/changesets/`
- `.coder/openhands-events/`
- `.coder/logs/`

Any destructive cleanup for durable history must be explicit, scoped, and
confirmed by the caller.

## Secret Policy

Provider API keys and other secrets must not be written to `.coder/` JSONL
files. Session JSONL uses metadata-only records, and the store rejects
secret-like keys or strings for session record payloads.

Provider credentials belong in the configured provider settings path or
environment variables, not in run/session/timeline JSONL.
