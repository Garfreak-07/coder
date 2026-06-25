import { useState } from "react";

import { getArtifact, getBlob, getContextPacket, getToolResult } from "./api";
import type { RunEvent } from "./types";

interface LoopReplayGroup {
  kind: "loop";
  key: string;
  nodeId: string;
  iteration: number;
  events: RunEvent[];
}

type ReplayItem = RunEvent | LoopReplayGroup;

export function EventReplayList({ events, runId }: { events: RunEvent[]; runId: string | null }) {
  return (
    <>
      {groupReplayEvents(events).map((item, index) => {
        if (isLoopReplayGroup(item)) {
          const contextLinks = item.events.filter(isContextPacketEvent).length;
          const artifactLinks = item.events.filter((event) => event.type === "artifact.produced").length;
          const tokenEntries = item.events.filter((event) => event.type === "token.ledger.entry").length;
          return (
            <div className="loop-replay-group" key={item.key}>
              <div className="event-heading">
                <strong>Loop iteration</strong>
                <code>{item.nodeId}</code>
                <span>#{item.iteration}</span>
              </div>
              <div className="summary-grid">
                <span>{item.events.length} events</span>
                <span>{contextLinks} ContextPacket links</span>
                <span>{artifactLinks} Artifact links</span>
                <span>{tokenEntries} TokenLedger entries</span>
              </div>
              {item.events.map((event, eventIndex) => (
                <EventRow event={event} key={event.id ?? `${event.type}-${eventIndex}`} runId={runId} />
              ))}
            </div>
          );
        }
        return <EventRow event={item} key={item.id ?? `${item.type}-${index}`} runId={runId} />;
      })}
    </>
  );
}

function EventRow({ event, runId }: { event: RunEvent; runId: string | null }) {
  const contextPacket = isContextPacketEvent(event);
  const artifact = event.type === "artifact.produced";
  const tokenLedger = event.type === "token.ledger.entry";
  const toolResult = event.type === "tool.result";
  const contextCompaction = event.type === "agent.context_compaction.applied";
  return (
    <div className="event-row" id={eventDomId(event)}>
      <div className="event-heading">
        <strong>{event.type}</strong>
        {event.node_id && <code>{event.node_id}</code>}
      </div>
      <span>{event.message ?? ""}</span>
      {contextPacket && <ContextPacketCard event={event} runId={runId} />}
      {artifact && <ArtifactCard event={event} runId={runId} />}
      {tokenLedger && <TokenLedgerCard event={event} />}
      {toolResult && <ToolResultCard event={event} runId={runId} />}
      {contextCompaction && <ContextCompactionCard event={event} />}
      {!contextPacket &&
        !artifact &&
        !tokenLedger &&
        !toolResult &&
        !contextCompaction &&
        event.payload &&
        Object.keys(event.payload).length > 0 && <pre>{JSON.stringify(event.payload, null, 2)}</pre>}
    </div>
  );
}

function eventDomId(event: RunEvent): string {
  return `event-${String(event.id ?? event.type).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function isLoopReplayGroup(item: ReplayItem): item is LoopReplayGroup {
  return "kind" in item && item.kind === "loop";
}

function isContextPacketEvent(event: RunEvent): boolean {
  return (
    event.type === "agent.context_packet" ||
    event.type === "agent.context_packet_v2" ||
    event.type === "agent.coding_context_packet"
  );
}

function groupReplayEvents(events: RunEvent[]): ReplayItem[] {
  const items: ReplayItem[] = [];
  let group: LoopReplayGroup | null = null;
  for (const event of events) {
    if (event.type === "loop.iteration.started") {
      if (group) items.push(group);
      const meta = loopEventMeta(event);
      group = {
        kind: "loop",
        key: `loop-${meta.nodeId}-${meta.iteration}-${event.id ?? items.length}`,
        nodeId: meta.nodeId,
        iteration: meta.iteration,
        events: [event]
      };
      continue;
    }
    if (group) {
      group.events.push(event);
      if (event.type === "loop.iteration.completed" && loopEventMeta(event).nodeId === group.nodeId) {
        items.push(group);
        group = null;
      }
      continue;
    }
    items.push(event);
  }
  if (group) items.push(group);
  return items;
}

function loopEventMeta(event: RunEvent): { nodeId: string; iteration: number } {
  const payload = objectValue(event.payload);
  return {
    nodeId: String(event.node_id ?? payload?.node_id ?? "loop"),
    iteration: Number(payload?.iteration ?? 0)
  };
}

function ContextPacketCard({ event, runId }: { event: RunEvent; runId: string | null }) {
  const payload = objectValue(event.payload);
  const inlinePacket = payload?.packet;
  const packetId = typeof payload?.packet_id === "string" ? payload.packet_id : null;
  const summary = objectValue(payload?.summary);
  const [loadedPacket, setLoadedPacket] = useState<Record<string, unknown> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadPacket() {
    if (!runId || !packetId || loading) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const detail = await getContextPacket(runId, packetId);
      setLoadedPacket(detail.packet);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }

  const packet = inlinePacket ?? loadedPacket;
  if (!packet || typeof packet !== "object" || Array.isArray(packet)) {
    return (
      <div className="context-packet-card">
        <div className="panel-subtitle">Externalized context packet</div>
        <div className="summary-grid">
          <span>stored separately</span>
          <span>packet: {packetId ?? "inline"}</span>
          <span>size: {String(payload?.size_chars ?? "unknown")}</span>
        </div>
        {summary && <pre>{JSON.stringify(summary, null, 2)}</pre>}
        {packetId && runId && (
          <button onClick={loadPacket} disabled={loading}>
            {loading ? "Loading..." : "Open packet"}
          </button>
        )}
        {loadError && <div className="muted">{loadError}</div>}
      </div>
    );
  }

  const value = packet as Record<string, unknown>;
  if (event.type === "agent.context_packet_v2" || typeof value.agent_id === "string") {
    return <ContextPacketV2Card packet={value} />;
  }

  const agent = objectValue(value.agent);
  const token = objectValue(value.token_estimate);
  const project = objectValue(value.project_context);
  const loop = objectValue(value.loop);
  const selectedKeys = Array.isArray(value.selected_state_keys) ? value.selected_state_keys : [];
  const tools = Array.isArray(value.allowed_tools) ? value.allowed_tools : [];

  return (
    <div className="context-packet-card">
      <div className="panel-subtitle">ContextPacket</div>
      <div className="summary-grid">
        <span>agent: {String(agent?.id ?? "unknown")}</span>
        <span>node: {String(value.node_id ?? "unknown")}</span>
        <span>tokens: {String(token?.packet ?? "unknown")}</span>
        <span>budget: {String(token?.budget ?? "none")}</span>
      </div>
      <div className="muted">Task: {String(value.task ?? "")}</div>
      <div className="muted">Repo: {String(project?.repo_root ?? "")}</div>
      {loop && (
        <div className="approval-card">
          <div className="panel-subtitle">Loop</div>
          <div className="summary-grid">
            <span>{String(loop.node_id ?? "loop")}</span>
            <span>iteration {String(loop.iteration ?? 0)}</span>
            <span>{loop["continue"] ? "continue" : "stopped"}</span>
            <span>{String(loop.break_reason ?? "no break")}</span>
          </div>
        </div>
      )}
      <div className="summary-grid">
        <span>state keys: {selectedKeys.map(String).join(", ") || "none"}</span>
        <span>tools: {tools.map(String).join(", ") || "none"}</span>
      </div>
      <details>
        <summary>View full context packet</summary>
        <pre>{JSON.stringify(value, null, 2)}</pre>
      </details>
    </div>
  );
}

function ContextCompactionCard({ event }: { event: RunEvent }) {
  const payload = objectValue(event.payload);
  const refs = stringList(payload?.externalized_refs);
  return (
    <div className="context-packet-card">
      <div className="panel-subtitle">Compacted context</div>
      <div className="summary-grid">
        <span>work item: {String(payload?.work_item_id ?? "unknown")}</span>
        <span>before: {String(payload?.token_estimate_before ?? "unknown")}</span>
        <span>after: {String(payload?.token_estimate_after ?? "unknown")}</span>
        <span>refs: {refs.length}</span>
      </div>
      {refs.length > 0 && <InlineList title="Externalized refs" values={refs} />}
      {stringList(payload?.warnings).length > 0 && <InlineList title="Warnings" values={stringList(payload?.warnings)} />}
    </div>
  );
}

function ToolResultCard({ event, runId }: { event: RunEvent; runId: string | null }) {
  const payload = objectValue(event.payload);
  const toolResultId = typeof payload?.tool_result_id === "string" ? payload.tool_result_id : null;
  const inlineResult = objectValue(payload?.result);
  const [loadedResult, setLoadedResult] = useState<Record<string, unknown> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadResult() {
    if (!runId || !toolResultId || loading) return;
    setLoading(true);
    setLoadError(null);
    try {
      const detail = await getToolResult(runId, toolResultId);
      const hydrated = await hydrateBlobRefs(detail.result, runId);
      setLoadedResult(objectValue(hydrated) ?? detail.result);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }

  const result = inlineResult ?? loadedResult;
  return (
    <div className="artifact-card">
      <div className="panel-subtitle">Externalized tool result</div>
      <div className="summary-grid">
        <span>{String(payload?.tool ?? "tool")}</span>
        <span>{toolResultId ?? "inline result"}</span>
        <span>size: {String(payload?.result_size_chars ?? "unknown")}</span>
        <span>{String(payload?.result_status ?? "unknown")}</span>
      </div>
      <div className="muted">Tool output persisted. Preview shown.</div>
      {payload?.result_summary !== undefined && <pre>{JSON.stringify(payload.result_summary, null, 2)}</pre>}
      {toolResultId && runId && (
        <button onClick={loadResult} disabled={loading}>
          {loading ? "Loading..." : "Open full output"}
        </button>
      )}
      {loadError && <div className="muted">{loadError}</div>}
      {result && (
        <details open>
          <summary>Tool output</summary>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

function ContextPacketV2Card({ packet }: { packet: Record<string, unknown> }) {
  const includedSkillIds = stringList(packet.included_skill_ids);
  const omittedSkillIds = stringList(packet.omitted_skill_ids);
  const includedRefs = stringList(packet.included_refs);
  const omittedRefs = stringList(packet.omitted_refs);
  return (
    <div className="context-packet-card">
      <div className="panel-subtitle">ContextPacketV2</div>
      <KeyValueList
        items={[
          ["Agent", String(packet.agent_id ?? "unknown")],
          ["Work item", String(packet.work_item_id ?? "unknown")],
          ["Artifact", String(packet.artifact_type ?? "unknown")],
          ["Input tokens", String(packet.estimated_input_tokens ?? 0)],
          ["Omitted tokens", String(packet.estimated_omitted_tokens ?? 0)],
          ["Compression", formatRatio(packet.compression_ratio)]
        ]}
      />
      <div className="summary-grid">
        <span>selected skills: {includedSkillIds.join(", ") || "none"}</span>
        <span>omitted skills: {omittedSkillIds.join(", ") || "none"}</span>
      </div>
      {includedRefs.length > 0 && <InlineList title="Included refs" values={includedRefs} />}
      {omittedRefs.length > 0 && <InlineList title="Omitted refs" values={omittedRefs} />}
      <details>
        <summary>View raw ContextPacketV2</summary>
        <pre>{JSON.stringify(packet, null, 2)}</pre>
      </details>
    </div>
  );
}

function TokenLedgerCard({ event }: { event: RunEvent }) {
  const payload = objectValue(event.payload);
  const entry = objectValue(payload?.entry) ?? payload;
  if (!entry) return null;
  const available = numberValue(entry.skill_tokens_available);
  const loaded = numberValue(entry.skill_tokens_loaded);
  const skillTokens = available === null || loaded === null ? "unknown" : `${loaded}/${available}`;
  return (
    <div className="context-packet-card">
      <div className="panel-subtitle">TokenLedger</div>
      <KeyValueList
        items={[
          ["Agent", String(entry.agent_id ?? "unknown")],
          ["Work item", String(entry.work_item_id ?? "unknown")],
          ["Artifact", String(entry.artifact_type ?? "unknown")],
          ["Skill tokens", skillTokens],
          ["Input tokens", String(entry.estimated_input_tokens ?? 0)],
          ["Output tokens", String(entry.estimated_output_tokens ?? 0)],
          ["Omitted tokens", String(entry.omitted_tokens ?? 0)],
          ["Compression", formatRatio(entry.compression_ratio)]
        ]}
      />
      <details>
        <summary>View raw TokenLedger entry</summary>
        <pre>{JSON.stringify(entry, null, 2)}</pre>
      </details>
    </div>
  );
}

function ArtifactCard({ event, runId }: { event: RunEvent; runId: string | null }) {
  const payload = objectValue(event.payload);
  const artifactId = typeof payload?.artifact_id === "string" ? payload.artifact_id : null;
  const artifactType = typeof payload?.artifact_type === "string" ? payload.artifact_type : "artifact";
  const summary = objectValue(payload?.summary);
  const [loadedArtifact, setLoadedArtifact] = useState<Record<string, unknown> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadArtifact() {
    if (!runId || !artifactId || loading) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const detail = await getArtifact(runId, artifactId);
      setLoadedArtifact(detail.artifact);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="artifact-card">
      <div className="panel-subtitle">Artifact</div>
      <div className="summary-grid">
        <span>{artifactType}</span>
        <span>{artifactId ?? "unknown id"}</span>
        <span>size: {String(payload?.size_chars ?? "unknown")}</span>
      </div>
      <ArtifactPreview artifactType={artifactType} artifact={loadedArtifact ?? summary} />
      {artifactId && runId && (
        <button onClick={loadArtifact} disabled={loading}>
          {loading ? "Loading..." : "Load full artifact"}
        </button>
      )}
      {loadError && <div className="muted">{loadError}</div>}
      {loadedArtifact && (
        <details open>
          <summary>Full artifact</summary>
          <pre>{JSON.stringify(loadedArtifact, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

function ArtifactPreview({
  artifactType,
  artifact
}: {
  artifactType: string;
  artifact: Record<string, unknown> | null;
}) {
  if (!artifact) {
    return <div className="muted">No artifact summary available.</div>;
  }
  if (artifactType === "run_contract") {
    const doneCriteria = stringList(artifact.done_criteria);
    const allowedPaths = stringList(objectValue(artifact.scope)?.allowed_paths);
    const forbiddenPaths = stringList(objectValue(artifact.scope)?.forbidden_paths);
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.user_goal ?? "")}</div>
        <KeyValueList
          items={[
            ["Done criteria", doneCriteria.length > 0 ? String(doneCriteria.length) : String(artifact.done_criteria ?? 0)],
            ["Allowed paths", allowedPaths.join(", ") || "not specified"],
            ["Forbidden paths", forbiddenPaths.join(", ") || "none"],
            ["Max auto rounds", String(artifact.max_auto_rounds ?? objectValue(artifact.loop_policy)?.max_auto_rounds ?? "unknown")]
          ]}
        />
        {doneCriteria.length > 0 && <InlineList title="Done criteria" values={doneCriteria} />}
      </div>
    );
  }
  if (artifactType === "planner_order") {
    const instructions = stringList(artifact.instructions_for_executor);
    const expected = stringList(artifact.expected_outputs);
    const stops = stringList(artifact.stop_and_return_to_planner_when);
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.round_goal ?? "")}</div>
        <KeyValueList
          items={[
            ["Round", String(artifact.round ?? "unknown")],
            ["Risk", String(artifact.risk_level ?? "unknown")],
            ["Human confirmation", String(artifact.requires_human_confirmation ?? false)],
            ["Expected outputs", expected.join(", ") || "none"]
          ]}
        />
        {instructions.length > 0 && <InlineList title="Executor instructions" values={instructions} />}
        {stops.length > 0 && <InlineList title="Return to Planner when" values={stops} />}
      </div>
    );
  }
  if (artifactType === "execution_result") {
    const changedFiles = stringList(artifact.changed_files);
    const unexpected = stringList(artifact.unexpected_issues);
    const verification = objectValue(artifact.verification);
    const checks = objectList(verification?.checks_run).map((check) => {
      const summary = String(check.summary ?? "").trim();
      const prefix = `${String(check.kind ?? "check")}: ${String(check.status ?? "unknown")}`;
      return summary ? `${prefix} - ${summary}` : prefix;
    });
    const evidence = uniqueStrings([
      ...stringList(artifact.evidence_refs),
      ...stringList(verification?.evidence_refs)
    ]);
    const remaining = uniqueStrings([
      ...stringList(artifact.remaining_work),
      ...stringList(verification?.remaining_work)
    ]);
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.summary ?? "")}</div>
        <KeyValueList
          items={[
            ["Round", String(artifact.round ?? "unknown")],
            ["Status", String(artifact.status ?? "unknown")],
            ["Verification", String(verification?.status ?? "unknown")],
            ["Confidence", String(verification?.confidence ?? "unknown")],
            ["Changed files", changedFiles.join(", ") || "none"],
            ["Blocker", String(artifact.blocker_type ?? "none")],
            ["Needs Planner", String(artifact.needs_planner_decision ?? false)]
          ]}
        />
        {unexpected.length > 0 && <InlineList title="Unexpected issues" values={unexpected} />}
        {checks.length > 0 && <InlineList title="Verification checks" values={checks} />}
        {remaining.length > 0 && <InlineList title="Remaining work" values={remaining} />}
        {evidence.length > 0 && <InlineList title="Evidence" values={evidence} />}
      </div>
    );
  }
  if (artifactType === "planner_decision") {
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.reason ?? "")}</div>
        <KeyValueList
          items={[
            ["Round", String(artifact.round ?? "unknown")],
            ["Done", String(artifact.task_done ?? false)],
            ["Next action", String(artifact.next_action ?? "unknown")],
            ["Risk", String(artifact.risk_level ?? "unknown")],
            ["Remaining auto rounds", String(artifact.remaining_auto_rounds ?? "unknown")]
          ]}
        />
      </div>
    );
  }
  if (artifactType === "round_summary") {
    const refs = stringList(artifact.important_refs);
    const remaining = stringList(artifact.remaining_work);
    return (
      <div className="artifact-specific">
        <KeyValueList
          items={[
            ["Round", String(artifact.round ?? "unknown")],
            ["Planner", String(artifact.planner_order_summary ?? "")],
            ["Execution", String(artifact.execution_summary ?? "")],
            ["Plan status", String(artifact.plan_status ?? "unknown")],
            ["Completed", String(artifact.completed_count ?? 0)],
            ["Blocked", String(artifact.blocked_count ?? 0)],
            ["Decision", String(artifact.planner_decision_summary ?? artifact.decision_summary ?? "")]
          ]}
        />
        {refs.length > 0 && <InlineList title="Important refs" values={refs} />}
        {remaining.length > 0 && <InlineList title="Remaining work" values={remaining} />}
      </div>
    );
  }
  if (artifactType === "final_report") {
    const files = objectValue(artifact.files);
    const commit = objectValue(artifact.commit);
    const checks = objectList(artifact.checks).map((check) => {
      const command = String(check.command ?? "").trim();
      const summary = String(check.summary ?? "").trim();
      const prefix = String(check.status ?? "unknown");
      return [prefix, summary, command].filter(Boolean).join(" - ");
    });
    const changedFiles = uniqueStrings([
      ...stringList(files?.created),
      ...stringList(files?.modified),
      ...stringList(files?.deleted)
    ]);
    const blockers = uniqueStrings([
      ...stringList(artifact.blocked_by),
      ...stringList(artifact.failed_by)
    ]);
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.summary ?? "")}</div>
        <KeyValueList
          items={[
            ["Status", String(artifact.status ?? "unknown")],
            ["Commit", String(commit?.sha ?? "none")],
            ["Files", changedFiles.join(", ") || "none"],
            ["Checks", String(checks.length)],
            ["Evidence refs", String(stringList(artifact.evidence_refs).length)]
          ]}
        />
        {checks.length > 0 && <InlineList title="Verification" values={checks} />}
        {blockers.length > 0 && <InlineList title="Blockers" values={blockers} />}
        {stringList(artifact.warnings).length > 0 && <InlineList title="Warnings" values={stringList(artifact.warnings)} />}
        {stringList(artifact.notes).length > 0 && <InlineList title="Notes" values={stringList(artifact.notes)} />}
        {stringList(artifact.next_steps).length > 0 && <InlineList title="Next steps" values={stringList(artifact.next_steps)} />}
        {stringList(artifact.evidence_refs).length > 0 && <InlineList title="Evidence" values={stringList(artifact.evidence_refs)} />}
      </div>
    );
  }
  if (artifactType === "plan_artifact") {
    const targetFiles = stringList(artifact.target_files);
    const steps = stringList(artifact.implementation_steps);
    const risks = stringList(artifact.risks);
    const checks = stringList(artifact.recommended_checks ?? artifact.checks);
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.summary ?? "")}</div>
        <KeyValueList
          items={[
            ["Target files", targetFiles.join(", ") || "none"],
            ["Steps", steps.length > 0 ? String(steps.length) : String(artifact.steps ?? 0)],
            ["Risks", risks.length > 0 ? String(risks.length) : String(artifact.risks ?? 0)],
            ["Checks", checks.join(", ") || "none"]
          ]}
        />
        {steps.length > 0 && <InlineList title="Implementation steps" values={steps} />}
        {risks.length > 0 && <InlineList title="Risks" values={risks} />}
      </div>
    );
  }
  if (artifactType === "patch_artifact") {
    const changedFiles = stringList(artifact.changed_files);
    const risks = stringList(artifact.risks);
    const patches = Array.isArray(artifact.patches) ? artifact.patches : [];
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.implementation_summary ?? artifact.summary ?? "")}</div>
        <KeyValueList
          items={[
            ["Changed files", changedFiles.join(", ") || "none"],
            ["Patches", String(patches.length || artifact.patches || 0)],
            ["Risks", risks.length > 0 ? String(risks.length) : String(artifact.risks ?? 0)],
            ["Suggested check", String(artifact.suggested_check_command ?? "none")]
          ]}
        />
        {patches.length > 0 && <PatchArtifactList patches={patches} />}
        {risks.length > 0 && <InlineList title="Risks" values={risks} />}
      </div>
    );
  }
  if (artifactType === "review_artifact") {
    const evidence = stringList(artifact.evidence);
    const issues = stringList(artifact.issues);
    return (
      <div className="artifact-specific">
        <KeyValueList
          items={[
            ["Status", String(artifact.status ?? "unknown")],
            ["Risk", String(artifact.risk_level ?? "unknown")],
            ["Issues", issues.length > 0 ? String(issues.length) : String(artifact.issues ?? 0)],
            ["Action", String(artifact.recommended_action ?? "none")]
          ]}
        />
        {issues.length > 0 && <InlineList title="Issues" values={issues} />}
        {evidence.length > 0 && <InlineList title="Evidence" values={evidence} />}
      </div>
    );
  }
  return <pre>{JSON.stringify(artifact, null, 2)}</pre>;
}

function KeyValueList({ items }: { items: [string, string][] }) {
  return (
    <div className="artifact-kv">
      {items.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function InlineList({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="artifact-list">
      <div className="panel-subtitle">{title}</div>
      {values.map((value, index) => (
        <div key={`${title}-${index}`}>{value}</div>
      ))}
    </div>
  );
}

function PatchArtifactList({ patches }: { patches: unknown[] }) {
  return (
    <div className="artifact-list">
      <div className="panel-subtitle">Patches</div>
      {patches.slice(0, 6).map((patch, index) => {
        const value = objectValue(patch);
        const diff = value ? value.diff : null;
        return (
          <div key={`patch-${index}`}>
            <strong>{String(value?.path ?? `patch ${index + 1}`)}</strong>
            <span>{String(value?.action ?? "change")}</span>
            {typeof diff === "string" && <code>{diff.slice(0, 180)}</code>}
            {objectValue(diff) && <code>{String(objectValue(diff)?.blob_id ?? "blob reference")}</code>}
          </div>
        );
      })}
      {patches.length > 6 && <div className="muted">+ {patches.length - 6} more patches</div>}
    </div>
  );
}

export function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => (typeof item === "string" ? item : JSON.stringify(item)));
}

export function objectList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const object = objectValue(item);
    return object ? [object] : [];
  });
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values));
}

export async function hydrateBlobRefs(value: unknown, runId: string): Promise<unknown> {
  const object = objectValue(value);
  if (
    object?.blob_id &&
    typeof object.blob_id === "string" &&
    (typeof object.size_chars === "number" || typeof object.original_chars === "number")
  ) {
    const blob = await getBlob(runId, object.blob_id);
    return blob.content;
  }
  if (Array.isArray(value)) {
    return Promise.all(value.map((item) => hydrateBlobRefs(item, runId)));
  }
  if (object) {
    const entries = await Promise.all(
      Object.entries(object).map(async ([key, item]) => [key, await hydrateBlobRefs(item, runId)] as const)
    );
    return Object.fromEntries(entries);
  }
  return value;
}

function numberValue(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatRatio(value: unknown): string {
  const number = numberValue(value);
  if (number === null) return "unknown";
  return `${Math.round(number * 100)}%`;
}

export function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}
