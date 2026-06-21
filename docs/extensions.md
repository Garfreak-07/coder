# Extension System

Extensions are globally installed and routed by the runtime. Users do not need
to attach every capability to every Agent.

## Plugins

Plugins provide executable operations:

- Command Runner
- File Patch Service
- MCP or connector operations
- Browser or external automation
- AgentEngine packages

External-effect operations require preview and approval metadata.

## Skills

Skills provide knowledge and procedures:

- Debugging guides
- Framework checklists
- Review procedures
- Domain templates

`ExtensionRouter` routes relevant skills per work item. `ContextService`
enforces token budgets and records loaded and omitted skill tokens.

## API

New product endpoints:

- `/api/v2/extensions/plugins`
- `/api/v2/extensions/skills`
- `/api/v2/extensions/installed`
- `/api/v2/extensions/search`
- `/api/v2/extensions/install`

Existing `/api/v2/skills/*` endpoints remain temporary compatibility aliases.
