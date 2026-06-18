# Contributing

Thanks for considering a contribution.

Coder aims to stay small, safe, and token-efficient. Contributions should preserve that direction.

## Principles

- Prefer simple deterministic code over extra agents.
- Keep prompts short and structured.
- Avoid broad filesystem writes.
- Never require secrets in committed files.
- Keep user-facing workflows understandable for ordinary developers.

## Before submitting changes

Run:

```powershell
python -m compileall src
langgraph-coder --repo . --scope src
```

If you add behavior that can modify files, include:

- scope checks;
- human approval points;
- rollback or snapshot strategy;
- tests or clear verification steps.

## Commit hygiene

- Do not commit `.env`.
- Do not commit generated `outputs/`.
- Do not commit `.coder_history/`.
- Keep commits focused and easy to review.

