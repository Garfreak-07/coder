import { agentEdgeIdFromIndex } from "../../workflowGraph";
import type { AgentWorkflowSpec, RoleCardSpec } from "../../types";

interface WorkflowStructurePanelProps {
  availableRoleCards: RoleCardSpec[];
  connectionFrom: string;
  connectionTo: string;
  newAgentRoleCard: string;
  selectedAgentId: string | null;
  selectedEdgeId: string | null;
  workflow: AgentWorkflowSpec;
  onAddAgent: () => void;
  onAddConnection: () => void;
  onConnectionFromChange: (value: string) => void;
  onConnectionToChange: (value: string) => void;
  onDeleteAgent: (agentId: string) => void;
  onDeleteConnection: (edgeIndex: number) => void;
  onRoleCardChange: (value: string) => void;
  onSelectAgent: (agentId: string) => void;
  onSelectEdge: (edgeId: string) => void;
}

export function WorkflowStructurePanel({
  availableRoleCards,
  connectionFrom,
  connectionTo,
  newAgentRoleCard,
  selectedAgentId,
  selectedEdgeId,
  workflow,
  onAddAgent,
  onAddConnection,
  onConnectionFromChange,
  onConnectionToChange,
  onDeleteAgent,
  onDeleteConnection,
  onRoleCardChange,
  onSelectAgent,
  onSelectEdge
}: WorkflowStructurePanelProps) {
  return (
    <aside className="workflow-structure-panel">
      <div className="panel-title">Workflow Structure</div>
      <div className="add-agent-card">
        <label>
          Agent type
          <select value={newAgentRoleCard} onChange={(event) => onRoleCardChange(event.target.value)}>
            {availableRoleCards.map((roleCard) => (
              <option key={roleCard.id} value={roleCard.id}>
                {roleCard.label}
              </option>
            ))}
          </select>
        </label>
        <button disabled={availableRoleCards.length === 0} onClick={onAddAgent}>Add</button>
      </div>
      <div className="list compact-list">
        {workflow.agents.map((agent) => (
          <div
            className={`structure-row ${agent.id === selectedAgentId ? "selected" : ""}`}
            key={agent.id}
          >
            <button className="structure-row-main" onClick={() => onSelectAgent(agent.id)}>
              {agent.name}
            </button>
            {agent.id !== workflow.primary_planner_id && (
              <button onClick={() => onDeleteAgent(agent.id)}>Delete</button>
            )}
          </div>
        ))}
      </div>
      <div className="panel-subtitle">Add Connection</div>
      <div className="connection-builder">
        <label>
          From
          <select value={connectionFrom} onChange={(event) => onConnectionFromChange(event.target.value)}>
            {workflow.agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          To
          <select value={connectionTo} onChange={(event) => onConnectionToChange(event.target.value)}>
            {workflow.agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </label>
        <button onClick={onAddConnection}>Add Connection</button>
      </div>
      <div className="panel-subtitle">Connections</div>
      <div className="list compact-list">
        {workflow.edges.map((edge, index) => {
          const edgeId = agentEdgeIdFromIndex(index);
          return (
            <div
              className={`structure-row ${edgeId === selectedEdgeId ? "selected" : ""}`}
              key={`${edge.from}-${edge.to}-${index}`}
            >
              <button className="structure-row-main" onClick={() => onSelectEdge(edgeId)}>
                {agentDisplayName(workflow, edge.from)} -&gt; {agentDisplayName(workflow, edge.to)}
              </button>
              <button onClick={() => onDeleteConnection(index)}>Delete</button>
            </div>
          );
        })}
        {workflow.edges.length === 0 && <div className="muted">No connections yet.</div>}
      </div>
    </aside>
  );
}

function agentDisplayName(workflow: AgentWorkflowSpec, agentId: string): string {
  return workflow.agents.find((agent) => agent.id === agentId)?.name ?? agentId;
}
