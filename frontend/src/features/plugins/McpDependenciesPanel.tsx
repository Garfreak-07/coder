interface McpDependenciesPanelProps {
  dependencies: unknown[];
}

export function McpDependenciesPanel({ dependencies }: McpDependenciesPanelProps) {
  return (
    <section className="plugin-section">
      <div className="panel-title">MCP dependencies</div>
      {dependencies.length === 0 ? (
        <div className="muted">No MCP dependencies declared for the selected plugin.</div>
      ) : (
        <pre>{JSON.stringify(dependencies, null, 2)}</pre>
      )}
    </section>
  );
}
