# Capability Boundary Matrix

External capabilities must enter Coder through a harness, a registered tool, and
the existing approval/evidence pipeline. This matrix is the audit record for the
v1 boundary pass.

| Capability | Tool name / entry point | Harness permission | Approval behavior | Evidence emitted | Timeline item |
| --- | --- | --- | --- | --- | --- |
| MCP tool calls | `mcp:{server_id}:{tool_name}` | MCP server manifest + explicit approval | MCP calls are blocked until approved; unknown tools require approval before rejection | `mcp_tool` event with blob refs for large output | `tool_call` / `approval` |
| Skills | `skill.lifecycle`, `skill.auto_update` | Skill manifest side-effect policy | External-effect skills must require preview; auto-update is limited to official low-risk skills | skill summary / validation report | `executor_step` |
| Plugin backend | `plugin:{operation}:{risk}` | Plugin manifest capability policy | Unknown, medium/high-risk, permissioned, or external-effect operations require approval | plugin validation / extension policy result | `tool_call` / `approval` |
| Commands | `run_command_sandbox` | `run_commands` | Model or risky commands emit `approval.requested`; approved commands run bounded in repo cwd | `command_evidence` repo evidence and command events | `command_execution` / `approval` |
| Patch preview | `propose_patch` | `write_files` | Preview is read-only; unsafe patch paths are rejected | `repo_evidence` patch preview | `file_change` |
| Patch apply | `apply_patch_sandbox` | `write_files` | Model patch apply requires approval before writing | `repo_evidence + patch_evidence` and patch events | `file_change` / `approval` |
| Repo find/search | `search_files` | `read_files` | Allowed inside assigned harness; sensitive/runtime dirs are skipped | `repo_evidence` | `tool_call` |
| Repo read | `read_file` | `read_files` | Allowed inside assigned harness; sensitive, binary, oversized, and escaping paths are rejected | `repo_evidence` | `tool_call` |
| Git status/diff | `inspect_git_diff` | `read_files` | Read-only; output is bounded | `repo_evidence` | `tool_call` |
| OpenHands executor | `openhands-code-edit` harness | `write_files`, `run_commands`, `network`, `secrets` as configured | Configured harness uses `ask` for side effects; raw events are normalized and secret-redacted | OpenHands event refs and blob-backed raw event evidence | `reasoning_summary`, `executor_step`, `tool_call`, `file_change` |
| Network | Harness backend only | `network` | Default is `deny`; OpenHands sample uses `ask`; no standalone network page/tool | backend-specific evidence or blocked status | `executor_step` / `approval` |
| Secrets | Provider settings / harness backend | `secrets` | Default is `deny`; provider keys are in-memory or env fallback and are never returned in full | redacted provider status; no JSONL plaintext keys | setup/status only, no raw secret timeline |
| Git commit | no direct public tool | `git_commit` | Default is `deny`; must be added as a registered harness tool before use | none today | none today |
| Git push | no direct public tool | `git_push` | Default is `deny`; must be added as a registered harness tool before use | none today | none today |
| Deploy | no direct public tool | `deploy` | Default is `deny`; must be added as a registered harness tool before use | none today | none today |

## Runtime Rules

- Server tool endpoints call the registered tool boundary before execution.
- Registered tool entries expose `required_permission`, `approval_behavior`,
  `evidence_emitted`, and `timeline_item` through `/api/v3/harness/tools`.
- Low-risk read tools are allowed only inside their assigned harness and still
  emit bounded evidence.
- Write, command, network, secret, publish, commit, push, and deploy abilities
  must not appear as standalone UI actions unless they are backed by a registered
  harness tool and approval behavior.
- Public timeline items are projections over events and evidence. They must not
  expose raw backend payloads or provider secrets.
