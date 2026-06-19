# Coder Handoff

## Current branch

- Branch: `codex/v02-loop-context-packets`
- Base: `main`
- Reason: `docs/requirements.md` states PR #1 and PR #2 are merged and new unrelated work should start from updated `main` on a new branch.

## Latest completed work

Implemented the MVP v0.2 first-class loop node and loop-aware ContextPacket foundation:

- Added `loop` to backend and frontend `NodeType`.
- Added loop node config fields:
  - `loop_mode`: `retry_until` | `while` | `for_each`;
  - `condition`;
  - `items_key`;
  - `item_key`;
  - `iteration_key`;
  - `max_iterations`;
  - `collect_key`;
  - `summary_key`.
- Added runtime loop state persisted in blocked-run checkpoints:
  - current iteration;
  - current item for `for_each`;
  - `continue` / `should_continue`;
  - `break_reason`;
  - `max_iterations`.
- Added loop runtime events:
  - `loop.started`;
  - `loop.iteration.started`;
  - `loop.iteration.completed`;
  - `loop.completed`.
- Added loop-aware ContextPacket events before agent calls:
  - event type: `agent.context_packet`;
  - includes task, agent metadata, selected state keys, selected state, summaries,
    project repo/scopes, allowed tools, permissions, context policy, token
    estimate, output contract, and active loop state.
- Added frontend loop node creation and inspector fields.
- Added readable loop canvas labels.
- Added ContextPacket cards in the run event panel with a compact summary and
  expandable full JSON.
- Updated the default coding workflow example to route reviewer output through
  a `review_retry` loop before either retrying or finishing.
- Added `tests/test_loop_context.py` for loop max-iteration behavior and
  ContextPacket event ordering/content.
- Updated `docs/requirements.md` implemented/roadmap status so loop and
  ContextPacket are no longer described as wholly missing.

## Verification

Passed:

```powershell
cd frontend
npm.cmd run build
```

Passed:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Passed:

```powershell
.\.venv\Scripts\python.exe -m coder_workbench.cli --repo . --workflow examples\workflows\coding-workbench.json --request "smoke test loop context" --approve
```

Note: `python -m pytest` was not available because `pytest` is not installed in the local virtual environment. The existing tests are `unittest` tests and pass through the standard library runner.

## Known limits after this handoff

- The i18n layer is intentionally minimal. Some runtime status strings and event
  payloads still show provider/runtime English because they come from backend
  event types and schema fields.
- Loop support is now first-class but intentionally narrow:
  - loop nodes determine whether the next iteration should continue and expose
    `should_continue` for edge conditions;
  - loop body structure is still represented by ordinary graph edges;
  - timeline grouping by iteration is not implemented yet;
  - `collect_key` and `summary_key` are schema fields but do not yet collect
    per-iteration outputs or compact prior iteration summaries;
  - `loop.blocked` is reserved in the event type but not emitted yet.
- ContextPacket events exist and are shown in the UI, but they do not yet include
  local knowledge chunk provenance, explicit artifact schemas, or compact prior
  iteration summaries.
- Provider settings UI is not implemented yet.
- Local `.md` / `.txt` knowledge base is not implemented yet.
- Restart-resume for blocked runs exists as persisted snapshots/listing, but full active resume after API process restart is still roadmap work.

## Loop architecture decision

The product should support loop as an explicit v0.2 workflow capability, not only as a graph trick.

Current status:

- Supported today: explicit `loop` nodes with `retry_until`, `while`, and
  `for_each` modes.
- Supported today: conditional edges can route back through a loop node, with
  traversal limits.
- Supported today: loop iteration state and break reasons are emitted and stored
  in run data/checkpoints.
- Not complete yet: iteration-grouped timeline UI, per-iteration output
  collection, compact prior-iteration summaries, and richer loop-back edge
  visualization.

Why edge-only looping is insufficient:

- It is hard for ordinary users to understand on the canvas.
- It does not expose iteration state cleanly in run events.
- It makes ContextPacket construction harder because the runtime cannot tell which artifacts belong to the current iteration.
- It is easy to create confusing retries without clear exit reasons.

Implemented loop design:

1. Add `loop` to backend and frontend `NodeType`.
2. Add loop node config fields:
   - `mode`: `while` | `for_each` | `retry_until`
   - `condition`: expression for `while` / `retry_until`
   - `items_key`: state key for `for_each`
   - `item_key`: current item output key
   - `iteration_key`: current iteration number output key
   - `max_iterations`: required, conservative default such as 3 or 5
   - `collect_key`: optional key for collected per-iteration outputs
   - `summary_key`: optional compact summary for ContextPacket reuse
3. Add runtime loop state:
   - iteration count by loop node ID;
   - current item;
   - collected outputs;
   - break reason: condition false, max iterations, approval rejected, error, or downstream block.
4. Runtime emits loop events:
   - `loop.started`
   - `loop.iteration.started`
   - `loop.iteration.completed`
   - `loop.completed`
   - `loop.blocked` is reserved but not emitted yet.
5. Add UI support:
   - implemented: loop node label and inspector fields;
   - implemented: ContextPacket viewer showing current loop state;
   - remaining: visual indication of loop-back edge;
   - remaining: run timeline grouping by iteration;
   - remaining: compact prior iteration summaries.
6. Keep safety hard limits:
   - workflow `max_steps`;
   - loop `max_iterations`;
   - edge `max_traversals`;
   - agent/tool call budgets;
   - token budget.

For the default coding workflow, the useful loop is:

```text
Tester / Reviewer
  -> condition: review.status == "needs_changes"
  -> Human Approval
  -> Executor
  -> Patch Preview
  -> Patch Approval
  -> Patch Apply
  -> Check
  -> Tester / Reviewer
```

The first implementation now uses a first-class loop node plus conditional
back-edges. Treat loop as product-usable for simple retry/while/for_each flows,
but not complete for rich iteration history until collection/summaries and UI
grouping are implemented.

## Recommended next direction

1. Harden loop UX and semantics.
   - Group run timeline entries by loop iteration.
   - Implement `collect_key` for per-iteration outputs.
   - Implement `summary_key` for compact prior-iteration summaries.
   - Add clearer visual indication for loop-back edges.
2. Expand ContextPacket detail.
   - Add local knowledge chunk provenance once md/txt retrieval exists.
   - Add explicit output artifact schema rendering.
   - Include compact prior loop iteration summaries.
3. Add default coding workflow artifact schemas.
   - `plan_artifact`
   - `patch_artifact`
   - `review_artifact`
4. Then add provider settings UI for OpenAI/DeepSeek.
   - Do not store keys in workflow JSON.
   - Include mock mode and connection testing.
