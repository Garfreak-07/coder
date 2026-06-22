export const enUS = {
  app: {
    defaultStatus: "Ready"
  },
  runtime: {
    title: "Runtime",
    refresh: "Refresh Runtime",
    unknown: "Unknown",
    tools: (count: number) => `${count} tools`,
    liveRuns: (count: number) => `${count} live runs`,
    storedRuns: (count: number) => `${count} stored runs`,
    noLiveRuns: "No live runs.",
    storedHistory: "Stored History",
    noStoredRuns: "No stored runs."
  },
  events: {
    title: "Run Events",
    empty: "No events yet."
  }
};
