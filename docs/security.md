# Upload Safety Checklist

Use this checklist before pushing code to GitHub.

## Never upload

- `.env`
- API keys
- GitHub tokens
- model provider keys
- database URLs
- private certificates
- SSH keys
- real user data
- local-only private paths when they reveal sensitive information

## Safe to upload

- `.env.example`
- README files
- source code without secrets
- documentation
- small synthetic examples

## Local checks

```powershell
git status --short
git diff --stat
git diff
```

Search for common secret words:

```powershell
Get-ChildItem -Recurse -File | Select-String -Pattern "api_key|token|secret|password|sk-"
```

Check ignored files:

```powershell
git status --ignored --short
```

## Current ignore policy

The repository ignores:

```text
.env
.env.*
outputs/
.coder_history/
.venv/
*.egg-info/
```

`.env.example` is intentionally allowed so users know which variables to configure.
