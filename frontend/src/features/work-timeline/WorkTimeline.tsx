import type { TimelineItem } from "./timelineTypes";
import {
  commandLine,
  formatDuration,
  timelineItemStatus,
  timelineItemTitle,
  timelineItemTone
} from "./timelineAdapter";

interface WorkTimelineProps {
  runId: string | null;
  items: TimelineItem[];
}

export function WorkTimeline({ runId, items }: WorkTimelineProps) {
  if (!runId && items.length === 0) return null;
  return (
    <section className="work-timeline" aria-label="Work timeline">
      <div className="timeline-header">
        <div>
          <span>Work timeline</span>
          <p>{items.length > 0 ? `${items.length} public step${items.length === 1 ? "" : "s"}` : "Waiting for executor events"}</p>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="timeline-empty">Work has started. Timeline events will appear here.</div>
      ) : (
        <ol className="timeline-list">
          {items.map((item) => (
            <li
              className={`timeline-item timeline-${item.type} timeline-tone-${timelineItemTone(item)}`}
              key={item.id}
            >
              <div className="timeline-marker" />
              <div className="timeline-body">
                <div className="timeline-title-row">
                  <strong>{timelineItemTitle(item)}</strong>
                  <span>{timelineItemStatus(item)}</span>
                </div>
                <TimelineItemBody item={item} />
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function TimelineItemBody({ item }: { item: TimelineItem }) {
  switch (item.type) {
    case "planner_message":
    case "user_message":
      return <p>{item.content}</p>;
    case "reasoning_summary":
      return (
        <ul>
          {item.summary_text.map((summary, index) => (
            <li key={`${item.id}-${index}`}>{summary}</li>
          ))}
        </ul>
      );
    case "plan_update":
      return <p>{item.summary}</p>;
    case "executor_step":
      return item.summary ? <p>{item.summary}</p> : null;
    case "tool_call":
      return (
        <>
          {item.summary && <p>{item.summary}</p>}
        </>
      );
    case "command_execution":
      return <CommandExecutionBody item={item} />;
    case "file_change":
      return (
        <>
          <div className="timeline-meta">
            <span>{item.path}</span>
            <span>{item.change_type}</span>
          </div>
        </>
      );
    case "approval":
      return (
        <>
          <p>{item.summary}</p>
          <div className="timeline-meta">
            <span>{item.risk_level}</span>
            <span>{item.action_type}</span>
          </div>
        </>
      );
    case "verification":
      return <p>{item.summary}</p>;
    case "final_summary":
      return (
        <div className="final-summary-card">
          <p>{item.summary}</p>
          {item.changed_files.length > 0 && (
            <InlineList title="Files" values={item.changed_files} />
          )}
          {item.checks.length > 0 && <InlineList title="Checks" values={item.checks} />}
          {item.blockers.length > 0 && <InlineList title="Remaining risks" values={item.blockers} />}
          {item.next_steps.length > 0 && <InlineList title="Next steps" values={item.next_steps} />}
          <div className="timeline-meta">
            <span>{item.evidence_refs.length} evidence refs</span>
          </div>
        </div>
      );
    default:
      return null;
  }
}

function CommandExecutionBody({ item }: { item: Extract<TimelineItem, { type: "command_execution" }> }) {
  const duration = formatDuration(item.duration_ms);
  const hasOutput = Boolean(item.stdout_preview || item.stderr_preview);

  return (
    <>
      <pre className="timeline-command">{commandLine(item.command)}</pre>
      <div className="timeline-meta">
        <span>cwd {item.cwd}</span>
        {typeof item.exit_code === "number" && <span>exit {item.exit_code}</span>}
        {duration && <span>{duration}</span>}
      </div>
      {hasOutput && (
        <details className="timeline-command-output">
          <summary>Command output</summary>
          {item.stdout_preview && <pre>{item.stdout_preview}</pre>}
          {item.stderr_preview && <pre className="timeline-stderr">{item.stderr_preview}</pre>}
        </details>
      )}
    </>
  );
}

function InlineList({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="timeline-inline-list">
      <span>{title}</span>
      <div>
        {values.slice(0, 6).map((value) => (
          <code key={value}>{value}</code>
        ))}
        {values.length > 6 && <code>+{values.length - 6} more</code>}
      </div>
    </div>
  );
}
