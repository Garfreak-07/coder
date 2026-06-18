# Security Policy

Coder is a local-first coding workflow tool. It may read local project files and, in future versions, generate patches.

## Supported versions

The project is early-stage. Security fixes target the latest `main` branch.

## Reporting a vulnerability

Please do not open a public issue for sensitive security reports.

For now, report privately by contacting the project owner on GitHub:

https://github.com/Garfreak-07

When reporting, include:

- affected version or commit;
- operating system;
- minimal reproduction steps;
- whether secrets, local files, or generated patches are involved.

## Safety expectations

- Do not commit `.env`, API keys, tokens, private certificates, or real user data.
- Review generated plans and patches before applying them.
- Keep modification scope narrow when working on another project.
- Treat model output as untrusted until checked by deterministic validation and human review.

