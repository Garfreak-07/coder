import type {
  AgentWorkflowAgent,
  RoleCardSpec
} from "../../types";

interface AgentWorkflowAgentInspectorProps {
  agent: AgentWorkflowAgent;
  roleCards: RoleCardSpec[];
  isPrimaryPlanner: boolean;
  onChange: (patch: Partial<AgentWorkflowAgent>) => void;
}

export function AgentWorkflowAgentInspector({
  agent,
  roleCards,
  isPrimaryPlanner,
  onChange
}: AgentWorkflowAgentInspectorProps) {
  const selectedRoleCard =
    roleCards.find((card) => card.id === agent.role_card) ??
    (!isPrimaryPlanner ? roleCards.find((card) => card.role === agent.role) ?? null : null);

  function applyRoleCard(roleCardId: string) {
    const roleCard = roleCards.find((card) => card.id === roleCardId);
    if (!roleCard) {
      return;
    }
    onChange({
      role_card: roleCard.id,
      role: roleCard.role,
      capabilities: [...roleCard.default_capabilities],
      can_talk_to_human: false,
      model_tier: "standard"
    });
  }

  return (
    <div className="form-stack agent-editor">
      <div className="summary-grid">
        <span>{selectedRoleCard?.label ?? agent.role}</span>
        <span>{isPrimaryPlanner ? "User-facing Planner" : "Planner-directed"}</span>
      </div>
      <label>
        Name
        <input value={agent.name} onChange={(event) => onChange({ name: event.target.value })} />
      </label>
      <label>
        Purpose
        <textarea
          value={agent.purpose ?? ""}
          onChange={(event) => onChange({ purpose: event.target.value })}
          rows={3}
        />
      </label>
      {isPrimaryPlanner ? (
        <div className="agent-policy-summary">
          <div className="panel-subtitle">Planner</div>
          <div className="muted">Primary Planner</div>
        </div>
      ) : (
        <label>
          Role
          <select value={selectedRoleCard?.id ?? ""} onChange={(event) => applyRoleCard(event.target.value)}>
            {roleCards.map((roleCard) => (
              <option key={roleCard.id} value={roleCard.id}>
                {roleCard.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {selectedRoleCard && <div className="muted">{selectedRoleCard.description}</div>}
    </div>
  );
}
