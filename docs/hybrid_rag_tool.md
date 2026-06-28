# Hybrid RAG Tool

Rust v3 implements a CI-safe retrieval baseline in `coder-memory`.
Retrieval results remain knowledge hints, not current-code evidence.

## Backends

`POST /api/v3/knowledge/retrieve` supports:

- `lexical`: default, always available, no external dependencies.
- `dense_mock`: deterministic hash-vector retrieval. It provides dense backend
  behavior without live embedding services.
- `hybrid`: weighted score fusion of lexical and deterministic dense scores.

The request can select a backend with:

```json
{
  "query": "workflow evidence",
  "top_k": 5,
  "backend": "lexical | dense_mock | hybrid",
  "scope": "project",
  "role": "workflow_supervisor"
}
```

If `backend` is omitted, Rust v3 uses `lexical`. Normal CI does not require
OpenAI, DeepSeek, Anthropic, Gemini, Chroma, or any external embedding service.

## Response Shape

Responses keep the compatibility `results` array and add `hits` cards for
frontend/tool consumers:

```json
{
  "hits": [
    {
      "source_id": "source",
      "chunk_id": "chunk",
      "score": 1.0,
      "backend": "hybrid",
      "preview": "bounded text",
      "trust_level": "source",
      "evidence_ref": "knowledge://source/chunk"
    }
  ]
}
```

## Policy

All backends enforce the same filters before returning results:

- role and requested-context ACLs
- purpose policy for planning, supervision, and execution roles
- scope selection such as `project`, `public`, `private`, or `all`
- non-secret sensitivity
- Task Execution cannot retrieve private or secret memory

Hints that mention code are marked `requires_repo_verification=true`. Agents
must verify current-code claims with native repo evidence before using them in
final reports or execution decisions.

## Future Enhancements

Production embedding providers, persistent vector indexes, and published
package-manager integrations remain optional follow-ups. They must stay
environment-gated and must not become normal CI requirements.
