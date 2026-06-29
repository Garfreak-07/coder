import type { ChangeSet } from "./changeSetTypes";

interface ReviewChangesCardProps {
  changeSets: ChangeSet[];
  diffByChangeSetId: Record<string, string>;
  loadingChangeSetId: string | null;
  onAccept: (changeSetId: string) => void;
  onLoadDiff: (changeSetId: string) => void;
  onUndo: (changeSetId: string) => void;
}

export function ReviewChangesCard({
  changeSets,
  diffByChangeSetId,
  loadingChangeSetId,
  onAccept,
  onLoadDiff,
  onUndo
}: ReviewChangesCardProps) {
  if (changeSets.length === 0) return null;
  return (
    <section className="review-changes-card" aria-label="Review changes">
      <div className="review-header">
        <div>
          <span>Review changes</span>
          <strong>{changeSets.length} change set{changeSets.length === 1 ? "" : "s"}</strong>
        </div>
      </div>
      {changeSets.map((changeSet) => {
        const diff = diffByChangeSetId[changeSet.change_set_id];
        const loading = loadingChangeSetId === changeSet.change_set_id;
        return (
          <article className="change-set-card" key={changeSet.change_set_id}>
            <div className="change-set-title">
              <strong>{changeSet.change_set_id}</strong>
              <code>{changeSet.status}</code>
            </div>
            <div className="timeline-meta">
              <span>{changeSet.repo_root}</span>
              {changeSet.reverse_patch_ref && <span>undo available</span>}
            </div>
            {changeSet.changed_files.length > 0 && (
              <div className="change-file-list">
                {changeSet.changed_files.map((file) => (
                  <span key={file.path}>
                    {file.path}
                    <small>{file.change_type}</small>
                  </span>
                ))}
              </div>
            )}
            {changeSet.command_checks.length > 0 && (
              <div className="change-check-list">
                {changeSet.command_checks.map((check) => (
                  <code key={check.command}>{check.command}</code>
                ))}
              </div>
            )}
            {diff && <pre className="review-diff">{diff}</pre>}
            <div className="review-actions">
              <button onClick={() => onLoadDiff(changeSet.change_set_id)} disabled={loading}>
                {loading ? "Loading diff..." : diff ? "Refresh diff" : "View diff"}
              </button>
              <button onClick={() => onAccept(changeSet.change_set_id)}>
                Accept
              </button>
              <button onClick={() => onUndo(changeSet.change_set_id)}>
                Undo
              </button>
            </div>
          </article>
        );
      })}
    </section>
  );
}
