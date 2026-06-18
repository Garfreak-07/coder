# Design Principles

Coder optimizes for the highest useful service with the lowest reasonable token cost.

## Core idea

```text
Small context → clear plan → bounded action → deterministic checks → concise review
```

## Rules

- Prefer module summaries over full file dumps.
- Prefer paths, diffs, check outputs, and structured facts over prose.
- Ask the model only when deterministic code cannot decide.
- Keep prompts short and role-specific.
- Limit loops to 3.
- Stop on scope escape, high risk, or repeated failure.
- Show users decisions, not internal chatter.

## Product tone

Concise. Useful. Calm.

No agent theater. No fake certainty. No giant explanations unless the user asks.

## Token strategy

1. Scan with code.
2. Compress into module map.
3. Send only selected scope to the model.
4. Generate patch, not essays.
5. Review diff and check output, not the whole repo.

