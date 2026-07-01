# OpenHands Planner Reuse Decision

Recorded: 2026-07-01

Decision: do not route Planner Chat through OpenHands conversation/runtime in
this phase. Keep the current Coder Planner provider path, and keep the boundary
thin so a future OpenHands-backed provider adapter can replace it if OpenHands
exposes a side-effect-free chat/provider surface.

## Product Boundary

Planner Chat must remain side-effect free:

- talks to the user
- uses configured provider credentials
- may read bounded planning context and memory proposals
- does not start workflow runs
- does not edit files
- does not run terminal commands
- does not call OpenHands tools

Executor remains the OpenHands-backed runtime:

- starts only after Start Work
- owns the ReAct loop
- uses terminal, file editor, and task tracker tools through harness policy
- emits evidence, timeline events, review changes, and undo state

## Current Implementation

Coder already has a narrow Planner provider path in
`crates/coder-server/src/lib.rs`:

- `ModelPlannerConversationEngine::live_assistant_message`
- `provider_http_client_builder`
- `provider_api_key`
- `model_provider_base_url`
- `planner_system_prompt`

This path calls an OpenAI-compatible chat completions endpoint directly, applies
provider settings from the UI, supports explicit provider proxy URLs, bypasses
proxies for localhost providers, redacts configured secrets from errors, and
falls back to deterministic planner responses only in mock mode.

OpenHands integration is currently execution-oriented:

- `coder-openhands::OpenHandsClient` creates or attaches conversations
- it sends user events and starts runs
- it polls or streams execution events
- `coder-workflow::OpenHandsHarnessBackend` normalizes those events into public
  ReAct timeline items

Those APIs are a good executor fit, but not a clean Planner Chat fit today.

## Reuse Questions

### Can Planner reuse the OpenHands provider adapter?

Not directly today. The reusable OpenHands Rust crate is a conversation/run/event
client, not a standalone provider adapter. The current Planner path needs only a
tool-less chat completion call, provider settings, proxy handling, and redacted
errors. Reusing OpenHands by starting a conversation would add run semantics the
Planner must avoid.

Future-safe direction: extract Coder's provider request construction into a
small `PlannerModelClient`/`ChatCompletionClient` interface. If OpenHands later
exposes a side-effect-free provider adapter, implement that interface behind the
same boundary.

### Can Planner reuse the OpenHands conversation/session client?

No for the product path in this phase. `OpenHandsClient` is designed around
OpenHands conversations and run triggering. Even with tools disabled, the shape
is still an execution conversation with server-side state outside the Planner
session store. That would make it harder to prove that Planner turns cannot
start work.

Future-safe direction: keep Planner sessions in Coder's session store and allow
only a tool-less, no-run OpenHands conversation adapter if it can be proven to:

- never call `trigger_run`
- never post user events with `run=true`
- never expose terminal, file, browser, or task tools
- persist only redacted message summaries into Coder state

### Can Planner reuse OpenHands event normalization?

Partially. OpenHands raw execution event normalization is already reused for
Executor timeline projection. Planner Chat should not emit OpenHands execution
events, but it can mirror the same public-envelope discipline:

- bounded public summaries
- no raw provider payloads in normal UI
- secret redaction before persistence
- evidence refs instead of large raw JSON blobs

Implementation is already aligned conceptually; no new runtime code is needed
for this phase.

### Can Planner reuse OpenHands memory/context components?

No concrete OpenHands memory adapter is available in this repository. Coder's
Planner memory boundary is already explicit: project/long-term memory can be
read or proposed only through planning-chat roles, and workflow agents cannot
confirm long-term writes.

Future-safe direction: if OpenHands exposes reusable context summarization, it
may feed bounded hints into Planner Chat, but memory writes must still go
through Coder's planner-only propose/confirm endpoints.

### Can Planner run through OpenHands with tools disabled?

Not safely enough for this phase. A tool-less OpenHands conversation could be
made to work technically, but it would still create another session/run-shaped
control plane beside Coder's Planner session model. The value is low while the
risk to the Planner/Executor split is high.

### Would that preserve side-effect-free planning?

Only if OpenHands provides a no-run, no-tools mode with enforceable API
contracts. The current local integration proved OpenHands Agent Server can run
real executor work; it did not prove a side-effect-free Planner mode.

### Would that simplify Coder?

Not now. It would replace a small direct chat-completions call with a larger
conversation/runtime adapter and more state synchronization. The simpler current
path is to keep Planner's provider call direct and keep Executor on OpenHands.

## Decision

Keep the current Planner provider path for product mode.

Do now:

- document this decision
- keep Planner provider code isolated behind `PlannerConversationEngine`
- keep OpenHands event normalization limited to executor events
- keep Provider Settings as the shared user configuration surface for Planner
  provider calls and OpenHands executor settings

Do later only if OpenHands exposes the right boundary:

- introduce a thin `OpenHandsPlannerConversationAdapter`
- make it tool-less and no-run by construction
- reuse only provider/session/message pieces, not executor tools
- keep Coder Planner session state canonical
- add tests proving Planner Chat cannot start OpenHands runs

## Acceptance Status

This phase does not implement an OpenHands-backed Planner adapter because the
safe reuse point is not present yet. The documented boundary keeps the future
swap small while preserving the product split that was already validated by
Planner Chat tests, Start Work tests, and the OpenHands live executor smoke.
