import { useCallback, useState } from "react";

import { getAgentRoleCards, getCapabilities, getHealth } from "../api";
import type { CapabilitySpec, HealthStatus, RoleCardSpec } from "../types";

export function useRuntimeInfo(onStatus: (status: string) => void) {
  const [capabilities, setCapabilities] = useState<CapabilitySpec[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [roleCards, setRoleCards] = useState<RoleCardSpec[]>([]);

  const refreshRuntimeInfo = useCallback(() => {
    Promise.all([getHealth(), getCapabilities(), getAgentRoleCards()])
      .then(([nextHealth, nextCapabilities, nextRoleCards]) => {
        setHealth(nextHealth);
        setCapabilities(nextCapabilities);
        setRoleCards(nextRoleCards);
      })
      .catch((error) => onStatus(`Failed to load runtime info: ${error.message}`));
  }, [onStatus]);

  return {
    capabilities,
    health,
    roleCards,
    refreshRuntimeInfo
  };
}
