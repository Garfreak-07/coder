# Plugin And Skills Page

The React Plugins & Skills page is available from the sidebar and is backed by
local Rust API v3 endpoints.

Frontend files:

```text
frontend/src/features/plugins/PluginsPage.tsx
frontend/src/features/plugins/PluginMarketplace.tsx
frontend/src/features/plugins/InstalledPlugins.tsx
frontend/src/features/plugins/SkillDetailsPanel.tsx
frontend/src/features/plugins/McpDependenciesPanel.tsx
frontend/src/features/plugins/HooksPanel.tsx
frontend/src/features/plugins/PluginSettingsPanel.tsx
```

Backend surfaces:

```text
GET  /api/v3/plugins/marketplaces
POST /api/v3/plugins/marketplaces
DELETE /api/v3/plugins/marketplaces/{name}
POST /api/v3/plugins/marketplaces/{name}/upgrade

GET /api/v3/plugins
GET /api/v3/plugins/installed
GET /api/v3/plugins/{plugin_id}
GET /api/v3/plugins/{plugin_id}/skills/{skill_name}

GET  /api/v3/skills/extra-roots
POST /api/v3/skills/extra-roots
GET  /api/v3/hooks
```

Milestone scope:

- local marketplace list
- installed plugins and skills
- skill detail read
- enable/disable/pin/update/remove/rollback through existing skill APIs
- MCP dependency display
- hook display
- cache/settings display

Deferred:

- remote sharing
- shared-with-me
- public marketplace publishing
- cloud auth
- paid marketplace
