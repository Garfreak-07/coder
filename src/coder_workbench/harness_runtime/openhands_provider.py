from __future__ import annotations

import importlib
import importlib.util
from typing import Any

from .native_events import NativeRuntimeEvent
from .profiles import OPENHANDS_PROVIDER_ID
from .runtime_context import HarnessRunRequest, HarnessRunResult
from .store import NativeRuntimeStore


class OpenHandsRuntimeProvider:
    """Feature-flagged OpenHands SDK provider boundary.

    This module is the only place that may import OpenHands SDK modules. The
    first implementation is deliberately conservative: it detects SDK presence,
    records native-provider lifecycle facts, and fails closed until the exact
    locally installed SDK invocation API is verified.
    """

    provider_id = OPENHANDS_PROVIDER_ID

    def __init__(
        self,
        *,
        runtime_module_names: tuple[str, ...] | None = None,
        native_store: NativeRuntimeStore | None = None,
    ) -> None:
        self.runtime_module_names = runtime_module_names or ("openhands", "openhands.sdk")
        self.native_store = native_store or NativeRuntimeStore()

    def is_available(self) -> bool:
        return self._load_sdk_module() is not None

    def run(self, request: HarnessRunRequest, *, emit: Any | None = None) -> HarnessRunResult:
        sdk_module = self._load_sdk_module()
        if sdk_module is None:
            return self._failed(
                request,
                emit=emit,
                code="openhands_sdk_unavailable",
                message="OpenHands SDK is not importable in this environment.",
            )

        self._emit(
            emit,
            "harness_runtime.openhands.started",
            "OpenHands runtime provider selected",
            mode=request.mode,
            profile_id=request.profile.id,
            sdk_module=getattr(sdk_module, "__name__", "unknown"),
        )
        event = self._record_event(
            request,
            native_type="provider.selected",
            status="blocked",
            summary="OpenHands SDK detected; invocation adapter is not implemented yet.",
            payload={
                "sdk_module": getattr(sdk_module, "__name__", "unknown"),
                "mode": request.mode,
                "profile_id": request.profile.id,
            },
        )
        self._emit(
            emit,
            "harness_runtime.openhands.failed",
            "OpenHands runtime invocation adapter is not implemented",
            mode=request.mode,
            profile_id=request.profile.id,
            native_event_ref=event.event_id,
        )
        return HarnessRunResult(
            status="failed",
            native_event_refs=[event.event_id],
            error={
                "code": "openhands_adapter_unimplemented",
                "message": "OpenHands SDK was detected, but the local invocation API has not been verified.",
            },
        )

    def _load_sdk_module(self) -> Any | None:
        for module_name in self.runtime_module_names:
            if importlib.util.find_spec(module_name) is None:
                continue
            return importlib.import_module(module_name)
        return None

    def _failed(
        self,
        request: HarnessRunRequest,
        *,
        emit: Any | None,
        code: str,
        message: str,
    ) -> HarnessRunResult:
        event = self._record_event(
            request,
            native_type="provider.error",
            status="failed",
            summary=message,
            payload={"code": code, "message": message},
        )
        self._emit(
            emit,
            "harness_runtime.openhands.failed",
            message,
            mode=request.mode,
            profile_id=request.profile.id,
            native_event_ref=event.event_id,
        )
        return HarnessRunResult(
            status="failed",
            native_event_refs=[event.event_id],
            error={"code": code, "message": message},
        )

    def _record_event(
        self,
        request: HarnessRunRequest,
        *,
        native_type: str,
        status: str,
        summary: str,
        payload: dict[str, Any],
    ) -> NativeRuntimeEvent:
        return self.native_store.append_event(
            run_id=request.context.run_id,
            round=request.context.round,
            work_item_id=str(request.input_artifacts.get("work_item_id") or "") or None,
            agent_id=request.context.agent_id,
            provider_id=self.provider_id,
            harness_id=request.profile.harness_id,
            mode=request.mode,
            native_type=native_type,
            status=status,
            summary=summary,
            payload=payload,
        )

    def _emit(self, emit: Any | None, event_type: str, message: str, **payload: Any) -> None:
        if emit is None:
            return
        emit(event_type, message, **payload)


__all__ = ["OpenHandsRuntimeProvider"]
