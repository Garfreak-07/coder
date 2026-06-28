from __future__ import annotations

from typing import Any, Protocol

from .runtime_context import HarnessRunRequest, HarnessRunResult


class HarnessProvider(Protocol):
    provider_id: str

    def is_available(self) -> bool:
        ...

    def run(self, request: HarnessRunRequest, *, emit: Any | None = None) -> HarnessRunResult:
        ...


class ProviderUnavailableError(RuntimeError):
    pass


__all__ = [
    "HarnessProvider",
    "ProviderUnavailableError",
]
