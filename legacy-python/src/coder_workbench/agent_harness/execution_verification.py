from __future__ import annotations

import hashlib
from typing import Any

from coder_workbench.core.planner_artifacts import ExecutionVerification


def ensure_execution_verification(artifact: dict[str, Any]) -> dict[str, Any]:
    payload = dict(artifact)
    verification = payload.get("verification")
    if isinstance(verification, dict):
        payload["verification"] = ExecutionVerification.model_validate(verification).model_dump(mode="json")
        return ensure_blocked_contract(payload)
    payload["verification"] = infer_execution_verification(payload)
    return ensure_blocked_contract(payload)


def ensure_blocked_contract(artifact: dict[str, Any]) -> dict[str, Any]:
    payload = dict(artifact)
    if payload.get("status") != "blocked":
        return payload
    blocker_type = _normalized_blocker_type(str(payload.get("blocker_type") or "unknown_error"))
    summary = str(payload.get("summary") or "Execution was blocked.")
    remaining = _remaining_work(payload)
    evidence_refs = _evidence_refs(payload)
    affected_files = _affected_files(payload)
    attempted_actions = [str(item) for item in payload.get("attempted_actions") or [] if str(item).strip()]
    payload["blocker_type"] = blocker_type
    payload.setdefault("executor_recovery_exhausted", True)
    payload.setdefault("blocker_reason", summary)
    payload.setdefault("blocker_fingerprint", _blocker_fingerprint(blocker_type, summary, affected_files))
    payload.setdefault(
        "recovery_attempts",
        [
            {"action": action, "result": "attempted"}
            for action in attempted_actions
        ],
    )
    payload.setdefault(
        "planner_recommendation",
        "replan_once" if payload.get("continue_without_human_possible") is True else "finish",
    )
    if payload.get("planner_recommendation") == "replan_once":
        payload.setdefault("replan_goal", summary)
    payload.setdefault("affected_files", affected_files)
    payload.setdefault("constraint_boundary", _constraint_boundary(blocker_type))
    if not remaining and not affected_files and not evidence_refs:
        remaining = [summary]
        payload["remaining_work"] = remaining
        verification = dict(payload.get("verification") or {})
        verification["remaining_work"] = remaining
        payload["verification"] = verification
    return payload


def infer_execution_verification(artifact: dict[str, Any]) -> dict[str, Any]:
    status = str(artifact.get("status") or "")
    evidence_refs = _evidence_refs(artifact)
    if status == "blocked":
        summary = str(artifact.get("summary") or "Execution was blocked.")
        return {
            "status": "blocked",
            "checks_run": [],
            "evidence_refs": evidence_refs,
            "confidence": "low",
            "remaining_work": _remaining_work(artifact) or [summary],
            "no_check_rationale": None,
            "repair_attempted": False,
            "repair_summary": None,
        }

    checks = _checks_from_requested_actions(artifact)
    if checks:
        verification_status = "fail" if any(check.get("status") == "fail" for check in checks) else "blocked" if any(check.get("status") == "blocked" for check in checks) else "pass"
        return {
            "status": verification_status,
            "checks_run": checks,
            "evidence_refs": evidence_refs,
            "confidence": "medium",
            "remaining_work": _remaining_work(artifact) if verification_status != "pass" else [],
            "no_check_rationale": None,
            "repair_attempted": False,
            "repair_summary": None,
        }

    if _has_static_completion_evidence(artifact):
        return {
            "status": "pass",
            "checks_run": [
                {
                    "check_id": "static-evidence",
                    "kind": "static",
                    "command": None,
                    "status": "pass",
                    "summary": "Execution result includes completion evidence.",
                    "output_ref": None,
                    "evidence_refs": evidence_refs,
                }
            ],
            "evidence_refs": evidence_refs,
            "confidence": "medium",
            "remaining_work": [],
            "no_check_rationale": None,
            "repair_attempted": False,
            "repair_summary": None,
        }

    return {
        "status": "skipped",
        "checks_run": [
            {
                "check_id": "no-executable-check",
                "kind": "skipped",
                "command": None,
                "status": "skipped",
                "summary": "No executable check was applicable to this WorkItem.",
                "output_ref": None,
                "evidence_refs": evidence_refs,
            }
        ],
        "evidence_refs": evidence_refs,
        "confidence": "low",
        "remaining_work": [],
        "no_check_rationale": "No executable check was applicable to this WorkItem.",
        "repair_attempted": False,
        "repair_summary": None,
    }


def verification_failed(artifact: dict[str, Any]) -> bool:
    verification = artifact.get("verification") if isinstance(artifact.get("verification"), dict) else {}
    return verification.get("status") in {"fail", "blocked"} and artifact.get("status") != "blocked"


def blocked_from_verification_failure(artifact: dict[str, Any], *, repair_attempted: bool, repair_summary: str | None = None) -> dict[str, Any]:
    verification = dict(artifact.get("verification") or {})
    remaining = verification.get("remaining_work") if isinstance(verification.get("remaining_work"), list) else []
    summary = str(artifact.get("summary") or "Execution verification failed.")
    verification.update(
        {
            "status": verification.get("status") if verification.get("status") in {"fail", "blocked"} else "fail",
            "repair_attempted": repair_attempted,
            "repair_summary": repair_summary,
            "remaining_work": remaining or [summary],
        }
    )
    blocked = dict(artifact)
    blocked.update(
        {
            "status": "blocked",
            "summary": summary,
            "unexpected_issues": list(blocked.get("unexpected_issues") or []) + ["test_failed"],
            "remaining_work": list(blocked.get("remaining_work") or []) + (remaining or [summary]),
            "needs_planner_decision": True,
            "blocker_type": "test_failed",
            "continue_without_human_possible": True,
            "verification": verification,
        }
    )
    return ensure_blocked_contract(blocked)


def _checks_from_requested_actions(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for index, action in enumerate(artifact.get("requested_actions") or [], start=1):
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("action_type") or action.get("type") or "")
        if action_type not in {"run_command_sandbox", "optional_check_command", "check_command"}:
            continue
        status = str(action.get("status") or "")
        if status in {"ok", "pass", "passed", "completed"}:
            check_status = "pass"
        elif status in {"blocked", "check_requires_planner_confirmation"}:
            check_status = "blocked"
        elif status in {"failed", "fail", "error"}:
            check_status = "fail"
        else:
            check_status = "skipped"
        checks.append(
            {
                "check_id": str(action.get("action_id") or f"check-{index}"),
                "kind": "command",
                "command": str(action.get("command") or ""),
                "status": check_status,
                "summary": str(action.get("summary") or action.get("reason") or ""),
                "output_ref": action.get("output_ref"),
                "evidence_refs": [str(action.get("output_ref"))] if action.get("output_ref") else [],
            }
        )
    return checks


def _has_static_completion_evidence(artifact: dict[str, Any]) -> bool:
    return any(
        artifact.get(key)
        for key in (
            "changed_files",
            "created_files",
            "deleted_files",
            "patch_refs",
            "outputs",
            "evidence_refs",
            "no_op_rationale",
        )
    )


def _evidence_refs(artifact: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("patch_refs", "outputs", "evidence_refs"):
        value = artifact.get(key)
        if isinstance(value, list):
            refs.extend(str(item) for item in value if str(item).strip())
    return refs


def _remaining_work(artifact: dict[str, Any]) -> list[str]:
    remaining = artifact.get("remaining_work")
    if isinstance(remaining, list):
        return [str(item) for item in remaining if str(item).strip()]
    issues = artifact.get("unexpected_issues")
    if isinstance(issues, list):
        return [str(item) for item in issues if str(item).strip()]
    return []


def _affected_files(artifact: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("affected_files", "changed_files", "created_files", "deleted_files"):
        value = artifact.get(key)
        if isinstance(value, list):
            refs.extend(str(item) for item in value if str(item).strip())
    return _unique(refs)


def _constraint_boundary(blocker_type: str) -> dict[str, bool]:
    return {
        "within_scope": blocker_type not in {"scope_violation", "risk_path_blocked"},
        "requires_secret": blocker_type == "missing_secret",
        "requires_network": blocker_type == "network_required",
        "requires_external_account": blocker_type == "external_account_required",
        "requires_destructive_action": blocker_type == "risk_path_blocked",
        "requires_out_of_scope_write": blocker_type == "scope_violation",
    }


def _blocker_fingerprint(blocker_type: str, reason: str, affected_files: list[str]) -> str:
    payload = "|".join([blocker_type, reason, *affected_files])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _normalized_blocker_type(value: str) -> str:
    return {
        "technical_blocker": "unknown_error",
        "verification_failed": "test_failed",
        "permission_blocked": "permission_boundary",
        "dependency_missing": "missing_dependency",
        "tool_error": "tool_unavailable",
        "out_of_contract": "scope_violation",
        "scope_boundary": "scope_violation",
        "risk_boundary": "risk_path_blocked",
        "unsafe_action": "risk_path_blocked",
        "patch_rejected": "risk_path_blocked",
        "transient_error_exhausted": "unknown_error",
        "ambiguity": "context_missing",
        "plan_conflict": "unknown_error",
    }.get(value, value)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
