import type { AgentWorkflowSpec } from "./types";
import { defaultPlannerLedAgentWorkflow } from "./examples";

export interface AgentWorkflowTemplateCard {
  id: "default-coding";
  workflow: AgentWorkflowSpec;
  agentCount: number;
  approvals: string;
  modelRequirement: string;
  knowledgeRequirement: string;
  risk: string;
}

export const agentWorkflowTemplateCards: AgentWorkflowTemplateCard[] = [
  {
    id: "default-coding",
    workflow: defaultPlannerLedAgentWorkflow,
    agentCount: 3,
    approvals: "plannerOnlyHuman",
    modelRequirement: "optionalModel",
    knowledgeRequirement: "structuredHandoff",
    risk: "mediumRisk"
  }
];

export function instantiateAgentWorkflowTemplate(template: AgentWorkflowTemplateCard): AgentWorkflowSpec {
  return {
    ...template.workflow,
    id: `${template.workflow.id}-${Date.now()}`,
    agents: template.workflow.agents.map((agent) => ({
      ...agent,
      capabilities: [...agent.capabilities]
    })),
    edges: template.workflow.edges.map((edge) => ({ ...edge })),
    loop_policy: { ...template.workflow.loop_policy },
    ui: {
      layout: Object.fromEntries(
        Object.entries(template.workflow.ui?.layout ?? {}).map(([agentId, position]) => [agentId, { ...position }])
      )
    }
  };
}
