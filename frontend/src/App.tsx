import { useCallback, useEffect, useMemo, useState } from "react";
import {
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge as FlowEdge,
  type EdgeChange,
  type Node as FlowNode,
  type NodeChange
} from "@xyflow/react";
import {
  deleteRun,
  getAgentWorkflow,
  getDefaultAgentWorkflow,
  getLibrary,
  getLiveAgentRun,
  getRun,
  getRunEvents,
  getToolResult,
  rollbackPatch,
  saveAgentWorkflow,
  startLiveAgentRun,
  submitPlannerResponse,
  subscribeRunEvents,
  validateAgentWorkflow
} from "./api";
import { defaultPlannerLedAgentWorkflow } from "./examples";
import { AppSidebar, type AppSection } from "./components/AppSidebar";
import { ProviderSettingsPanel } from "./components/ProviderSettingsPanel";
import { AgentWorkflowPage } from "./features/agent-workflow/AgentWorkflowPage";
import { PlannerChatPage, type PlannerStrength } from "./features/planner-chat/PlannerChatPage";
import { SkillsPanel } from "./features/skills/SkillsPanel";
import { useProviderSettings } from "./hooks/useProviderSettings";
import { useRuntimeInfo } from "./hooks/useRuntimeInfo";
import { enUS } from "./i18n";
import { EventReplayList, hydrateBlobRefs, objectList, objectValue, stringList } from "./runEvents";
import {
  agentEdgeIdFromIndex,
  agentEdgeIndexFromId,
  cleanAgentWorkflowEdge,
  cloneAgentWorkflow,
  downloadJson,
  linesToList,
  normalizeAgentWorkflow,
  toAgentFlowEdges,
  toAgentFlowNodes
} from "./workflowGraph";
import type {
  AgentModelTier,
  AgentWorkflowAgent,
  AgentWorkflowValidationResult,
  AgentWorkflowSpec,
  LibraryIndex,
  LiveRunDetail,
  RunEvent,
  RunSummaryItem,
  StoredRunDetail
} from "./types";

const t = enUS;
const initialAgentWorkflow = cloneAgentWorkflow(defaultPlannerLedAgentWorkflow);

export function App() {
  const [activeSection, setActiveSection] = useState<AppSection>("chat");
  const [library, setLibrary] = useState<LibraryIndex>({ agents: [], agent_workflows: [] });
  const [agentWorkflow, setAgentWorkflow] = useState<AgentWorkflowSpec>(() => cloneAgentWorkflow(initialAgentWorkflow));
  const [agentWorkflowValidation, setAgentWorkflowValidation] = useState<AgentWorkflowValidationResult | null>(null);
  const [nodes, setNodes] = useState<FlowNode[]>(() => toAgentFlowNodes(initialAgentWorkflow));
  const [edges, setEdges] = useState<FlowEdge[]>(() => toAgentFlowEdges(initialAgentWorkflow));
  const [selectedAgentWorkflowId, setSelectedAgentWorkflowId] = useState<string | null>("planner");
  const [selectedAgentWorkflowEdgeId, setSelectedAgentWorkflowEdgeId] = useState<string | null>(null);
  const [status, setStatus] = useState(t.app.defaultStatus);
  const [repo, setRepo] = useState(".");
  const [scopesText, setScopesText] = useState("");
  const [request, setRequest] = useState("Inspect this project and propose the next safe step.");
  const [submittedRequest, setSubmittedRequest] = useState("");
  const [plannerResponse, setPlannerResponse] = useState("");
  const [plannerResponseLoading, setPlannerResponseLoading] = useState(false);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [eventCursor, setEventCursor] = useState(0);
  const [eventHasMore, setEventHasMore] = useState(false);
  const [eventsLoadingMore, setEventsLoadingMore] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyStatusFilter, setHistoryStatusFilter] = useState("all");
  const [newAgentRoleCard, setNewAgentRoleCard] = useState("executor");
  const [connectionFrom, setConnectionFrom] = useState("planner");
  const [connectionTo, setConnectionTo] = useState("executor");
  const {
    runHistory,
    liveRuns,
    health,
    roleCards,
    refreshRuntimeInfo
  } = useRuntimeInfo(setStatus);
  const {
    providerSettings,
    providerStatus,
    providerForm,
    updateProviderForm,
    refreshProviderInfo,
    persistProviderSettings,
    runProviderTest
  } = useProviderSettings(setStatus);
  const [selectedRunDetail, setSelectedRunDetail] = useState<StoredRunDetail | LiveRunDetail | null>(null);
  const [selectedRunKind, setSelectedRunKind] = useState<"live" | "stored" | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const primaryPlannerAgent = useMemo(
    () => agentWorkflow.agents.find((agent) => agent.id === agentWorkflow.primary_planner_id) ?? null,
    [agentWorkflow.agents, agentWorkflow.primary_planner_id]
  );
  const availableRoleCards = useMemo(
    () => roleCards.filter((roleCard) => roleCard.id === "executor" || roleCard.id === "tester"),
    [roleCards]
  );
  const connectionFromValue = useMemo(
    () => resolveAgentSelectValue(agentWorkflow, connectionFrom, 0),
    [agentWorkflow, connectionFrom]
  );
  const connectionToValue = useMemo(
    () => resolveAgentSelectValue(agentWorkflow, connectionTo, 1),
    [agentWorkflow, connectionTo]
  );
  const filteredRunHistory = useMemo(
    () => filterRunHistory(runHistory, historyQuery, historyStatusFilter),
    [runHistory, historyQuery, historyStatusFilter]
  );

  useEffect(() => {
    refreshLibrary();
    refreshRuntimeInfo();
    refreshProviderInfo();
  }, []);

  function refreshLibrary() {
    getLibrary()
      .then(setLibrary)
      .catch((error) => setStatus(`Failed to load library: ${error.message}`));
  }

  async function openStoredRun(runId: string) {
    setStatus(`Loading stored run ${runId}...`);
    try {
      const detail = await getRun(runId, false);
      const eventPage = await getRunEvents(runId);
      const hydrated = {
        ...detail,
        result: {
          ...detail.result,
          events: eventPage.events
        }
      };
      setSelectedRunKind("stored");
      setSelectedRunDetail(hydrated);
      setActiveRunId(null);
      setEvents(eventPage.events);
      setEventCursor(eventPage.next_cursor);
      setEventHasMore(eventPage.has_more);
      setEventsLoadingMore(false);
      setRepo(detail.repo_root);
      setRequest(detail.request);
      setSubmittedRequest(detail.request);
      setStatus(
        eventPage.has_more
          ? `Stored run ${runId}: ${detail.result.status} (${eventPage.events.length}+ events)`
          : `Stored run ${runId}: ${detail.result.status}`
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function loadMoreStoredEvents() {
    if (selectedRunKind !== "stored" || !selectedRunDetail || eventsLoadingMore || !eventHasMore) {
      return;
    }
    const runId = selectedRunDetail.id;
    setEventsLoadingMore(true);
    try {
      const eventPage = await getRunEvents(runId, eventCursor);
      setEvents((current) => mergeEvents(current, eventPage.events));
      setSelectedRunDetail((current) => {
        if (!current || current.id !== runId || selectedRunKind !== "stored") return current;
        const stored = current as StoredRunDetail;
        return {
          ...stored,
          result: {
            ...stored.result,
            events: mergeEvents(stored.result.events, eventPage.events)
          }
        };
      });
      setEventCursor(eventPage.next_cursor);
      setEventHasMore(eventPage.has_more);
      setStatus(`Stored run ${runId}: loaded ${eventPage.next_cursor} events`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setEventsLoadingMore(false);
    }
  }

  async function openLiveRun(runId: string, attach = false) {
    setStatus(`Loading live run ${runId}...`);
    try {
      const detail = await getLiveAgentRun(runId);
      setSelectedRunKind("live");
      setSelectedRunDetail(detail);
      setActiveRunId(detail.id);
      setEvents(detail.events);
      setEventCursor(0);
      setEventHasMore(false);
      setEventsLoadingMore(false);
      setRepo(detail.repo_root);
      setRequest(detail.request);
      setSubmittedRequest(detail.request);
      setStatus(`Live run ${runId}: ${detail.status}`);
      if (attach || detail.status === "queued" || detail.status === "running") {
        subscribeToRun(detail.id, liveEventsUrl(detail));
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  function renderWorkflowCanvas(nextAgentWorkflow: AgentWorkflowSpec) {
    setNodes(toAgentFlowNodes(nextAgentWorkflow));
    setEdges(toAgentFlowEdges(nextAgentWorkflow));
  }

  function setCurrentAgentWorkflow(next: AgentWorkflowSpec) {
    const clean = normalizeAgentWorkflow(cloneAgentWorkflow(next));
    setAgentWorkflow(clean);
    renderWorkflowCanvas(clean);
    setSelectedAgentWorkflowId(clean.agents[0]?.id ?? null);
    setSelectedAgentWorkflowEdgeId(null);
  }

  function updateAgentWorkflow(mutator: (current: AgentWorkflowSpec) => AgentWorkflowSpec) {
    const next = normalizeAgentWorkflow(mutator(cloneAgentWorkflow(agentWorkflow)));
    setAgentWorkflow(next);
    setAgentWorkflowValidation(null);
    renderWorkflowCanvas(next);
  }

  function updatePlannerStrength(strength: PlannerStrength) {
    const modelTier = modelTierForPlannerStrength(strength);
    updateAgentWorkflow((current) => ({
      ...current,
      agents: current.agents.map((agent) =>
        agent.id === current.primary_planner_id ? { ...agent, model_tier: modelTier } : agent
      )
    }));
  }

  async function loadDefaultAgentWorkflow() {
    setStatus("Loading default Agent workflow...");
    try {
      const payload = await getDefaultAgentWorkflow();
      setCurrentAgentWorkflow(payload.agent_workflow);
      setStatus(`Loaded ${payload.agent_workflow.name}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function loadAgentWorkflow(workflowId: string) {
    setStatus(`Loading Agent workflow ${workflowId}...`);
    try {
      const agentWorkflow = await getAgentWorkflow(workflowId);
      setCurrentAgentWorkflow(agentWorkflow);
      setStatus(`Loaded Agent workflow ${workflowId}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function persistWorkflow() {
    try {
      const workflow = normalizeAgentWorkflow(agentWorkflow);
      const validation = await validateAgentWorkflow(workflow);
      setAgentWorkflowValidation(validation);
      if (validation.status === "error") {
        setCurrentAgentWorkflow(workflow);
        setStatus("Save blocked by Agent workflow validation errors.");
        return;
      }
      const saved = await saveAgentWorkflow(workflow);
      setCurrentAgentWorkflow(saved);
      refreshLibrary();
      setStatus(`Saved Agent workflow ${saved.id}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function persistWorkflowAsCopy() {
    try {
      const workflow = normalizeAgentWorkflow({
        ...agentWorkflow,
        id: uniqueWorkflowId(agentWorkflow.name || agentWorkflow.id)
      });
      const validation = await validateAgentWorkflow(workflow);
      setAgentWorkflowValidation(validation);
      if (validation.status === "error") {
        setCurrentAgentWorkflow(workflow);
        setStatus("Save As blocked by Agent workflow validation errors.");
        return;
      }
      const saved = await saveAgentWorkflow(workflow);
      setCurrentAgentWorkflow(saved);
      refreshLibrary();
      setStatus(`Saved new Agent workflow ${saved.id}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  function exportWorkflow() {
    const workflow = normalizeAgentWorkflow(agentWorkflow);
    downloadJson(`${workflow.id || "agent-workflow"}.json`, workflow);
    setStatus(`Exported Agent workflow ${workflow.id || "agent-workflow"}`);
  }

  function importWorkflow(file: File | null) {
    if (!file) return;
    file
      .text()
      .then(async (text) => {
        const raw = JSON.parse(text) as AgentWorkflowSpec;
        const rawId = String(raw.id ?? "imported-workflow");
        const idExists = library.agent_workflows.some((workflow) => workflow.id === rawId);
        const parsed = normalizeAgentWorkflow({
          ...raw,
          id: idExists ? `${rawId}-${Date.now()}` : rawId
        });
        setCurrentAgentWorkflow(parsed);
        const validation = await validateAgentWorkflow(parsed);
        setAgentWorkflowValidation(validation);
        if (validation.status !== "error") {
          const saved = await saveAgentWorkflow(parsed);
          setCurrentAgentWorkflow(saved);
          refreshLibrary();
          setStatus(idExists ? `Imported as new Agent workflow ${saved.id}` : `Imported Agent workflow ${saved.id}`);
          return;
        }
        setStatus(
          validation.status === "error"
            ? `Imported Agent workflow ${parsed.id} with validation errors`
            : `Imported Agent workflow ${parsed.id}`
        );
      })
      .catch((error) => setStatus(error instanceof Error ? `Import failed: ${error.message}` : "Import failed"));
  }

  function uniqueAgentWorkflowAgentId(current: AgentWorkflowSpec, role: string) {
    const used = new Set(current.agents.map((agent) => agent.id));
    let index = 1;
    let candidate = role;
    while (used.has(candidate)) {
      index += 1;
      candidate = `${role}_${index}`;
    }
    return candidate;
  }

  function addAgentWorkflowAgent() {
    const roleCard = availableRoleCards.find((card) => card.id === newAgentRoleCard) ?? availableRoleCards[0];
    if (!roleCard) {
      setStatus("Role cards are unavailable.");
      return;
    }
    const id = uniqueAgentWorkflowAgentId(agentWorkflow, roleCard.role);
    const agent: AgentWorkflowAgent = {
      id,
      name: nextAgentDisplayName(agentWorkflow, roleCard.role),
      role: roleCard.role,
      role_card: roleCard.id,
      model_tier: "standard",
      can_talk_to_human: false,
      capabilities: [...roleCard.default_capabilities]
    };
    updateAgentWorkflow((current) => {
      const layout = { ...(current.ui?.layout ?? {}) };
      const index = current.agents.length;
      layout[id] = { x: 80 + (index % 3) * 280, y: 120 + Math.floor(index / 3) * 170 };
      return {
        ...current,
        agents: [...current.agents, agent],
        ui: { ...(current.ui ?? {}), layout }
      };
    });
    setSelectedAgentWorkflowId(id);
    setSelectedAgentWorkflowEdgeId(null);
    setStatus(`Added ${agent.name}.`);
  }

  function removeAgentWorkflowAgent(agentId = selectedAgentWorkflowId) {
    if (!agentId) return;
    const target = agentWorkflow.agents.find((agent) => agent.id === agentId);
    if (!target) return;
    if (agentId === agentWorkflow.primary_planner_id) {
      setStatus("Primary Planner cannot be deleted.");
      return;
    }
    updateAgentWorkflow((current) => {
      const layout = { ...(current.ui?.layout ?? {}) };
      delete layout[agentId];
      return {
        ...current,
        agents: current.agents.filter((agent) => agent.id !== agentId),
        edges: current.edges.filter((edge) => edge.from !== agentId && edge.to !== agentId),
        ui: { ...(current.ui ?? {}), layout }
      };
    });
    setSelectedAgentWorkflowId((current) => (current === agentId ? agentWorkflow.primary_planner_id : current));
    setSelectedAgentWorkflowEdgeId(null);
    setStatus(`Deleted ${target.name}.`);
  }

  const onAgentNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const removedIds = changes.filter((change) => change.type === "remove").map((change) => change.id);
      const blockedPrimaryDelete = removedIds.includes(agentWorkflow.primary_planner_id);
      const removableIds = new Set(removedIds.filter((id) => id !== agentWorkflow.primary_planner_id));
      if (blockedPrimaryDelete) {
        setStatus("Primary Planner cannot be deleted.");
      }
      const allowedChanges = changes.filter((change) => change.type !== "remove" || removableIds.has(change.id));
      setNodes((currentNodes) => {
        const nextNodes = applyNodeChanges(allowedChanges, currentNodes);
        setAgentWorkflow((currentWorkflow) => {
          const layout = { ...(currentWorkflow.ui?.layout ?? {}) };
          const agentIds = new Set(currentWorkflow.agents.map((agent) => agent.id));
          for (const node of nextNodes) {
            if (agentIds.has(node.id)) {
              layout[node.id] = { x: node.position.x, y: node.position.y };
            }
          }
          for (const removedId of removableIds) {
            delete layout[removedId];
          }
          const nextWorkflow = normalizeAgentWorkflow({
            ...currentWorkflow,
            agents: currentWorkflow.agents.filter((agent) => !removableIds.has(agent.id)),
            edges: currentWorkflow.edges.filter((edge) => !removableIds.has(edge.from) && !removableIds.has(edge.to)),
            ui: { ...(currentWorkflow.ui ?? {}), layout }
          });
          setAgentWorkflowValidation(null);
          setSelectedAgentWorkflowId((current) =>
            current && removableIds.has(current) ? nextWorkflow.agents[0]?.id ?? null : current
          );
          setSelectedAgentWorkflowEdgeId((current) => (current && removedIds.length > 0 ? null : current));
          return nextWorkflow;
        });
        return nextNodes;
      });
    },
    [agentWorkflow.primary_planner_id]
  );

  const onAgentEdgesChange = useCallback((changes: EdgeChange[]) => {
    const removedIndexes = new Set(
      changes
        .filter((change) => change.type === "remove")
        .map((change) => agentEdgeIndexFromId(change.id))
        .filter((index): index is number => index !== null)
    );
    setEdges((current) => applyEdgeChanges(changes, current));
    if (removedIndexes.size > 0) {
      setAgentWorkflow((currentWorkflow) => {
        const nextWorkflow = {
          ...currentWorkflow,
          edges: currentWorkflow.edges.filter((_, index) => !removedIndexes.has(index))
        };
        setEdges(toAgentFlowEdges(nextWorkflow));
        setAgentWorkflowValidation(null);
        setSelectedAgentWorkflowEdgeId(null);
        return nextWorkflow;
      });
    }
  }, []);

  function onAgentConnect(connection: Connection) {
    const source = connection.source;
    const target = connection.target;
    if (!source || !target) return;
    if (source === target) {
      setStatus("Agent edges must connect two different Agents.");
      return;
    }
    if (agentWorkflow.edges.some((edge) => edge.from === source && edge.to === target)) {
      setStatus(`Edge ${source} -> ${target} already exists.`);
      return;
    }
    updateAgentWorkflow((current) => ({
      ...current,
      edges: [...current.edges, cleanAgentWorkflowEdge({ from: source, to: target }, current.primary_planner_id)]
    }));
    setSelectedAgentWorkflowEdgeId(agentEdgeIdFromIndex(agentWorkflow.edges.length));
    setSelectedAgentWorkflowId(null);
    setStatus(`Connected ${source} -> ${target}.`);
  }

  function addWorkflowConnection() {
    const source = connectionFromValue;
    const target = connectionToValue;
    if (!source || !target) {
      setStatus("Choose two Agents before adding a connection.");
      return;
    }
    if (source === target) {
      setStatus("Agent edges must connect two different Agents.");
      return;
    }
    if (agentWorkflow.edges.some((edge) => edge.from === source && edge.to === target)) {
      setStatus(`Connection ${agentDisplayName(agentWorkflow, source)} -> ${agentDisplayName(agentWorkflow, target)} already exists.`);
      return;
    }
    updateAgentWorkflow((current) => ({
      ...current,
      edges: [...current.edges, cleanAgentWorkflowEdge({ from: source, to: target }, current.primary_planner_id)]
    }));
    setSelectedAgentWorkflowId(null);
    setSelectedAgentWorkflowEdgeId(agentEdgeIdFromIndex(agentWorkflow.edges.length));
    setStatus(`Connected ${agentDisplayName(agentWorkflow, source)} -> ${agentDisplayName(agentWorkflow, target)}.`);
  }

  function removeAgentWorkflowEdge(edgeIndex: number) {
    const edge = agentWorkflow.edges[edgeIndex];
    if (!edge) return;
    updateAgentWorkflow((current) => ({
      ...current,
      edges: current.edges.filter((_, index) => index !== edgeIndex)
    }));
    setSelectedAgentWorkflowEdgeId(null);
    setStatus(`Deleted connection ${agentDisplayName(agentWorkflow, edge.from)} -> ${agentDisplayName(agentWorkflow, edge.to)}.`);
  }

  async function runWorkflow() {
    const requestText = request.trim();
    if (!requestText) return;
    setRunLoading(true);
    setStatus("Validating Agent workflow...");
    try {
      const workflow = normalizeAgentWorkflow(agentWorkflow);
      const validation = await validateAgentWorkflow(workflow);
      setAgentWorkflowValidation(validation);
      setCurrentAgentWorkflow(workflow);
      if (validation.status === "error") {
        setStatus("Run blocked by Agent workflow validation errors.");
        return;
      }
      const scopes = linesToList(scopesText);
      setEvents([]);
      setEventCursor(0);
      setEventHasMore(false);
      setEventsLoadingMore(false);
      setActiveRunId(null);
      setStatus("Starting Agent workflow run...");
      setSubmittedRequest(requestText);
      setRequest("");
      const run = await startLiveAgentRun({
        repo,
        request: requestText,
        agent_workflow: workflow,
        approved: false,
        scopes
      });
      setActiveRunId(run.run_id);
      setSelectedRunKind("live");
      setSelectedRunDetail(null);
      setStatus(`Live Agent run ${run.run_id}: ${run.status}`);
      subscribeToRun(run.run_id, run.events_url);
      refreshRuntimeInfo();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setRunLoading(false);
    }
  }

  async function submitPlannerHumanResponse() {
    const liveDetail = selectedRunKind === "live" ? (selectedRunDetail as LiveRunDetail | null) : null;
    const runId = liveDetail?.id ?? activeRunId;
    const response = plannerResponse.trim();
    if (!runId || !response) return;
    setPlannerResponseLoading(true);
    setStatus(`Sending Planner response for ${runId}...`);
    try {
      const resumed = await submitPlannerResponse(runId, { response, data: { source: "planner_chat" } });
      setPlannerResponse("");
      setActiveRunId(resumed.run_id);
      setSelectedRunKind("live");
      setStatus(`Planner response accepted for ${resumed.run_id}: ${resumed.status}`);
      subscribeToRun(resumed.run_id, resumed.events_url);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setPlannerResponseLoading(false);
    }
  }

  async function deleteStoredRun(runId: string) {
    if (!window.confirm(`Delete stored run ${runId}? This also removes blobs no other run references.`)) {
      return;
    }
    setStatus(`Deleting stored run ${runId}...`);
    try {
      const result = await deleteRun(runId);
      setSelectedRunDetail(null);
      setSelectedRunKind(null);
      setEvents([]);
      setEventCursor(0);
      setEventHasMore(false);
      refreshRuntimeInfo();
      setStatus(`Deleted ${result.run_id}; removed ${result.orphan_blobs_removed} orphan blob(s).`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  function subscribeToRun(runId: string, eventsUrl: string) {
    const source = subscribeRunEvents(
      eventsUrl,
      (event) => {
        setEvents((current) => {
          const isDuplicate = Boolean(event.id && current.some((existing) => existing.id === event.id));
          if (!isDuplicate && isTerminalRunEvent(event.type)) {
            source.close();
          }
          return upsertEvent(current, event);
        });
      },
      () => {
        setStatus(`Event stream closed for ${runId}`);
        source.close();
      }
    );
  }

  function liveEventsUrl(detail: LiveRunDetail) {
    return `/api/v2/live-agent-runs/${detail.id}/events`;
  }

  const isWaitingForPlannerResponse = isWaitingForPlannerHumanResponse(selectedRunDetail, selectedRunKind);
  const chatRunStatus = selectedRunDetail
    ? runStatusLabel(selectedRunDetail, selectedRunKind)
    : activeRunId
      ? "running"
      : "ready";
  const plannerStrength = plannerStrengthFromTier(primaryPlannerAgent?.model_tier ?? "best");
  const chatEvidence = (
    <div className="chat-evidence-stack">
      <RunSummary events={events} />
      <RunEvidenceCards events={events} />
      <PatchPanel
        events={events}
        runId={selectedRunKind === "stored" ? selectedRunDetail?.id ?? null : null}
        repo={repo}
        scopes={linesToList(scopesText)}
        onStatus={setStatus}
      />
      {events.length > 0 && (
        <details className="event-log-details">
          <summary>Event log</summary>
          <EventReplayList
            events={events}
            runId={selectedRunKind === "stored" ? selectedRunDetail?.id ?? null : null}
          />
        </details>
      )}
    </div>
  );

  return (
    <div className="app-shell">
      <AppSidebar activeSection={activeSection} status={status} onSectionChange={setActiveSection} />

      {activeSection === "chat" ? (
        <PlannerChatPage
          activeRunId={activeRunId}
          evidence={chatEvidence}
          isWaitingForPlannerResponse={isWaitingForPlannerResponse}
          plannerPrompt={plannerPromptText(selectedRunDetail)}
          plannerResponse={plannerResponse}
          plannerResponseLoading={plannerResponseLoading}
          repo={repo}
          request={request}
          runLoading={runLoading}
          runStatus={chatRunStatus}
          scopesText={scopesText}
          submittedRequest={submittedRequest}
          plannerStrength={plannerStrength}
          onPlannerResponseChange={setPlannerResponse}
          onRepoChange={setRepo}
          onRequestChange={setRequest}
          onScopesTextChange={setScopesText}
          onPlannerStrengthChange={updatePlannerStrength}
          onSubmitPlannerResponse={submitPlannerHumanResponse}
          onSubmitRequest={runWorkflow}
        />
      ) : activeSection === "workflow" ? (
        <AgentWorkflowPage
          agentWorkflow={agentWorkflow}
          availableRoleCards={availableRoleCards}
          connectionFrom={connectionFromValue}
          connectionTo={connectionToValue}
          edges={edges}
          library={library}
          newAgentRoleCard={newAgentRoleCard}
          nodes={nodes}
          selectedAgentId={selectedAgentWorkflowId}
          selectedEdgeId={selectedAgentWorkflowEdgeId}
          validation={agentWorkflowValidation}
          onAddAgent={addAgentWorkflowAgent}
          onAddConnection={addWorkflowConnection}
          onConnectionFromChange={setConnectionFrom}
          onConnectionToChange={setConnectionTo}
          onDeleteAgent={removeAgentWorkflowAgent}
          onDeleteConnection={removeAgentWorkflowEdge}
          onEdgeClick={(edgeId) => {
            setSelectedAgentWorkflowEdgeId(edgeId);
            setSelectedAgentWorkflowId(null);
          }}
          onEdgesChange={onAgentEdgesChange}
          onExport={exportWorkflow}
          onImport={importWorkflow}
          onLoadDefault={loadDefaultAgentWorkflow}
          onMaxRoundsChange={(rounds) =>
            updateAgentWorkflow((current) => ({
              ...current,
              loop_policy: { ...current.loop_policy, max_auto_rounds: rounds }
            }))
          }
          onNodeClick={(nodeId) => {
            setSelectedAgentWorkflowId(nodeId);
            setSelectedAgentWorkflowEdgeId(null);
          }}
          onNodesChange={onAgentNodesChange}
          onConnect={onAgentConnect}
          onRoleCardChange={setNewAgentRoleCard}
          onSave={persistWorkflow}
          onSaveAs={persistWorkflowAsCopy}
          onSelectWorkflow={(workflowId) => {
            if (workflowId) loadAgentWorkflow(workflowId);
          }}
          onWorkflowNameChange={(name) => updateAgentWorkflow((current) => ({ ...current, name }))}
        />
      ) : activeSection === "extensions" ? (
        <main className="page-main">
          <SkillsPanel onStatus={setStatus} />
        </main>
      ) : activeSection === "runs" ? (
        <main className="page-main page-grid">
          <section className="panel">
            <div className="panel-title">{t.runtime.title}</div>
            <button onClick={refreshRuntimeInfo}>{t.runtime.refresh}</button>
            <div className="summary-grid">
              <span>{health?.status ?? t.runtime.unknown}</span>
              <span>{t.runtime.tools(health?.tools.length ?? 0)}</span>
              <span>{t.runtime.liveRuns(liveRuns.length)}</span>
              <span>{t.runtime.storedRuns(runHistory.length)}</span>
            </div>
            <div className="panel-subtitle">Live</div>
            <div className="list compact-list">
              {liveRuns.map((run) => (
                <button className="list-item" key={run.id} onClick={() => openLiveRun(run.id)}>
                  <span>{run.workflow_id}</span>
                  <small>{run.status} / {run.events} events</small>
                </button>
              ))}
              {liveRuns.length === 0 && <div className="muted">{t.runtime.noLiveRuns}</div>}
            </div>
            <div className="panel-subtitle">{t.runtime.storedHistory}</div>
            <div className="history-filters">
              <input
                placeholder="Search runs"
                value={historyQuery}
                onChange={(event) => setHistoryQuery(event.target.value)}
              />
              <select value={historyStatusFilter} onChange={(event) => setHistoryStatusFilter(event.target.value)}>
                <option value="all">All statuses</option>
                <option value="completed">Completed</option>
                <option value="blocked">Blocked</option>
                <option value="failed">Failed</option>
              </select>
            </div>
            <div className="list compact-list">
              {filteredRunHistory.map((run) => (
                <button className="list-item" key={run.id} onClick={() => openStoredRun(run.id)}>
                  <span>{run.workflow_id}</span>
                  <small>
                    {run.status}
                    {run.status_code ? `:${run.status_code}` : ""} / {run.events} events
                  </small>
                </button>
              ))}
              {runHistory.length === 0 && <div className="muted">{t.runtime.noStoredRuns}</div>}
              {runHistory.length > 0 && filteredRunHistory.length === 0 && <div className="muted">No runs match the filter.</div>}
            </div>
          </section>
          <section className="panel events-panel">
            <div className="panel-title">{t.events.title}</div>
            <RunDetailCard
              detail={selectedRunDetail}
              kind={selectedRunKind}
              activeRunId={activeRunId}
              onAttach={(runId) => openLiveRun(runId, true)}
              onOpenStored={(runId) => openStoredRun(runId)}
              onDeleteStored={(runId) => deleteStoredRun(runId)}
            />
            <RunSummary
              events={events}
            />
            <PatchPanel
              events={events}
              runId={selectedRunKind === "stored" ? selectedRunDetail?.id ?? null : null}
              repo={repo}
              scopes={linesToList(scopesText)}
              onStatus={setStatus}
            />
            {events.length === 0 ? (
              <div className="muted">{t.events.empty}</div>
            ) : (
              <EventReplayList
                events={events}
                runId={selectedRunKind === "stored" ? selectedRunDetail?.id ?? null : null}
              />
            )}
            {selectedRunKind === "stored" && eventHasMore && (
              <button onClick={loadMoreStoredEvents} disabled={eventsLoadingMore}>
                {eventsLoadingMore ? "Loading events..." : "Load more events"}
              </button>
            )}
          </section>
        </main>
      ) : (
        <main className="page-main page-grid">
          <section className="panel">
            <div className="panel-title">Provider Settings</div>
            <ProviderSettingsPanel
              form={providerForm}
              settings={providerSettings}
              status={providerStatus}
              onChange={updateProviderForm}
              onSave={persistProviderSettings}
              onRefresh={refreshProviderInfo}
              onTest={runProviderTest}
            />
          </section>
        </main>
      )}
    </div>
  );
}

function runStatusLabel(detail: StoredRunDetail | LiveRunDetail, kind: "live" | "stored" | null): string {
  if (kind === "stored" && "result" in detail) return detail.result?.status ?? "unknown";
  return (detail as LiveRunDetail).status ?? "unknown";
}

function isWaitingForPlannerHumanResponse(
  detail: StoredRunDetail | LiveRunDetail | null,
  kind: "live" | "stored" | null
): boolean {
  if (!detail || kind !== "live") return false;
  const live = detail as LiveRunDetail;
  return live.status === "blocked" && live.result?.status_code === "planner_ask_human";
}

function plannerPromptText(detail: StoredRunDetail | LiveRunDetail | null): string {
  if (!detail || !("result" in detail) || !detail.result) return "The Planner is waiting for your response.";
  const checkpoint = objectValue(detail.result.resume_checkpoint);
  const checkpointData = objectValue(checkpoint?.data);
  const resultData = objectValue(detail.result.data);
  return String(
    checkpointData?.planner_human_prompt ??
      resultData?.planner_human_prompt ??
      detail.result.status_reason ??
      "The Planner is waiting for your response."
  );
}

function plannerStrengthFromTier(tier: AgentModelTier | string): PlannerStrength {
  if (tier === "economy") return "fast";
  if (tier === "standard") return "balanced";
  return "strong";
}

function modelTierForPlannerStrength(strength: PlannerStrength): AgentModelTier {
  if (strength === "fast") return "economy";
  if (strength === "balanced") return "standard";
  return "best";
}

function uniqueWorkflowId(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug || "agent-workflow"}-${Date.now()}`;
}

function resolveAgentSelectValue(workflow: AgentWorkflowSpec, preferredId: string, fallbackIndex: number): string {
  if (workflow.agents.some((agent) => agent.id === preferredId)) return preferredId;
  return workflow.agents[fallbackIndex]?.id ?? workflow.agents[0]?.id ?? "";
}

function nextAgentDisplayName(workflow: AgentWorkflowSpec, role: string): string {
  const base = role === "tester" ? "Tester" : "Executor";
  const count = workflow.agents.filter((agent) => agent.role === role).length;
  return count === 0 ? base : `${base} ${count + 1}`;
}

function agentDisplayName(workflow: AgentWorkflowSpec, agentId: string): string {
  return workflow.agents.find((agent) => agent.id === agentId)?.name ?? agentId;
}

const evidenceArtifactTypes = new Set([
  "planner_order",
  "execution_result",
  "test_result",
  "planner_decision",
  "round_summary",
  "patch_preview",
  "sandbox_apply",
  "check_result",
  "debug_finding",
  "runtime_action"
]);

function RunEvidenceCards({ events }: { events: RunEvent[] }) {
  const artifactCards = events
    .filter((event) => event.type === "artifact.produced")
    .map((event) => evidenceFromArtifactEvent(event))
    .filter((item): item is EvidenceCardModel => item !== null);
  const toolCards = [
    evidenceFromToolResult("patch_preview", "Patch Preview", latestToolResult(events, "propose_patch") ?? latestToolResult(events, "dry_patch")),
    evidenceFromToolResult("sandbox_apply", "Sandbox Apply", latestToolResult(events, "apply_patch")),
    evidenceFromToolResult("check_result", "Check Result", latestToolResult(events, "check"))
  ].filter((item): item is EvidenceCardModel => item !== null);
  const cards = dedupeEvidenceCards([...artifactCards, ...toolCards]).slice(-12);

  if (events.length === 0) return null;
  if (cards.length === 0) {
    return (
      <div className="evidence-empty">
        <div className="panel-subtitle">Evidence</div>
        <div className="muted">No Planner-facing artifacts yet. Evidence cards appear as the run progresses.</div>
      </div>
    );
  }

  return (
    <div className="evidence-card-list">
      {cards.map((card) => (
        <article className={`evidence-card evidence-${statusClass(card.status)}`} key={card.key}>
          <div className="evidence-card-heading">
            <strong>{card.title}</strong>
            <span>{card.status}</span>
          </div>
          {card.summary && <p>{card.summary}</p>}
          <div className="summary-grid">
            {card.round && <span>round {card.round}</span>}
            {card.nextAction && <span>next: {card.nextAction}</span>}
            {card.needsPlanner && <span>needs Planner</span>}
            {card.ref && <span>{card.ref}</span>}
          </div>
          {card.files.length > 0 && <InlineTextList title="Files" values={card.files} />}
          {card.commands.length > 0 && <InlineTextList title="Commands / checks" values={card.commands} />}
        </article>
      ))}
    </div>
  );
}

interface EvidenceCardModel {
  key: string;
  title: string;
  status: string;
  summary: string;
  round: string | null;
  nextAction: string | null;
  needsPlanner: boolean;
  files: string[];
  commands: string[];
  ref: string | null;
}

function evidenceFromArtifactEvent(event: RunEvent): EvidenceCardModel | null {
  const payload = objectValue(event.payload);
  const artifactType = String(payload?.artifact_type ?? "");
  if (!evidenceArtifactTypes.has(artifactType)) return null;
  const summary = objectValue(payload?.summary) ?? payload ?? {};
  const title = evidenceTitle(artifactType);
  return {
    key: `${artifactType}-${String(payload?.artifact_id ?? event.id ?? title)}`,
    title,
    status: evidenceStatus(summary, artifactType),
    summary: evidenceSummary(summary, event.message ?? ""),
    round: valueString(summary.round),
    nextAction: valueString(summary.next_action),
    needsPlanner: Boolean(summary.needs_planner_decision),
    files: evidenceFiles(summary),
    commands: evidenceCommands(summary),
    ref: valueString(payload?.artifact_id)
  };
}

function evidenceFromToolResult(key: string, title: string, result: Record<string, unknown> | null): EvidenceCardModel | null {
  if (!result) return null;
  return {
    key,
    title,
    status: evidenceStatus(result, key),
    summary: evidenceSummary(result, ""),
    round: valueString(result.round),
    nextAction: null,
    needsPlanner: Boolean(result.needs_planner_decision),
    files: evidenceFiles(result),
    commands: evidenceCommands(result),
    ref: valueString(result.output_ref ?? result.tool_result_id)
  };
}

function dedupeEvidenceCards(cards: EvidenceCardModel[]): EvidenceCardModel[] {
  const seen = new Set<string>();
  return cards.filter((card) => {
    if (seen.has(card.key)) return false;
    seen.add(card.key);
    return true;
  });
}

function evidenceTitle(type: string): string {
  return type
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function evidenceStatus(value: Record<string, unknown>, fallback: string): string {
  if (typeof value.status === "string") return value.status;
  if (typeof value.result_status === "string") return value.result_status;
  if (typeof value.next_action === "string") return value.next_action;
  if (typeof value.passed === "boolean") return value.passed ? "passed" : "not passed";
  return fallback;
}

function evidenceSummary(value: Record<string, unknown>, fallback: string): string {
  for (const key of ["summary", "reason", "round_goal", "message", "compressed_summary"]) {
    if (typeof value[key] === "string" && value[key]) return String(value[key]);
  }
  return fallback;
}

function evidenceFiles(value: Record<string, unknown>): string[] {
  const direct = stringList(value.changed_files);
  if (direct.length > 0) return direct;
  const files = objectList(value.files).map((file) => String(file.path ?? file.name ?? ""));
  if (files.length > 0) return files.filter(Boolean);
  return objectList(value.proposed_changes).map((file) => String(file.path ?? "")).filter(Boolean);
}

function evidenceCommands(value: Record<string, unknown>): string[] {
  return [
    value.command,
    value.check_command,
    value.suggested_check_command,
    value.argv ? JSON.stringify(value.argv) : null
  ]
    .filter((item): item is string => typeof item === "string" && item.length > 0)
    .slice(0, 4);
}

function valueString(value: unknown): string | null {
  if (typeof value === "string" && value) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}

function InlineTextList({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="inline-text-list">
      <span>{title}</span>
      <div>
        {values.slice(0, 5).map((value) => (
          <code key={value}>{value}</code>
        ))}
        {values.length > 5 && <code>+{values.length - 5} more</code>}
      </div>
    </div>
  );
}

function PatchPanel({
  events,
  runId,
  repo,
  scopes,
  onStatus
}: {
  events: RunEvent[];
  runId: string | null;
  repo: string;
  scopes: string[];
  onStatus: (status: string) => void;
}) {
  const [loadedToolResults, setLoadedToolResults] = useState<Record<string, Record<string, unknown>>>({});
  const [toolResultErrors, setToolResultErrors] = useState<Record<string, string>>({});
  const [rollbackResult, setRollbackResult] = useState<Record<string, unknown> | null>(null);
  const [rollbackLoading, setRollbackLoading] = useState(false);
  const toolResultIds = useMemo(() => storedToolResultIds(events), [events]);
  const toolResultKey = toolResultIds.join("|");

  useEffect(() => {
    if (!runId) {
      setLoadedToolResults((current) => (Object.keys(current).length > 0 ? {} : current));
      setToolResultErrors((current) => (Object.keys(current).length > 0 ? {} : current));
      return;
    }
    let cancelled = false;
    const missing = toolResultIds.filter((id) => !loadedToolResults[id] && !toolResultErrors[id]);
    for (const id of missing) {
      getToolResult(runId, id)
        .then(async (detail) => {
          if (cancelled) return;
          const hydrated = await hydrateBlobRefs(detail.result, runId);
          if (cancelled) return;
          setLoadedToolResults((current) => ({ ...current, [id]: hydrated as Record<string, unknown> }));
        })
        .catch((error) => {
          if (cancelled) return;
          setToolResultErrors((current) => ({
            ...current,
            [id]: error instanceof Error ? error.message : String(error)
          }));
        });
    }
    return () => {
      cancelled = true;
    };
  }, [runId, toolResultKey, loadedToolResults, toolResultErrors, toolResultIds]);

  const patch = latestToolResult(events, "propose_patch", loadedToolResults) ?? latestToolResult(events, "dry_patch", loadedToolResults);
  const apply = latestToolResult(events, "apply_patch", loadedToolResults);
  const check = latestToolResult(events, "check", loadedToolResults);
  const files = Array.isArray(patch?.files) ? patch.files : [];
  const snapshotId = typeof apply?.snapshot_id === "string" ? apply.snapshot_id : null;
  const applyErrors = Array.isArray(apply?.errors) ? apply.errors : [];
  const isLoadingToolResult = runId ? toolResultIds.some((id) => !loadedToolResults[id] && !toolResultErrors[id]) : false;
  const toolResultErrorMessages = Object.values(toolResultErrors);
  const relatedObjects = useMemo(() => relatedPatchObjects(events), [events]);

  async function rollback() {
    if (!snapshotId) return;
    onStatus(`Rolling back snapshot ${snapshotId}...`);
    setRollbackLoading(true);
    setRollbackResult(null);
    try {
      const result = await rollbackPatch({ repo, snapshot_id: snapshotId, scopes });
      setRollbackResult(result.rollback);
      onStatus(String(result.rollback.message ?? `Rolled back ${snapshotId}`));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRollbackResult({ status: "failed", message });
      onStatus(message);
    } finally {
      setRollbackLoading(false);
    }
  }

  if (!patch && !apply && !check) return null;

  return (
    <div className="patch-panel">
      {(relatedObjects.artifacts.length > 0 || relatedObjects.contexts.length > 0) && (
        <div>
          <div className="panel-subtitle">Related Run Objects</div>
          <div className="object-links">
            {relatedObjects.artifacts.map((item) => (
              <a href={`#${eventDomId(item.event)}`} key={item.event.id}>
                {item.type}: {item.id.slice(0, 12)}
              </a>
            ))}
            {relatedObjects.contexts.map((item) => (
              <a href={`#${eventDomId(item.event)}`} key={item.event.id}>
                context: {item.id.slice(0, 12)}
              </a>
            ))}
          </div>
        </div>
      )}
      {patch && (
        <div>
          <div className="panel-subtitle">Patch Preview</div>
          {files.length === 0 && isLoadingToolResult ? (
            <div className="muted">Loading full tool result...</div>
          ) : files.length === 0 ? (
            <div className="muted">No file changes proposed.</div>
          ) : (
            files.map((file, index) => {
              const item = file as Record<string, unknown>;
              return (
                <div className="diff-block" key={`${String(item.path)}-${index}`}>
                  <div className="event-heading">
                    <strong>{String(item.path ?? "unknown")}</strong>
                    <code>{String(item.action ?? "update")}</code>
                  </div>
                  <pre>{String(item.diff ?? "")}</pre>
                </div>
              );
            })
          )}
        </div>
      )}
      {toolResultErrorMessages.length > 0 && (
        <div className="muted">Tool result load failed: {toolResultErrorMessages.join("; ")}</div>
      )}
      {apply && (
        <div>
          <div className="panel-subtitle">Patch Apply</div>
          <div className="summary-grid">
            <span>{String(apply.status ?? "unknown")}</span>
            {snapshotId && <span>snapshot {snapshotId.slice(0, 8)}</span>}
          </div>
          {typeof apply.message !== "undefined" && <div className="muted">{String(apply.message)}</div>}
          {applyErrors.length > 0 && (
            <div className="patch-errors">
              {applyErrors.map((error, index) => {
                const item = error as Record<string, unknown>;
                return (
                  <div className="patch-error" key={`${String(item.path ?? "unknown")}-${index}`}>
                    <strong>{String(item.path ?? "unknown")}</strong>
                    <code>{String(item.code ?? "error")}</code>
                    <span>{String(item.message ?? "Patch apply rejected.")}</span>
                  </div>
                );
              })}
            </div>
          )}
          {snapshotId && (
            <button onClick={rollback} disabled={rollbackLoading}>
              {rollbackLoading ? "Rolling back..." : "Rollback snapshot"}
            </button>
          )}
          {rollbackResult && (
            <div className="rollback-status">
              <div className="panel-subtitle">Rollback Status</div>
              <div className="summary-grid">
                <span>{String(rollbackResult.status ?? "unknown")}</span>
                <span>{String(rollbackResult.snapshot_id ?? snapshotId ?? "no snapshot")}</span>
                <span>{Array.isArray(rollbackResult.restored) ? `${rollbackResult.restored.length} files` : "files unknown"}</span>
              </div>
              {typeof rollbackResult.message !== "undefined" && <div className="muted">{String(rollbackResult.message)}</div>}
            </div>
          )}
        </div>
      )}
      {check && (
        <div>
          <div className="panel-subtitle">Check Result</div>
          <div className="summary-grid">
            <span>{check.passed ? "passed" : "not passed"}</span>
            {typeof check.returncode === "number" && <span>exit {check.returncode}</span>}
          </div>
          {typeof check.output !== "undefined" && <pre>{String(check.output)}</pre>}
        </div>
      )}
    </div>
  );
}

function relatedPatchObjects(events: RunEvent[]) {
  const artifacts = events
    .filter((event) => event.type === "artifact.produced")
    .map((event) => {
      const type = String(event.payload?.artifact_type ?? "artifact");
      const id = String(event.payload?.artifact_id ?? event.id ?? "artifact");
      return { event, type, id };
    })
    .filter((item) => item.type === "patch_artifact" || item.type === "plan_artifact")
    .slice(-4);
  const contexts = events
    .filter((event) => event.type === "agent.context_packet")
    .map((event) => {
      const id = String(event.payload?.packet_id ?? event.id ?? "context");
      return { event, id };
    })
    .slice(-4);
  return { artifacts, contexts };
}

function eventDomId(event: RunEvent): string {
  return `event-${String(event.id ?? event.type).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function RunDetailCard({
  detail,
  kind,
  activeRunId,
  onAttach,
  onOpenStored,
  onDeleteStored
}: {
  detail: StoredRunDetail | LiveRunDetail | null;
  kind: "live" | "stored" | null;
  activeRunId: string | null;
  onAttach: (runId: string) => void;
  onOpenStored: (runId: string) => void;
  onDeleteStored: (runId: string) => void;
}) {
  if (!detail || !kind) return null;
  const result = "result" in detail ? detail.result : null;
  const status = kind === "stored" ? result?.status : (detail as LiveRunDetail).status;
  const events = kind === "stored" ? result?.events.length ?? 0 : (detail as LiveRunDetail).events.length;
  const liveDetail = kind === "live" ? (detail as LiveRunDetail) : null;
  const canAttach = liveDetail?.status === "queued" || liveDetail?.status === "running" || liveDetail?.status === "blocked";
  const canApprove = liveDetail?.status === "blocked" && Boolean(liveDetail.approval_required);

  return (
    <div className="run-detail-card">
      <div className="event-heading">
        <strong>{kind === "live" ? "Live run detail" : "Stored run detail"}</strong>
        <code>{detail.id}</code>
      </div>
      <div className="summary-grid">
        <span>{status ?? "unknown"}</span>
        <span>{events} events</span>
        {result && <span>{result.agent_calls} agent calls</span>}
        {result && <span>{result.tool_calls} tool calls</span>}
        {result && <span>{result.estimated_tokens_used} est. tokens</span>}
        {result?.blocked_node_id && <span>blocked at {result.blocked_node_id}</span>}
        {result?.status_code && <span>{result.status_code}</span>}
      </div>
      {result?.status_reason && <div className="muted">Reason: {result.status_reason}</div>}
      <div className="muted">Repo: {detail.repo_root}</div>
      <div className="muted">Request: {detail.request}</div>
      {liveDetail?.stored_run_id && (
        <button onClick={() => onOpenStored(liveDetail.stored_run_id as string)}>
          Open stored result
        </button>
      )}
      {canAttach && (
        <button disabled={activeRunId === detail.id && canApprove} onClick={() => onAttach(detail.id)}>
          {canApprove ? "Reattach blocked run" : "Reattach event stream"}
        </button>
      )}
      {kind === "stored" && <button onClick={() => onDeleteStored(detail.id)}>Delete stored run</button>}
      {liveDetail?.error && <div className="muted">Error: {liveDetail.error}</div>}
    </div>
  );
}

function latestToolResult(
  events: RunEvent[],
  nodeId: string,
  loadedToolResults: Record<string, Record<string, unknown>> = {}
): Record<string, unknown> | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type === "tool.result" && event.node_id === nodeId) {
      const result = event.payload?.result;
      if (result && typeof result === "object" && !Array.isArray(result)) return result as Record<string, unknown>;
      const toolResultId = typeof event.payload?.tool_result_id === "string" ? event.payload.tool_result_id : null;
      if (toolResultId && loadedToolResults[toolResultId]) return loadedToolResults[toolResultId];
      const resultStatus = event.payload?.result_status;
      if (typeof resultStatus === "string") {
        return {
          status: resultStatus,
          summary: event.payload?.result_summary,
          keys: event.payload?.result_keys,
          tool_result_id: toolResultId
        };
      }
      continue;
    }
    if (event.type !== "node.completed" || event.node_id !== nodeId) continue;
    const result = event.payload?.result;
    if (result && typeof result === "object" && !Array.isArray(result)) return result as Record<string, unknown>;
    const resultStatus = event.payload?.result_status;
    if (typeof resultStatus === "string") {
      return {
        status: resultStatus,
        summary: event.payload?.result_summary,
        keys: event.payload?.result_keys
      };
    }
  }
  return null;
}

function storedToolResultIds(events: RunEvent[]): string[] {
  const ids = new Set<string>();
  for (const event of events) {
    if (event.type !== "tool.result") continue;
    const toolResultId = typeof event.payload?.tool_result_id === "string" ? event.payload.tool_result_id : null;
    if (toolResultId && !event.payload?.result) ids.add(toolResultId);
  }
  return [...ids];
}

function RunSummary({ events }: { events: RunEvent[] }) {
  const latest = events.at(-1);
  const agentCalls = events.filter((event) => event.type === "agent.called").length;
  const toolCalls = events.filter((event) => event.type === "tool.called").length;
  const selectedEdges = events.filter((event) => event.type === "edge.selected").length;
  const approvalRequests = events.filter((event) => event.type === "approval.required");
  const approvalRecords = events.filter((event) => event.type === "approval.recorded");
  const latestApproval = pendingApprovalEvent(events);
  const isBlocked = latest?.type === "run.blocked";
  const latestPayload = objectValue(latest?.payload);

  if (events.length === 0) return null;

  return (
    <div className="run-summary">
      <div>
        <span className={`status-pill ${statusClass(latest?.type)}`}>{latest?.type ?? "running"}</span>
      </div>
      <div className="summary-grid">
        <span>{events.length} events</span>
        <span>{agentCalls} agent calls</span>
        <span>{toolCalls} tool calls</span>
        <span>{selectedEdges} edges</span>
      </div>
      {!latestApproval && isBlocked && (
        <div className="approval-card">
          <div className="panel-subtitle">Blocked</div>
          <div className="summary-grid">
            <span>{String(latestPayload?.code ?? "blocked")}</span>
            <span>{String(latestPayload?.reason ?? latest?.message ?? "")}</span>
          </div>
        </div>
      )}
      {latestApproval && isBlocked && (
        <div className="approval-card">
          <div className="panel-subtitle">Pending Approval</div>
          <div className="summary-grid">
            <span>{String(latestApproval.payload?.approval_type ?? "human_gate")}</span>
            <span>{latestApproval.node_id ?? "unknown node"}</span>
          </div>
          {typeof latestApproval.payload?.command !== "undefined" && <pre>{String(latestApproval.payload.command)}</pre>}
          {typeof latestApproval.payload?.reason !== "undefined" && <div className="muted">{String(latestApproval.payload.reason)}</div>}
        </div>
      )}
      {approvalRecords.length > 0 && (
        <div className="approval-card">
          <div className="panel-subtitle">Approval Audit</div>
          {approvalRecords.map((event) => (
            <div className="approval-record" key={event.id}>
              <span>{String(event.payload?.approval_type ?? "approval")}</span>
              <span>{event.payload?.approved ? "approved" : "rejected"}</span>
              <span>{String(event.payload?.node_id ?? event.node_id ?? "unknown node")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function upsertEvent(events: RunEvent[], next: RunEvent): RunEvent[] {
  if (!next.id) return [...events, next];
  return events.some((event) => event.id === next.id) ? events : [...events, next];
}

function mergeEvents(events: RunEvent[], incoming: RunEvent[]): RunEvent[] {
  return incoming.reduce((current, event) => upsertEvent(current, event), events);
}

function pendingApprovalEvent(events: RunEvent[]): RunEvent | null {
  const latestApproval = [...events].reverse().find((event) => event.type === "approval.required");
  if (!latestApproval) return null;
  const latestRecord = [...events].reverse().find((event) => event.type === "approval.recorded");
  if (!latestRecord) return latestApproval;
  const approvalTime = Date.parse(String(latestApproval.created_at ?? ""));
  const recordTime = Date.parse(String(latestRecord.created_at ?? ""));
  if (Number.isFinite(approvalTime) && Number.isFinite(recordTime) && recordTime >= approvalTime) {
    return null;
  }
  return latestApproval;
}

function filterRunHistory(runs: RunSummaryItem[], query: string, status: string): RunSummaryItem[] {
  const needle = query.trim().toLowerCase();
  return runs.filter((run) => {
    if (status !== "all" && run.status !== status) return false;
    if (!needle) return true;
    return [
      run.id,
      run.workflow_id,
      run.repo_root,
      run.request,
      run.status,
      run.status_code ?? "",
      run.status_reason ?? ""
    ]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });
}

function isTerminalRunEvent(type: string): boolean {
  return (
    type === "run.completed" ||
    type === "run.failed" ||
    type === "run.blocked" ||
    type === "agent_graph.run.completed" ||
    type === "agent_graph.run.failed" ||
    type === "agent_graph.run.blocked"
  );
}

function statusClass(type: string | undefined): string {
  if (type === "run.completed" || type === "agent_graph.run.completed") return "good";
  if (type === "run.failed" || type === "agent_graph.run.failed") return "bad";
  if (type === "run.blocked" || type === "agent_graph.run.blocked" || type === "approval.required") return "warn";
  return "";
}

