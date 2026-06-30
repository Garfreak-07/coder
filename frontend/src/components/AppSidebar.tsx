export const appSections = ["chat", "workflow", "extensions", "settings"] as const;

export type AppSection = (typeof appSections)[number];
const primaryAppSections = ["chat", "settings"] as const satisfies readonly AppSection[];

interface AppSidebarProps {
  activeSection: AppSection;
  status: string;
  onSectionChange: (section: AppSection) => void;
  showExtensions?: boolean;
}

const sectionLabels: Record<AppSection, string> = {
  chat: "Planner Chat",
  workflow: "Workflow editor",
  extensions: "Plugins & Skills",
  settings: "Settings"
};

export function AppSidebar({
  activeSection,
  status,
  onSectionChange,
  showExtensions = false
}: AppSidebarProps) {
  const advancedSections: readonly AppSection[] = showExtensions ? ["workflow", "extensions"] : ["workflow"];
  const advancedOpen = activeSection === "workflow" || activeSection === "extensions";

  return (
    <aside className="app-sidebar">
      <div className="sidebar-brand">
        <div className="eyebrow">Planner-led local workflows</div>
        <h1>Coder</h1>
      </div>
      <nav className="side-nav" aria-label="Primary">
        {primaryAppSections.map((section) => (
          <button
            className={activeSection === section ? "selected" : ""}
            key={section}
            onClick={() => onSectionChange(section)}
          >
            {sectionLabels[section]}
          </button>
        ))}
        <details className="advanced-nav" open={advancedOpen}>
          <summary>Advanced</summary>
          <div className="nav-group-label">Developer</div>
          {advancedSections.map((section) => (
            <button
              className={activeSection === section ? "selected" : ""}
              key={section}
              onClick={() => onSectionChange(section)}
            >
              {sectionLabels[section]}
            </button>
          ))}
        </details>
      </nav>
      <div className="sidebar-status">{status}</div>
    </aside>
  );
}
