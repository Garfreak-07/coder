import { useCallback, useState } from "react";

import { getCapabilities, getHealth, getLiveRuns, getRuns } from "../api";
import type { CapabilitySpec, HealthStatus, RunSummaryItem } from "../types";

export function useRuntimeInfo(onStatus: (status: string) => void) {
  const [capabilities, setCapabilities] = useState<CapabilitySpec[]>([]);
  const [runHistory, setRunHistory] = useState<RunSummaryItem[]>([]);
  const [liveRuns, setLiveRuns] = useState<RunSummaryItem[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);

  const refreshRuntimeInfo = useCallback(() => {
    Promise.all([getRuns(), getLiveRuns(), getHealth(), getCapabilities()])
      .then(([runs, live, nextHealth, nextCapabilities]) => {
        setRunHistory(runs);
        setLiveRuns(live);
        setHealth(nextHealth);
        setCapabilities(nextCapabilities);
      })
      .catch((error) => onStatus(`Failed to load runtime info: ${error.message}`));
  }, [onStatus]);

  return {
    capabilities,
    runHistory,
    liveRuns,
    health,
    refreshRuntimeInfo
  };
}
