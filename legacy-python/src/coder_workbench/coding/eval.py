from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import CodingEvaluationReportArtifact, CodingTaskSpec


def load_coding_task(path: str | Path) -> CodingTaskSpec:
    return CodingTaskSpec.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def evaluate_fake_coding_task(task: CodingTaskSpec | dict[str, Any]) -> CodingEvaluationReportArtifact:
    spec = CodingTaskSpec.model_validate(task)
    tests_pass = 1.0 if spec.acceptance.tests_pass else 0.0
    forbidden_change = 0.0 if spec.acceptance.no_forbidden_files_changed else 1.0
    task_pass = 1.0 if tests_pass and forbidden_change == 0.0 else 0.0
    return CodingEvaluationReportArtifact(
        task_id=spec.task_id,
        task_pass_rate=task_pass,
        patch_created_rate=1.0 if spec.expected_changed_files else 0.0,
        patch_apply_rate=1.0,
        tests_pass_rate=tests_pass,
        forbidden_change_rate=forbidden_change,
        planner_rounds=1,
        worker_interrupt_rate=0.0,
        human_prompt_rate=0.0,
        estimated_tokens=0,
        repair_count=0,
        details={
            "repo_fixture": spec.repo_fixture,
            "check_commands": spec.check_commands,
            "expected_changed_files": spec.expected_changed_files,
        },
    )


def build_run_coding_eval(data: dict[str, Any], events: list[Any] | None = None) -> dict[str, Any]:
    graph_run_cache = data.get("graph_run_cache") if isinstance(data, dict) else None
    if not isinstance(graph_run_cache, dict):
        return CodingEvaluationReportArtifact().model_dump(mode="json")

    execution_cache = graph_run_cache.get("execution_cache") if isinstance(graph_run_cache.get("execution_cache"), dict) else {}
    hidden_effects = graph_run_cache.get("hidden_effects") if isinstance(graph_run_cache.get("hidden_effects"), list) else []
    token_ledger = data.get("token_ledger") if isinstance(data.get("token_ledger"), list) else []
    rounds = data.get("rounds") if isinstance(data.get("rounds"), list) else []
    debug_findings = data.get("debug_findings") if isinstance(data.get("debug_findings"), list) else []

    total_items = max(1, len(execution_cache))
    patch_preview_effects = [
        effect
        for effect in hidden_effects
        if effect.get("effect_type") == "modify_files" and effect.get("status") == "patch_preview_created"
    ]
    sandbox_apply_effects = [effect for effect in hidden_effects if effect.get("effect_type") == "sandbox_apply"]
    patch_created = len(patch_preview_effects)
    check_effects = [effect for effect in hidden_effects if effect.get("effect_type") == "optional_check_command"]
    checks_passed = sum(1 for effect in check_effects if effect.get("status") == "completed" and effect.get("passed", True) is not False)
    failed_check_results = sum(
        1
        for effect in check_effects
        if effect.get("status") in {"failed", "check_requires_planner_confirmation"} or effect.get("passed") is False
    )
    sandbox_apply_passed = sum(
        1
        for effect in sandbox_apply_effects
        if effect.get("status") in {"applied", "ok"}
    )
    failed_sandbox_apply = sum(
        1
        for effect in sandbox_apply_effects
        if effect.get("status") not in {"applied", "ok"}
    )
    debug_finding_effects = [effect for effect in hidden_effects if effect.get("effect_type") == "debug_finding"]
    runtime_action_effects = [effect for effect in hidden_effects if effect.get("effect_type") == "runtime_action"]
    blocked_runtime_actions = sum(1 for effect in runtime_action_effects if effect.get("status") == "blocked")
    failed_runtime_actions = sum(1 for effect in runtime_action_effects if effect.get("status") == "failed")
    verification_statuses = [_verification_status(record) for record in execution_cache.values() if isinstance(record, dict)]
    verification_pass_count = sum(1 for status in verification_statuses if status in {"pass", "skipped"})
    interrupts = graph_run_cache.get("interrupts") if isinstance(graph_run_cache.get("interrupts"), list) else []
    human_prompts = [event for event in (events or []) if getattr(event, "type", "") == "planner.human_prompt"]
    estimated_tokens = 0
    for entry in token_ledger:
        if isinstance(entry, dict):
            estimated_tokens += int(entry.get("estimated_input_tokens") or 0)
            estimated_tokens += int(entry.get("estimated_output_tokens") or 0)
    repair_count = len([event for event in (events or []) if "repair" in getattr(event, "type", "")])

    effect_gate_passed = not any(
        [
            failed_check_results,
            failed_sandbox_apply,
            blocked_runtime_actions,
            failed_runtime_actions,
            debug_finding_effects,
        ]
    )
    debug_finding_count = max(len(debug_findings), len(debug_finding_effects))
    report = CodingEvaluationReportArtifact(
        task_pass_rate=1.0 if _run_succeeded(execution_cache) and effect_gate_passed else 0.0,
        patch_created_rate=patch_created / total_items,
        patch_apply_rate=(sandbox_apply_passed / len(sandbox_apply_effects)) if sandbox_apply_effects else (1.0 if patch_created else 0.0),
        tests_pass_rate=(verification_pass_count / len(verification_statuses)) if verification_statuses else (1.0 if not check_effects else checks_passed / max(1, len(check_effects))),
        forbidden_change_rate=0.0,
        planner_rounds=len(rounds) or int(graph_run_cache.get("round") or 0),
        worker_interrupt_rate=len(interrupts) / total_items,
        human_prompt_rate=len(human_prompts) / max(1, len(rounds) or 1),
        estimated_tokens=estimated_tokens,
        repair_count=repair_count,
        details={
            "patch_created": bool(patch_created),
            "sandbox_tests_passed": bool(check_effects and checks_passed == len(check_effects)),
            "sandbox_checks_passed": bool(check_effects and checks_passed == len(check_effects)),
            "debug_findings": debug_finding_count,
            "patch_preview_count": len(patch_preview_effects),
            "sandbox_apply_count": len(sandbox_apply_effects),
            "check_result_count": len(check_effects),
            "failed_check_results": failed_check_results,
            "debug_finding_count": debug_finding_count,
            "runtime_action_count": len(runtime_action_effects),
            "blocked_runtime_actions": blocked_runtime_actions,
            "failed_runtime_actions": failed_runtime_actions,
            "forbidden_change": False,
            "worker_interrupts": len(interrupts),
            "human_prompts": len(human_prompts),
        },
    )
    return report.model_dump(mode="json")


def _run_succeeded(execution_cache: dict[str, Any]) -> bool:
    if any(record.get("status") == "blocked" for record in execution_cache.values() if isinstance(record, dict)):
        return False
    if any(_verification_status(record) in {"fail", "blocked"} for record in execution_cache.values() if isinstance(record, dict)):
        return False
    return True


def _verification_status(record: dict[str, Any]) -> str:
    artifact = record.get("artifact_payload") if isinstance(record.get("artifact_payload"), dict) else {}
    verification = artifact.get("verification") if isinstance(artifact.get("verification"), dict) else {}
    return str(verification.get("status") or "")
