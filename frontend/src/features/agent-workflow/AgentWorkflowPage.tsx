import {
  Background,
  MiniMap,
  ReactFlow,
  type Connection,
  type Edge as FlowEdge,
  type EdgeChange,
  type Node as FlowNode,
  type NodeChange
} from "@xyflow/react";

import { AgentWorkflowValidationPanel } from "./AgentWorkflowValidationPanel";
import { WorkflowSelector } from "./WorkflowSelector";
import { WorkflowStructurePanel } from "./WorkflowStructurePanel";
import type {
  AgentWorkflowSpec,
  AgentWorkflowValidationResult,
  LibraryIndex,
  RoleCardSpec
} from "../../types";

interface AgentWorkflowPageProps {
  agentWorkflow: AgentWorkflowSpec;
  availableRoleCards: RoleCardSpec[];
  connectionFrom: string;
  connectionTo: string;
  edges: FlowEdge[];
  library: LibraryIndex;
  newAgentRoleCard: string;
  nodes: FlowNode[];
  selectedAgentId: string | null;
  selectedEdgeId: string | null;
  validation: AgentWorkflowValidationResult | null;
  onAddAgent: () => void;
  onAddConnection: () => void;
  onConnectionFromChange: (value: string) => void;
  onConnectionToChange: (value: string) => void;
  onDeleteAgent: (agentId: string) => void;
  onDeleteConnection: (edgeIndex: number) => void;
  onEdgeClick: (edgeId: string) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onExport: () => void;
  onImport: (file: File | null) => void;
  onLoadDefault: () => void;
  onMaxRoundsChange: (rounds: number) => void;
  onNodeClick: (nodeId: string) => void;
  onNodesChange: (changes: NodeChange[]) => void;
  onConnect: (connection: Connection) => void;
  onRoleCardChange: (value: string) => void;
  onSave: () => void;
  onSaveAs: () => void;
  onSelectWorkflow: (workflowId: string) => void;
  onWorkflowNameChange: (name: string) => void;
}

export function AgentWorkflowPage({
  agentWorkflow,
  availableRoleCards,
  connectionFrom,
  connectionTo,
  edges,
  library,
  newAgentRoleCard,
  nodes,
  selectedAgentId,
  selectedEdgeId,
  validation,
  onAddAgent,
  onAddConnection,
  onConnectionFromChange,
  onConnectionToChange,
  onDeleteAgent,
  onDeleteConnection,
  onEdgeClick,
  onEdgesChange,
  onExport,
  onImport,
  onLoadDefault,
  onMaxRoundsChange,
  onNodeClick,
  onNodesChange,
  onConnect,
  onRoleCardChange,
  onSave,
  onSaveAs,
  onSelectWorkflow,
  onWorkflowNameChange
}: AgentWorkflowPageProps) {
  return (
    <main className="workflow-page">
      <section className="workflow-page-header">
        <div>
          <h2>Agent Workflow</h2>
        </div>
        <div className="button-row">
          <button onClick={onSave}>Save</button>
          <button onClick={onSaveAs}>Save As</button>
          <label className="file-button">
            Import
            <input
              type="file"
              accept="application/json,.json"
              onChange={(event) => onImport(event.target.files?.[0] ?? null)}
            />
          </label>
          <button onClick={onExport}>Export</button>
        </div>
      </section>

      <section className="workflow-controls-row">
        <WorkflowSelector
          workflows={library.agent_workflows}
          value={agentWorkflow.id}
          onLoadDefault={onLoadDefault}
          onSelect={onSelectWorkflow}
        />
        <label>
          Workflow name
          <input value={agentWorkflow.name} onChange={(event) => onWorkflowNameChange(event.target.value)} />
        </label>
        <label>
          Max auto rounds
          <input
            type="number"
            min={1}
            max={20}
            value={agentWorkflow.loop_policy.max_auto_rounds}
            onChange={(event) => onMaxRoundsChange(Number(event.target.value))}
          />
        </label>
      </section>

      <AgentWorkflowValidationPanel result={validation} />

      <section className="workflow-editor-layout">
        <div className="canvas-panel workflow-canvas-panel">
          <div className="workflow-flow-shell">
            <ReactFlow
              className="workflow-flow"
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              nodesConnectable
              deleteKeyCode="Backspace"
              onNodeClick={(_, node) => onNodeClick(node.id)}
              onEdgeClick={(_, edge) => onEdgeClick(edge.id)}
              fitView
            >
              <Background />
              <MiniMap className="workflow-minimap" position="top-left" style={{ width: 120, height: 80 }} />
            </ReactFlow>
          </div>
        </div>

        <WorkflowStructurePanel
          availableRoleCards={availableRoleCards}
          connectionFrom={connectionFrom}
          connectionTo={connectionTo}
          newAgentRoleCard={newAgentRoleCard}
          selectedAgentId={selectedAgentId}
          selectedEdgeId={selectedEdgeId}
          workflow={agentWorkflow}
          onAddAgent={onAddAgent}
          onAddConnection={onAddConnection}
          onConnectionFromChange={onConnectionFromChange}
          onConnectionToChange={onConnectionToChange}
          onDeleteAgent={onDeleteAgent}
          onDeleteConnection={onDeleteConnection}
          onRoleCardChange={onRoleCardChange}
          onSelectAgent={onNodeClick}
          onSelectEdge={onEdgeClick}
        />
      </section>
    </main>
  );
}
