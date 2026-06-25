from __future__ import annotations

from typing import Any

from .profiles import INTERNAL_FALLBACK_PROVIDER_ID
from .runtime_context import HarnessRunRequest, HarnessRunResult


class InternalFallbackProvider:
    """Compatibility provider used while AgentRun is migrated incrementally."""

    provider_id = INTERNAL_FALLBACK_PROVIDER_ID

    def is_available(self) -> bool:
        return True

    def run(self, request: HarnessRunRequest, *, emit: Any | None = None) -> HarnessRunResult:
        if emit is not None:
            emit(
                "harness_runtime.fallback.unconfigured",
                "InternalFallbackProvider was invoked without a legacy runtime adapter",
                mode=request.mode,
                profile_id=request.profile.id,
            )
        return HarnessRunResult(
            status="failed",
            error={
                "code": "fallback_provider_unconfigured",
                "message": "InternalFallbackProvider is not wired to a legacy runtime adapter for this request.",
            },
        )


__all__ = ["InternalFallbackProvider"]
