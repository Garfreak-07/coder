# Codex Parity Gap Report

## Mirrored Codex Behavior

- Planner Chat is side-effect free; chat turns cannot start execution.
- Start Work is an explicit execution action.
- Run events are projected into user-facing timeline items instead of raw JSON.
- Timeline items cover plan updates, executor steps, tools, commands, file
  changes, approvals, verification, and final summary.
- Review Changes exposes changed files, diff, checks, accept, and undo.

## Removed Coder Behavior

- Main Planner UI no longer shows Draft Plan.
- Main Planner UI no longer exposes Discuss/Work mode toggle.
- Chat input is no longer disabled by internal plan state.
- PlanDraft details are no longer rendered as the default chat message card.
- Raw run event replay is hidden behind debug UI.
- Plugins & Skills marketplace UI is hidden from core navigation and remains a
  developer/debug surface.

## Still Different From Codex

- Coder keeps a user-editable Agent Workflow canvas.
- Coder stores local run state through `RunStore`, repo evidence, artifacts,
  blobs, and checkpoints rather than Codex session JSONL names.
- Plugin/skill marketplace support is retained only as a local developer/debug
  surface in this milestone.
- Review/undo is conservative: undo requires current diff to match the recorded
  review diff.

## Intentionally Different

Coder splits Codex into Planner and Executor:

- Planner talks to the user and owns public summaries.
- Executor acts through harnesses and never chats directly with the user.
- Harness specs remain the tool, permission, memory, and backend boundary.
- OpenHands stays the preferred executor backend when configured.

## Non-Blocking

- Remote plugin sharing and public marketplace publishing.
- Live OpenHands matrix gates.
- Streaming planner deltas.
- GPU-backed local semantic index or local model acceleration.
