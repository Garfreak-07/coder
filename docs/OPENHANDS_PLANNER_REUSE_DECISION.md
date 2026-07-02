# OpenHands Planner Reuse Decision

Recorded: 2026-07-02

Decision: implement Path B, an OpenHands-compatible Planner adapter, now. Do
not route Planner Chat through a live OpenHands conversation until OpenHands
provides a no-run, no-tools chat/session contract that can be enforced by API.

## What Was Weak

The old Planner path was too easy for a general chat model to misuse:

- Prompt issue: the boundary between chat and Start Work was appended as general
  guidance, not a strict product contract.
- Provider issue: Planner used a direct chat-completions request with a large
  token budget and no finish-reason handling.
- Context issue: Planner context did not use the same session/context shape as
  OpenHands execution payloads.
- Output contract issue: responses were only plain text plus loose readiness
  fields, so tables and long answers leaked into chat.
- Session loop issue: chat turns were stored as message strings without
  structured artifacts or truncation metadata.
- Reuse issue: Planner did not reuse OpenHands-compatible message/session/context
  shapes, while Executor already did.

## Implemented Now

`crates/coder-server/src/lib.rs` now has
`OpenHandsCompatiblePlannerAdapter`.

The adapter reuses OpenHands-compatible shapes without creating an OpenHands run:

- OpenHands conversation payload shape from
  `coder_workflow::build_openhands_conversation_payload`.
- OpenHands context contract shape: `coder.openhands.conversation.v1` and
  `coder.openhands.context.v1`.
- OpenHands message event shape: role, text content, `cache_prompt=false`, and
  `run=false`.
- OpenHands model naming normalization through the shared payload builder, while
  stripping `api_key_env` and `base_url_env` from the Planner context payload so
  secrets are not embedded in prompts.

The Planner remains side-effect free:

- no OpenHands server conversation is created
- no `trigger_run`
- no user event is posted to OpenHands
- `run=false` on all compatible message events
- `tools=[]`
- `include_default_tools=[]`
- terminal, file editor, task tracker, command execution, network tools, secrets,
  git commit, git push, and deploy are denied in the Planner-compatible context

## Prompt And Contract

Planner prompt now states:

- Chat is planning and conversation only.
- Planner does not edit files or run commands in chat.
- Execution starts only when the user clicks Start Work.
- When ready, Planner says: "I'm ready. Click Start Work and I'll execute this
  through the OpenHands executor."
- Planner must not mention Discuss/Work modes or expose internal readiness state.
- Planner keeps normal answers bounded and avoids markdown tables in chat.

Planner API responses now include:

- `assistant_message`
- `ready_for_start_work`
- `missing_information`
- `concise_plan_summary`
- `structured_artifacts`
- `response_truncated`

The UI displays only the assistant message and compact artifact cards.

## Executor Runtime Boundary

Planner reuse is separate from execution ownership. Coder now treats OpenHands
as an internal executor runtime in managed mode:

- Coder generates an in-memory Executor Runtime Secret per server launch.
- The secret is generated from OS-backed randomness and is different for each
  runtime.
- The secret is injected into the managed OpenHands child process only through
  process environment, never through persisted config.
- Start Work injects the runtime secret into `OpenHandsHarnessConfig` through
  the existing skipped `session_api_key` field, so serialization and git diffs
  do not contain it.
- External OpenHands URLs and tokens remain a developer/enterprise mode, not
  normal user setup.

Managed mode preserves the Planner boundary: Planner Chat still has no tools,
no terminal, no file editor, and no command execution. Start Work is the only
path that can hand work to the OpenHands executor.

## Why Not Path A Yet

Path A would require Planner Chat to create a live OpenHands conversation. The
current `coder-openhands::OpenHandsClient` is an execution client: it creates or
attaches conversations, sends user events, can start runs, and polls execution
events. Even if tools are omitted, it still introduces server-side
conversation/runtime state outside Coder's canonical Planner session store.

Concrete blockers:

- no documented no-run Planner conversation API
- no enforced no-tools/no-default-tools contract at the OpenHands API boundary
- no side-effect-free provider-only adapter exposed by OpenHands in this repo
- no proof that OpenHands will not create executable runtime state for Planner
  chat turns

Until those blockers are removed, Path A would weaken the Planner/Executor
split. Path B gives concrete reuse while preserving the product boundary.

## Tests

Current tests prove:

- Planner does not claim it edited or ran files in chat.
- Planner tells the user to click Start Work when ready.
- Planner can mark `Create a minimal Snake game in F:\ccc\coder-snake-game`
  ready.
- Planner can answer two turns through a real local provider test server.
- Provider `finish_reason=length` produces a controlled truncated response.
- Markdown table output becomes structured table artifacts.
- The OpenHands-compatible Planner adapter has no terminal, file editor, task
  tracker, default tools, command tools, or run-triggering message events.
- Managed OpenHands runtime secrets are generated per server state, injected
  only into the in-memory harness config, and not serialized.

## Remaining Work

OpenHands-backed Planner Chat can replace Path B only after OpenHands exposes a
tool-disabled, no-run chat/session/provider adapter with explicit guarantees.
When that exists, Coder should keep its Planner session store canonical and use
OpenHands only as the safe conversation/provider backend.
