import type { PluginManifest, SkillSummary } from "../../types";

interface InstalledPluginsProps {
  plugins: PluginManifest[];
  skills: SkillSummary[];
  onSelectPlugin: (pluginId: string) => void;
}

export function InstalledPlugins({ plugins, skills, onSelectPlugin }: InstalledPluginsProps) {
  return (
    <section className="plugin-section">
      <div className="panel-title">Installed</div>
      <div className="plugin-card-grid">
        {plugins.map((plugin) => (
          <button className="plugin-card plugin-card-button" key={plugin.id} onClick={() => onSelectPlugin(plugin.id)}>
            <div>
              <strong>{plugin.name}</strong>
              <code>{plugin.enabled ? "enabled" : "disabled"}</code>
            </div>
            <span>{plugin.description}</span>
          </button>
        ))}
        {skills.map((skill) => (
          <article className="plugin-card" key={skill.id}>
            <div>
              <strong>{skill.name}</strong>
              <code>{skill.enabled ? "enabled" : "disabled"}</code>
            </div>
            <p>{skill.description}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
