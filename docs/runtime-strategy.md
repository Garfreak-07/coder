# Agent Runtime Strategy

This project should keep the regular user path simple:

```text
select project -> describe request -> run default workflow
```

Advanced runtime details should be inferred, hidden, or shown only as debug output.

## Default workflow

Use three user-visible agents:

```text
Codex Planner
  -> DeepSeek CC Executor
  -> DeepSeek CC Tester
  -> Codex Planner
       -> finish when tests pass
       -> retry executor when failures are actionable
       -> block when risk/scope is unacceptable
```

Codex owns planning and judgment. DeepSeek-backed Claude Code-style agents own implementation and testing.

## Token policy

The default workflow should minimize token burn by design:

1. Keep static instructions at the beginning of prompts.
2. Put volatile project/request data at the end.
3. Send module summaries and selected file snippets, not full repository dumps.
4. Pass structured state between agents instead of full transcripts.
5. Compact each loop into:
   - planner summary
   - target files
   - changed files
   - test output excerpt
   - retry instruction
6. Log token usage and cached-token counts when providers expose them.

This follows OpenAI prompt caching guidance: cache hits depend on exact prefix matches; static instructions should come before variable user/project content; caching starts at 1024-token prompts and cached-token counts are reported in usage metadata.

## Network policy

Default network policy:

```text
Codex Planner: network off by default
DeepSeek CC Executor: network off by default
DeepSeek CC Tester: network off by default
```

Network should be enabled only by capability pack, for example:

- GitHub connector
- package registry lookup
- web search
- remote MCP server

Any network capability should declare:

- why it needs network
- allowed domains or server command
- whether credentials are required
- whether user approval is required

## Transport policy

Prefer local-first transports:

1. In-process calls for built-in tools.
2. MCP stdio for local connector processes.
3. MCP Streamable HTTP only for long-running or remote servers.
4. A2A only for external agent interoperability; local workflow routing can stay in-process.

MCP stdio is the best default for local tools because the client starts the server as a subprocess and communicates over stdin/stdout. For remote/multi-client cases, MCP Streamable HTTP supports POST/GET, SSE streaming, sessions, resumability, and explicit security requirements such as Origin validation and localhost binding for local servers.

A2A is useful for agent discovery and interop because its spec includes Agent Cards, skills/capabilities, tasks, streaming, push notifications, and protocol bindings. For this project, keep A2A internal until external agents need to connect.

## Dynamic LangGraph policy

Users should be able to manually configure agents on the canvas without requiring Python code changes each time.

The right shape is:

```text
fixed Python graph runner
  + workflow JSON from canvas
  + generic agent node
  + generic route node
  + provider/tool registry
```

LangGraph still needs a compiled graph before execution, but the compiled graph can be a generic interpreter:

```text
START
  -> load_workflow_spec
  -> execute_next_step
  -> route_from_spec
  -> execute_next_step
  -> ... until done / retry / blocked
```

That means:

- adding a new agent card does not require code changes;
- adding a new edge does not require code changes;
- changing role/model/capabilities does not require code changes;
- adding a brand-new tool type may require registry code once, then becomes selectable.

Only these should require Python changes:

- new deterministic node implementation;
- new tool adapter;
- new transport adapter;
- new state schema field that cannot fit existing generic fields.

## References

- LangGraph models workflows as state, nodes, and edges; nodes and edges are Python functions, and graphs must be compiled before use.
- LangGraph supports conditional routing and dynamic `Send`/`Command` patterns for flexible control flow.
- MCP defines stdio and Streamable HTTP transports.
- A2A defines Agent Cards, Agent Skills, tasks, streaming, and protocol binding concepts.
