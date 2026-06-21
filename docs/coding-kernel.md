# Coding Kernel

The Coding Kernel owns repository intelligence and controlled local effects.

Current services:

- `ContextService`: builds `ContextPacketV2`, selected skill context,
  coding context packets, and token ledger entries.
- `PatchService`: validates proposed changes, guards risk paths, creates patch
  previews, applies approved patches, and rolls back snapshots.
- `CommandService`: validates cwd/scope, enforces approval for product checks,
  runs sandbox/local checks, and captures output.
- `ArtifactRepairService`: central one-shot JSON artifact repair for
  Planner/Worker/Tester paths.

Agent Engines receive prepared context and return artifacts. Patch/check effects
remain behind runtime services.
