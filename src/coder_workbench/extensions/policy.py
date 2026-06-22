from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class ExtensionActionPolicy:
    operation_id: str
    risk_level: str
    permissions: list[str]
    requires_approval: bool
    known_operation: bool
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "risk_level": self.risk_level,
            "permissions": self.permissions,
            "requires_approval": self.requires_approval,
            "known_operation": self.known_operation,
            "reason": self.reason,
        }


def merge_extension_policy(
    *,
    operation_id: str,
    capability: Any | None,
    spec_risk_level: str,
    spec_requires_permission: bool,
    input_requires_permission: bool,
    input_requires_approval: bool,
) -> ExtensionActionPolicy:
    spec_risk = _normalize_risk(spec_risk_level)
    if capability is None:
        return ExtensionActionPolicy(
            operation_id=operation_id,
            risk_level=spec_risk,
            permissions=[],
            requires_approval=True,
            known_operation=False,
            reason="Unknown plugin operation requires explicit approval.",
        )

    capability_risk = _normalize_risk(getattr(capability, "risk_level", "low"))
    effective_risk = max(
        [spec_risk, capability_risk],
        key=lambda item: _RISK_ORDER.get(item, 0),
    )
    permissions = [str(item) for item in (getattr(capability, "permissions", ()) or ())]
    requires_approval = bool(
        getattr(capability, "requires_approval", False)
        or spec_requires_permission
        or input_requires_permission
        or input_requires_approval
        or effective_risk in {"medium", "high"}
    )
    return ExtensionActionPolicy(
        operation_id=operation_id,
        risk_level=effective_risk,
        permissions=permissions,
        requires_approval=requires_approval,
        known_operation=True,
        reason="Capability policy merged.",
    )


def _normalize_risk(value: Any) -> str:
    risk = str(value or "low").strip().lower()
    return risk if risk in _RISK_ORDER else "low"
