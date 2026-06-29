import type { HookSummary } from "../../types";

interface HooksPanelProps {
  hooks: HookSummary[];
}

export function HooksPanel({ hooks }: HooksPanelProps) {
  return (
    <section className="plugin-section">
      <div className="panel-title">Hooks</div>
      <div className="plugin-marketplace-list">
        {hooks.map((hook) => (
          <div className="plugin-row" key={hook.id}>
            <strong>{hook.id}</strong>
            <span>{hook.description}</span>
            <code>{hook.enabled ? hook.trigger : "disabled"}</code>
          </div>
        ))}
      </div>
    </section>
  );
}
