# Non-Blocking Enhancements

These items are intentionally outside the current release gate.

| Item | Status | Owner area | Why non-blocking | Minimal future acceptance criteria |
| --- | --- | --- | --- | --- |
| Production embedding provider integration | Tracked | Memory/RAG | CI-safe lexical, dense_mock, and hybrid retrieval already cover normal validation without live credentials. | Configured provider, redaction policy, offline tests, and opt-in live smoke. |
| True streaming SSE/WebSocket planner deltas | Tracked | Planner API / React | Current DTOs expose streaming-ready event shapes with non-streaming responses. | `planner.message.started`, `planner.message.delta`, and `planner.message.completed` delivered incrementally with reconnect behavior. |
| Live OpenHands compatibility matrix | Tracked | OpenHands adapter | Current adapter supports configured Agent Server paths and existing tests cover common shapes without requiring a live server. | Matrix doc, supported OpenHands versions/path strategies, and opt-in live smoke jobs. |
| Richer MCP compatibility | Tracked | Harness/tool integrations | Current MCP validation and mock invocation cover the local release gate. | Compatibility notes for common MCP servers, side-effect classification tests, and approval-policy fixtures. |
| Published npm package | Tracked | Packaging | Local npm wrapper dry-run validates packaging shape; publishing credentials are not required for release hardening. | Versioned package published from CI with provenance and install smoke. |
| Published Homebrew tap | Tracked | Packaging | Formula exists, but tap write access is not needed for the current local release gate. | Formula update automation with checksum verification in tap CI. |
| Signed release artifacts | Tracked | Release | Unsigned local artifacts are enough for current install/smoke validation. | CI signing step, public verification instructions, and failure gate. |
| Checksum verification | Tracked | Release | Dry-run packaging validates paths without requiring final release archives. | SHA256 generated and verified for every release artifact before publish. |
| IDE integration | Tracked | Product integrations | Current React/Rust workbench covers the requested Planner-first loop. | IDE extension can start Planner Chat, show approvals, and open evidence refs. |
| Remote plugin sharing and public marketplace publishing | Tracked | Plugins & Skills | Local marketplace, installed list, skill details, MCP dependencies, hooks, and update actions cover this milestone. | Authenticated sharing, shared-with-me, publish flow, and cloud trust policy. |
| Optional GPU-backed local index | Tracked | Retrieval/cache | Core Coder uses CPU/disk only; normal Planner Chat, OpenHands execution, tests, and release validation do not require GPU. | Feature flag, CPU fallback, provider capability detection, and CI with no GPU. |
