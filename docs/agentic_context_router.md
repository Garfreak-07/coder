# Agentic Context Router

Batch F adds a deterministic, LangGraph-inspired router for choosing retrieval
channels before a harness prompt is assembled.

## Core Rule

```text
RAG is a hint, not evidence.
Repo search/read/test/diff output is evidence.
```

The router does not add LangGraph or LangChain as required dependencies. It
adapts the useful Adaptive RAG pattern into Coder-native state transitions:

```text
classify intent
-> choose initial source
-> retrieve
-> grade context
-> rewrite weak queries
-> switch source when useful
-> verify code-like knowledge hints with repo evidence
-> assemble context
```

## Sources

`native_repo` uses bounded file discovery, text search, and file-range reads.
It produces `repo_evidence` and refs under `.coder/runs/{run_id}/repo_evidence/`.

`run_evidence` uses execution results, verification summaries, changed-file
summaries, blockers, diff refs, log refs, native event refs, run snapshots, and
planner task state. It supports runtime and workflow completion claims.

`direct_memory` loads small scoped memory cards directly through the existing
memory retriever.

`hybrid_rag` uses ACL-filtered BM25/Chroma hybrid retrieval only for knowledge
hints: external docs, project notes, design decisions, roadmaps, prior run
context, historical blockers, and scoped coding knowledge.

`clarify_user` is allowed only for Planning Chat.

## Role Profiles

Planning Chat can use memory and RAG early for planning, history, docs,
roadmaps, decisions, Obsidian-style notes, and user-maintained notes. Any claim
about current code must be verified through repo evidence.

Workflow Supervisor starts with run evidence and completion facts. RAG can
provide historical or policy hints, but cannot prove tests passed, files
changed correctly, or blockers were resolved.

Task Execution starts with native repo evidence and may use RAG only for
external docs, scoped coding knowledge, or historical blocker hints. RAG cannot
justify a code edit.

## Context Packet Mapping

Router output maps into harness context packets as:

- `warm.repo_evidence`
- `warm.run_evidence`
- `warm.knowledge_hints`
- `warm.memory_cards`
- `warm.retrieval_route_trace`
- `cold_refs.repo_evidence`
- `cold_refs.run_evidence`
- existing `cold_refs.knowledge` and `cold_refs.memory`

Full files, raw logs, raw diffs, prompts, and model outputs remain behind refs
or existing artifact stores.

## Future Adapters

Obsidian vault sync is a future Batch G knowledge bridge. Obsidian notes are
planning context and project knowledge, not code evidence.

MCP is a future Batch H adapter. MCP tools must call Coder routing services and
ACL-filtered retrieval; they must not expose raw Chroma, raw BM25, global memory
search, or an unscoped query engine.
