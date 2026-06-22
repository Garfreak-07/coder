import type { AgentWorkflowSummary } from "../../types";

interface WorkflowSelectorProps {
  workflows: AgentWorkflowSummary[];
  value: string;
  onLoadDefault: () => void;
  onSelect: (workflowId: string) => void;
}

export function WorkflowSelector({ workflows, value, onLoadDefault, onSelect }: WorkflowSelectorProps) {
  return (
    <div className="workflow-selector">
      <label>
        Saved workflow
        <select value={value} onChange={(event) => onSelect(event.target.value)}>
          <option value="">Select a saved workflow</option>
          {workflows.map((workflow) => (
            <option key={workflow.id} value={workflow.id}>
              {workflow.name ?? workflow.id} - {workflow.agents} agents / {workflow.edges} edges /{" "}
              {workflow.max_auto_rounds ?? 3} rounds
            </option>
          ))}
        </select>
      </label>
      <button onClick={onLoadDefault}>Load Default</button>
    </div>
  );
}
