export const appSections = ["chat", "workflow", "extensions", "runs", "settings"] as const;

export type AppSection = (typeof appSections)[number];

interface AppSidebarProps {
  activeSection: AppSection;
  status: string;
  onSectionChange: (section: AppSection) => void;
}

const sectionLabels: Record<AppSection, string> = {
  chat: "Planner Chat",
  workflow: "Agent Workflow",
  extensions: "Extensions",
  runs: "Runs",
  settings: "Settings"
};

export function AppSidebar({ activeSection, status, onSectionChange }: AppSidebarProps) {
  return (
    <aside className="app-sidebar">
      <div className="sidebar-brand">
        <div className="eyebrow">Planner-led local workflows</div>
        <h1>Coder</h1>
      </div>
      <nav className="side-nav" aria-label="Primary">
        {appSections.map((section) => (
          <button
            className={activeSection === section ? "selected" : ""}
            key={section}
            onClick={() => onSectionChange(section)}
          >
            {sectionLabels[section]}
          </button>
        ))}
      </nav>
      <div className="sidebar-status">{status}</div>
    </aside>
  );
}
