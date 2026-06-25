from __future__ import annotations

from typing import Any


def build_final_report(
    *,
    status: str,
    data: dict[str, Any],
    artifacts: dict[str, Any],
    events: list[Any],
    status_reason: str | None = None,
    status_code: str | None = None,
) -> dict[str, Any]:
    execution_results = _collect_execution_results(artifacts)
    if not execution_results:
        execution_results = _collect_execution_results_from_shared_state(data)
    report_status = _status_from_run(status, execution_results)
    evidence_refs = _collect_evidence_refs(execution_results, data)
    checks = _collect_checks(execution_results)
    blocked_by = _blocked_by(execution_results, status_reason if report_status == "blocked" else None)
    failed_by = _failed_by(execution_results, status_reason if report_status == "failed" else None)
    notes: list[str] = []
    warnings: list[str] = []
    if not evidence_refs:
        notes.append("No evidence refs were recorded for this run.")
    if status_code:
        notes.append(f"Run status code: {status_code}.")
    if status_reason and report_status not in {"blocked", "failed"}:
        notes.append(status_reason)

    return {
        "artifact_type": "final_report",
        "status": report_status,
        "summary": _summary_from_status(
            status=report_status,
            execution_results=execution_results,
            status_reason=status_reason,
        ),
        "commit": _collect_commit(data),
        "files": _collect_changed_files(execution_results),
        "checks": checks,
        "completed": _completed_items(execution_results),
        "blocked_by": blocked_by,
        "failed_by": failed_by,
        "warnings": warnings,
        "notes": notes,
        "next_steps": _next_steps_from_blockers(blocked_by, failed_by),
        "evidence_refs": evidence_refs,
    }


def _collect_execution_results(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    results = [
        artifact
        for artifact in artifacts.values()
        if isinstance(artifact, dict) and artifact.get("artifact_type") == "execution_result"
    ]
    return sorted(
        results,
        key=lambda item: (
            int(item.get("round") or 0),
            int(item.get("merge_index") or 0),
            str(item.get("work_item_id") or ""),
        ),
    )


def _collect_execution_results_from_shared_state(data: dict[str, Any]) -> list[dict[str, Any]]:
    state = data.get("shared_run_state")
    if not isinstance(state, dict):
        return []
    work_items = state.get("work_items")
    if not isinstance(work_items, dict):
        return []
    results: list[dict[str, Any]] = []
    for work_item_id, item in work_items.items():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status not in {"completed", "blocked"}:
            continue
        result_ref = str(item.get("execution_result_ref") or "")
        evidence_refs = [result_ref] if result_ref else []
        results.append(
            {
                "artifact_type": "execution_result",
                "round": state.get("control", {}).get("round", 0) if isinstance(state.get("control"), dict) else 0,
                "work_item_id": str(item.get("work_item_id") or work_item_id),
                "agent_id": str(item.get("agent_id") or ""),
                "status": status,
                "summary": str(item.get("summary") or ""),
                "blocker_reason": item.get("blocked_reason"),
                "evidence_refs": evidence_refs,
                "verification": {
                    "status": "blocked" if status == "blocked" else "skipped",
                    "checks_run": [],
                    "evidence_refs": evidence_refs,
                    "confidence": "low" if status == "blocked" else "medium",
                    "remaining_work": [str(item.get("blocked_reason"))] if item.get("blocked_reason") else [],
                },
            }
        )
    return results


def _collect_changed_files(execution_results: list[dict[str, Any]]) -> dict[str, list[str]]:
    created = _unique_strings(
        file_name
        for result in execution_results
        for file_name in _string_list(result.get("created_files"))
    )
    deleted = _unique_strings(
        file_name
        for result in execution_results
        for file_name in _string_list(result.get("deleted_files"))
    )
    modified = _unique_strings(
        file_name
        for result in execution_results
        for file_name in _string_list(result.get("changed_files"))
        if file_name not in created and file_name not in deleted
    )
    return {
        "created": created,
        "modified": modified,
        "deleted": deleted,
    }


def _collect_checks(execution_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for result in execution_results:
        verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
        for check in verification.get("checks_run") or []:
            if not isinstance(check, dict):
                continue
            checks.append(
                {
                    "command": check.get("command") if isinstance(check.get("command"), str) else None,
                    "status": _check_status(check.get("status")),
                    "summary": str(check.get("summary") or ""),
                    "output_ref": check.get("output_ref") if isinstance(check.get("output_ref"), str) else None,
                    "evidence_refs": _string_list(check.get("evidence_refs")),
                }
            )
    return checks


def _collect_evidence_refs(execution_results: list[dict[str, Any]], data: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for result in execution_results:
        refs.extend(_string_list(result.get("evidence_refs")))
        refs.extend(_string_list(result.get("patch_refs")))
        verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
        refs.extend(_string_list(verification.get("evidence_refs")))
        for check in verification.get("checks_run") or []:
            if isinstance(check, dict):
                refs.extend(_string_list(check.get("evidence_refs")))
                output_ref = check.get("output_ref")
                if isinstance(output_ref, str) and output_ref:
                    refs.append(output_ref)
    persisted = data.get("persisted_blob_refs")
    if isinstance(persisted, list):
        for record in persisted:
            if isinstance(record, dict) and isinstance(record.get("blob_id"), str):
                refs.append(record["blob_id"])
    return _unique_strings(refs)


def _status_from_run(status: str, execution_results: list[dict[str, Any]]) -> str:
    if status in {"completed", "blocked", "failed", "cancelled"}:
        return status
    if any(result.get("status") == "blocked" for result in execution_results):
        return "blocked"
    return "failed"


def _summary_from_status(
    *,
    status: str,
    execution_results: list[dict[str, Any]],
    status_reason: str | None,
) -> str:
    if status_reason and status in {"blocked", "failed", "cancelled"}:
        return status_reason
    if status == "completed":
        completed = _completed_items(execution_results)
        if completed:
            return "Completed: " + "; ".join(completed[:3])
        return "Run completed."
    if status == "blocked":
        return "Run blocked before all work could complete."
    if status == "cancelled":
        return "Run cancelled."
    return "Run failed."


def _next_steps_from_blockers(blocked_by: list[str], failed_by: list[str]) -> list[str]:
    if blocked_by:
        return ["Resolve the listed blocker and rerun or continue the Planner-led task."]
    if failed_by:
        return ["Inspect the failure reason and rerun the relevant verification."]
    return []


def _collect_commit(data: dict[str, Any]) -> dict[str, str | None] | None:
    commit = data.get("commit")
    if isinstance(commit, dict):
        sha = commit.get("sha")
        message = commit.get("message")
        if isinstance(sha, str) or isinstance(message, str):
            return {
                "sha": sha if isinstance(sha, str) else None,
                "message": message if isinstance(message, str) else None,
            }
    return None


def _completed_items(execution_results: list[dict[str, Any]]) -> list[str]:
    completed: list[str] = []
    for result in execution_results:
        if result.get("status") != "completed":
            continue
        summary = str(result.get("summary") or "").strip()
        work_item_id = str(result.get("work_item_id") or "").strip()
        if summary and work_item_id:
            completed.append(f"{work_item_id}: {summary}")
        elif summary:
            completed.append(summary)
        elif work_item_id:
            completed.append(work_item_id)
    return completed


def _blocked_by(execution_results: list[dict[str, Any]], status_reason: str | None) -> list[str]:
    blockers = [
        _blocker_summary(result)
        for result in execution_results
        if result.get("status") == "blocked"
    ]
    if status_reason:
        blockers.append(status_reason)
    return _unique_strings(blocker for blocker in blockers if blocker)


def _failed_by(execution_results: list[dict[str, Any]], status_reason: str | None) -> list[str]:
    failures: list[str] = []
    for result in execution_results:
        verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
        if verification.get("status") == "fail":
            failures.append(_blocker_summary(result) or str(result.get("summary") or "Verification failed."))
    if status_reason:
        failures.append(status_reason)
    return _unique_strings(failure for failure in failures if failure)


def _blocker_summary(result: dict[str, Any]) -> str:
    blocker_type = str(result.get("blocker_type") or "").strip()
    reason = str(result.get("blocker_reason") or result.get("summary") or "").strip()
    if blocker_type and reason:
        return f"{blocker_type}: {reason}"
    return blocker_type or reason


def _check_status(value: Any) -> str:
    status = str(value or "").lower()
    if status in {"pass", "passed"}:
        return "passed"
    if status in {"fail", "failed", "error"}:
        return "failed"
    if status == "blocked":
        return "blocked"
    if status == "skipped":
        return "skipped"
    return "unknown"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _unique_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
