export const appSections = ["chat", "workflow", "extensions", "settings"] as const;

export type AppSection = (typeof appSections)[number];
const coreAppSections = appSections.filter((section) => section !== "extensions");

interface AppSidebarProps {
  activeSection: AppSection;
  status: string;
  onSectionChange: (section: AppSection) => void;
  showExtensions?: boolean;
}

const sectionLabels: Record<AppSection, string> = {
  chat: "Planner Chat",
  workflow: "Agent Workflow",
  extensions: "Plugins & Skills",
  settings: "Settings"
};

export function AppSidebar({
  activeSection,
  status,
  onSectionChange,
  showExtensions = false
}: AppSidebarProps) {
  const visibleSections: readonly AppSection[] = showExtensions ? appSections : coreAppSections;

  return (
    <aside className="app-sidebar">
      <div className="sidebar-brand">
        <div className="eyebrow">Planner-led local workflows</div>
        <h1>Coder</h1>
      </div>
      <nav className="side-nav" aria-label="Primary">
        {visibleSections.map((section) => (
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
