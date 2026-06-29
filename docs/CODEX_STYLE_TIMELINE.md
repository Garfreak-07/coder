# Codex-Style Timeline

Coder projects run events through:

```text
GET /api/v3/runs/{run_id}/timeline
```

The response contains stable public items:

- `planner_message`
- `reasoning_summary`
- `plan_update`
- `executor_step`
- `tool_call`
- `command_execution`
- `file_change`
- `approval`
- `verification`
- `final_summary`

The projector summarizes existing run events and report data. It does not expose
raw backend payloads, raw OpenHands JSON, or private chain-of-thought by
default. Debug replay remains available only in the React debug UI.

Frontend rendering lives in:

```text
frontend/src/features/work-timeline/WorkTimeline.tsx
frontend/src/features/work-timeline/timelineTypes.ts
frontend/src/features/work-timeline/timelineAdapter.ts
```

The timeline is the normal work surface after Start Work. Raw event cards are
not part of the ordinary chat view.
