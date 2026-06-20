import { useState } from "react";

import { getArtifact, getBlob, getContextPacket } from "./api";
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
          const contextLinks = item.events.filter((event) => event.type === "agent.context_packet").length;
          const artifactLinks = item.events.filter((event) => event.type === "artifact.produced").length;
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
  return (
    <div className="event-row" id={eventDomId(event)}>
      <div className="event-heading">
        <strong>{event.type}</strong>
        {event.node_id && <code>{event.node_id}</code>}
      </div>
      <span>{event.message ?? ""}</span>
      {event.type === "agent.context_packet" && <ContextPacketCard event={event} runId={runId} />}
      {event.type === "artifact.produced" && <ArtifactCard event={event} runId={runId} />}
      {event.type !== "agent.context_packet" &&
        event.type !== "artifact.produced" &&
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
        <div className="panel-subtitle">ContextPacket</div>
        <div className="summary-grid">
          <span>packet: {packetId ?? "inline"}</span>
          <span>size: {String(payload?.size_chars ?? "unknown")}</span>
        </div>
        {summary && <pre>{JSON.stringify(summary, null, 2)}</pre>}
        {packetId && runId && (
          <button onClick={loadPacket} disabled={loading}>
            {loading ? "Loading..." : "Load full packet"}
          </button>
        )}
        {loadError && <div className="muted">{loadError}</div>}
      </div>
    );
  }

  const value = packet as Record<string, unknown>;
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
        <summary>查看完整上下文包</summary>
        <pre>{JSON.stringify(value, null, 2)}</pre>
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
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.summary ?? "")}</div>
        <KeyValueList
          items={[
            ["Round", String(artifact.round ?? "unknown")],
            ["Status", String(artifact.status ?? "unknown")],
            ["Changed files", changedFiles.join(", ") || "none"],
            ["Needs Planner", String(artifact.needs_planner_decision ?? false)]
          ]}
        />
        {unexpected.length > 0 && <InlineList title="Unexpected issues" values={unexpected} />}
      </div>
    );
  }
  if (artifactType === "test_result") {
    const evidence = stringList(artifact.evidence);
    const remaining = stringList(artifact.remaining_work);
    const issues = objectList(artifact.issues).map((issue) => String(issue.title ?? JSON.stringify(issue)));
    return (
      <div className="artifact-specific">
        <div className="muted">{String(artifact.summary ?? "")}</div>
        <KeyValueList
          items={[
            ["Round", String(artifact.round ?? "unknown")],
            ["Status", String(artifact.status ?? "unknown")],
            ["Issues", String(issues.length || artifact.issues || 0)],
            ["Confidence", String(artifact.confidence ?? "unknown")]
          ]}
        />
        {issues.length > 0 && <InlineList title="Issues" values={issues} />}
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
            ["Test", String(artifact.test_summary ?? "")],
            ["Decision", String(artifact.planner_decision_summary ?? artifact.decision_summary ?? "")]
          ]}
        />
        {refs.length > 0 && <InlineList title="Important refs" values={refs} />}
        {remaining.length > 0 && <InlineList title="Remaining work" values={remaining} />}
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

export async function hydrateBlobRefs(value: unknown, runId: string): Promise<unknown> {
  const object = objectValue(value);
  if (object?.blob_id && typeof object.blob_id === "string" && typeof object.size_chars === "number") {
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

export function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}
