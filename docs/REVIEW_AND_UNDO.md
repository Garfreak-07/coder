# Review And Undo

Review Changes is exposed through:

```text
GET  /api/v3/runs/{run_id}/changes
GET  /api/v3/runs/{run_id}/changes/{change_set_id}/diff
POST /api/v3/runs/{run_id}/changes/{change_set_id}/accept
POST /api/v3/runs/{run_id}/changes/{change_set_id}/undo
```

The current baseline builds a conservative changeset from the run's repo root,
final report, and current git diff. Opening the review records that diff in a
run artifact.

Undo policy:

- Undo uses `git apply -R`.
- Undo first checks the reverse patch with `git apply -R --check`.
- Undo proceeds only if the current working-tree diff exactly matches the
  recorded review diff.
- If the diff changed after review, the endpoint returns `409 Conflict`.
- Coder never silently discards unrelated user changes.

Frontend rendering lives in:

```text
frontend/src/features/review-changes/ReviewChangesCard.tsx
frontend/src/features/review-changes/changeSetTypes.ts
```

Future work can add run-start snapshots and checkpoint restore fallback, but
the current implementation already provides explicit diff review, accept, and
safe reverse-patch undo.
