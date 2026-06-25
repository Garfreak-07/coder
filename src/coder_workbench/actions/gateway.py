from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from coder_workbench.actions.result_budget import ResultBudget, apply_result_budget
from coder_workbench.actions.schema import ACTION_TYPES, ActionResult, ActionSpec
from coder_workbench.actions.tool_execution import ToolExecutionResult, ToolExecutionService, ToolExecutionSpec
from coder_workbench.budget import BudgetBroker, BudgetLimit
from coder_workbench.context.budget import ContextBudget, context_compaction_enabled
from coder_workbench.core.artifacts import ArtifactValidationError, validate_artifact
from coder_workbench.coding import build_repo_intelligence
from coder_workbench.coding.command_service import CommandService
from coder_workbench.coding.patch_service import PatchService
from coder_workbench.extensions import ExtensionRuntime
from coder_workbench.extensions.policy import merge_extension_policy
from coder_workbench.skills import SkillIndex, estimate_tokens
from coder_workbench.tools.filesystem import DEFAULT_IGNORE_DIRS, TEXT_EXTENSIONS, resolve_scoped_path


PatchServiceFactory = Callable[[str | Path, list[str], dict[str, Any]], PatchService]
CommandServiceFactory = Callable[[str | Path, list[str], dict[str, Any]], CommandService]
ExtensionRuntimeFactory = Callable[[], ExtensionRuntime]


TOOL_EXECUTION_ACTION_TYPES = {
    "call_plugin",
    "call_mcp",
    "repo_index",
    "read_file",
    "search_files",
    "inspect_git_diff",
    "propose_patch",
    "apply_patch_sandbox",
    "run_command_sandbox",
    "run_command",
    "read_tool_output",
}


@dataclass
class RunContext:
    run_id: str
    repo_root: str | Path
    sandbox_root: str | Path | None = None
    scopes: list[str] | None = None
    data: dict[str, Any] | None = None
    cache: Any | None = None
    item: Any | None = None
    planner_order_ref: str | None = None
    upstream_refs: list[str] | None = None
    user_request: str = ""
    role: str = ""
    skill_index: SkillIndex | None = None
    skill_store_root: Path | None = None
    repo_intelligence: dict[str, Any] | None = None
    artifact_type: str = "execution_result"
    emit: Any | None = None
    model: Any | None = None

    @property
    def mutable_data(self) -> dict[str, Any]:
        if self.data is None:
            self.data = {}
        return self.data

    @property
    def active_scopes(self) -> list[str]:
        return list(self.scopes or [])


class ActionGateway:
    """Single entry point for low-level runtime actions."""

    def __init__(
        self,
        *,
        budget_broker: BudgetBroker | None = None,
        context_service: Any | None = None,
        repair_service: Any | None = None,
        patch_service_factory: PatchServiceFactory | None = None,
        command_service_factory: CommandServiceFactory | None = None,
        extension_runtime_factory: ExtensionRuntimeFactory | None = None,
        tool_execution_service: ToolExecutionService | None = None,
        result_budget: ResultBudget | None = None,
        enable_tool_execution_service: bool | None = None,
    ) -> None:
        self.budget_broker = budget_broker or BudgetBroker(BudgetLimit())
        if context_service is None:
            from coder_workbench.context import ContextService

            context_service = ContextService()
        self.context_service = context_service
        if repair_service is None:
            from coder_workbench.agent_harness.repair import ArtifactRepairService

            repair_service = ArtifactRepairService()
        self.repair_service = repair_service
        self.patch_service_factory = patch_service_factory or (
            lambda repo_root, scopes, data: PatchService(repo_root, scopes=scopes, data=data)
        )
        self.command_service_factory = command_service_factory or (
            lambda repo_root, scopes, data: CommandService(repo_root, scopes=scopes, data=data)
        )
        self.extension_runtime_factory = extension_runtime_factory or ExtensionRuntime
        self.tool_execution_service = tool_execution_service or ToolExecutionService()
        self.result_budget = result_budget or ResultBudget()
        self.enable_tool_execution_service = (
            _feature_enabled("CODER_ENABLE_TOOL_EXECUTION_SERVICE")
            if enable_tool_execution_service is None
            else bool(enable_tool_execution_service)
        )

    def run(self, spec: ActionSpec, *, run_context: RunContext) -> ActionResult:
        closed_action_types = (
            "build_context",
            "call_plugin",
            "call_mcp",
            "repo_index",
            "read_file",
            "search_files",
            "inspect_git_diff",
            "propose_patch",
            "apply_patch_sandbox",
            "run_command_sandbox",
            "run_command",
            "read_tool_output",
            "return_execution_result",
            "validate_artifact",
            "repair_artifact",
        )
        _ = closed_action_types
        if spec.action_type not in ACTION_TYPES:
            return ActionResult(
                status="failed",
                summary=f"Unknown action_type: {spec.action_type}",
                error_code="unknown_action_type",
            )
        try:
            if self.enable_tool_execution_service and spec.action_type in TOOL_EXECUTION_ACTION_TYPES:
                return self._run_with_tool_execution_service(spec, run_context)
            return self._run_direct(spec, run_context)
        except Exception as exc:  # pragma: no cover - defensive gateway boundary
            return ActionResult(status="failed", summary=str(exc), error_code="action_gateway_exception")

    def _run_direct(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        if spec.action_type == "build_context":
            return self._build_context(spec, run_context)
        if spec.action_type == "read_file":
            return self._read_file(spec, run_context)
        if spec.action_type == "search_files":
            return self._search_files(spec, run_context)
        if spec.action_type == "inspect_git_diff":
            return self._inspect_git_diff(spec, run_context)
        if spec.action_type == "read_tool_output":
            return self._read_tool_output(spec, run_context)
        if spec.action_type == "return_execution_result":
            return ActionResult(
                status="failed",
                summary="return_execution_result is handled by the harness loop.",
                error_code="loop_control_action",
            )
        if spec.action_type == "propose_patch":
            return self._propose_patch(spec, run_context)
        if spec.action_type == "apply_patch_sandbox":
            return self._apply_patch_sandbox(spec, run_context)
        if spec.action_type in {"run_command", "run_command_sandbox"}:
            return self._run_command(spec, run_context)
        if spec.action_type == "repo_index":
            return self._repo_index(spec, run_context)
        if spec.action_type == "call_plugin":
            return self._call_plugin(spec, run_context)
        if spec.action_type == "call_mcp":
            return self._call_mcp(spec, run_context)
        if spec.action_type == "validate_artifact":
            return self._validate_artifact(spec)
        if spec.action_type == "repair_artifact":
            return self._repair_artifact(spec, run_context)
        return ActionResult(
            status="failed",
            summary=f"Action type {spec.action_type} is not implemented yet.",
            error_code="action_not_implemented",
        )

    def _run_with_tool_execution_service(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        tool_spec = _tool_execution_spec(spec, run_context)

        def handler(_: ToolExecutionSpec, __: RunContext) -> ActionResult:
            return self._run_direct(spec, run_context)

        result = self.tool_execution_service.run_one(tool_spec, run_context, handler=handler)
        payload = dict(result.payload)
        if payload:
            payload, externalized_refs = apply_result_budget(
                payload,
                data=run_context.mutable_data,
                run_id=run_context.run_id,
                action_id=spec.action_id,
                action_type=spec.action_type,
                budget=self.result_budget,
            )
            if externalized_refs:
                payload.setdefault("result_budget", {})["externalized_refs"] = externalized_refs
        return _action_result_from_tool_execution(result, payload)

    def _apply_result_budget(
        self,
        spec: ActionSpec,
        run_context: RunContext,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        compacted, externalized_refs = apply_result_budget(
            payload,
            data=run_context.mutable_data,
            run_id=run_context.run_id,
            action_id=spec.action_id,
            action_type=spec.action_type,
            budget=self.result_budget,
        )
        if externalized_refs:
            compacted.setdefault("result_budget", {})["externalized_refs"] = externalized_refs
        return compacted, externalized_refs

    def _build_context(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        skill_index = _input_or_context(spec, run_context, "skill_index")
        if skill_index is None:
            skill_index = SkillIndex()
        estimated = spec.estimated_tokens or _estimate_context_tokens(spec, run_context, skill_index)
        reservation = self.budget_broker.reserve_context(
            run_id=run_context.run_id,
            agent_id=_agent_id(run_context),
            estimated_tokens=estimated,
            action_type=spec.action_type,
        )
        budget_compressed = False
        if not reservation.approved and reservation.reason == "context_budget_exceeded" and skill_index.enabled():
            skill_index = SkillIndex(skills=[])
            estimated = _estimate_context_tokens(spec, run_context, skill_index)
            reservation = self.budget_broker.reserve_context(
                run_id=run_context.run_id,
                agent_id=_agent_id(run_context),
                estimated_tokens=estimated,
                action_type=spec.action_type,
            )
            budget_compressed = True
        if not reservation.approved and reservation.reason == "context_budget_exceeded" and context_compaction_enabled(run_context.data):
            estimated = min(estimated, self.budget_broker.limit.max_context_tokens_per_call)
            reservation = self.budget_broker.reserve_context(
                run_id=run_context.run_id,
                agent_id=_agent_id(run_context),
                estimated_tokens=estimated,
                action_type=spec.action_type,
            )
            budget_compressed = True
        if not reservation.approved:
            return ActionResult(
                status="blocked",
                summary="BudgetBroker denied context construction.",
                error_code=reservation.reason,
                payload={"reservation": reservation.model_dump(mode="json")},
            )

        context = self.context_service.build_for_work_item(
            cache=_required(_input_or_context(spec, run_context, "cache"), "cache"),
            item=_required(_input_or_context(spec, run_context, "item"), "item"),
            planner_order_ref=_required(_input_or_context(spec, run_context, "planner_order_ref"), "planner_order_ref"),
            upstream_refs=list(_input_or_context(spec, run_context, "upstream_refs") or []),
            user_request=str(_input_or_context(spec, run_context, "user_request") or ""),
            role=str(_input_or_context(spec, run_context, "role") or ""),
            skill_index=skill_index,
            skill_store_root=Path(_required(_input_or_context(spec, run_context, "skill_store_root"), "skill_store_root")),
            run_id=run_context.run_id,
            repo_root=str(run_context.repo_root),
            repo_intelligence=dict(_input_or_context(spec, run_context, "repo_intelligence") or {}),
            artifact_type=str(_input_or_context(spec, run_context, "artifact_type") or "execution_result"),
            context_budget=ContextBudget.from_data(run_context.data),
            enable_context_compaction=context_compaction_enabled(run_context.data),
            data=run_context.mutable_data,
        )
        self.budget_broker.commit(reservation.reservation_id, actual_tokens=context.token_ledger_entry.estimated_input_tokens)
        return ActionResult(
            status="ok",
            summary="ContextService built work-item context.",
            token_used=context.token_ledger_entry.estimated_input_tokens,
            payload={
                "reservation": reservation.model_dump(mode="json"),
                "budget_compressed": budget_compressed,
                "context": context,
                "envelope": context.envelope,
                "skill_route": context.skill_route,
                "context_packet": context.context_packet,
                "token_ledger_entry": context.token_ledger_entry,
                "coding_context_packet": context.coding_context_packet,
                "compact_coding_context_packet": context.compact_coding_context_packet,
                "context_compaction": context.compaction_result.__dict__ if context.compaction_result else None,
            },
        )

    def _read_file(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        path = str(spec.input.get("path") or "").strip()
        if not path:
            return ActionResult(status="failed", summary="read_file requires path.", error_code="path_required")
        target = resolve_scoped_path(Path(run_context.repo_root).resolve(), path, run_context.active_scopes)
        if not target.exists():
            return ActionResult(status="failed", summary=f"File not found: {path}", error_code="missing_file")
        if not target.is_file():
            return ActionResult(status="failed", summary=f"Path is not a file: {path}", error_code="not_file")
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            return ActionResult(status="failed", summary=f"File is not UTF-8 text: {path}", error_code="binary_file")
        start_line = max(1, int(spec.input.get("start_line") or 1))
        end_line_value = spec.input.get("end_line")
        end_line = len(lines) if end_line_value in (None, "") else max(start_line, int(end_line_value))
        selected = lines[start_line - 1 : end_line]
        relative = target.relative_to(Path(run_context.repo_root).resolve()).as_posix()
        payload = {
            "path": relative,
            "start_line": start_line,
            "end_line": min(end_line, len(lines)),
            "total_lines": len(lines),
            "content": "\n".join(selected),
        }
        payload, refs = self._apply_result_budget(spec, run_context, payload)
        return ActionResult(
            status="ok",
            summary=f"Read {relative}:{start_line}-{min(end_line, len(lines))}.",
            output_ref=refs[0] if refs else None,
            payload=payload,
        )

    def _search_files(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        query = str(spec.input.get("query") or "").strip()
        if not query:
            return ActionResult(status="failed", summary="search_files requires query.", error_code="query_required")
        max_results = max(1, min(500, int(spec.input.get("max_results") or 50)))
        root = Path(run_context.repo_root).resolve()
        paths = _string_list(spec.input.get("paths"))
        scan_roots = [resolve_scoped_path(root, path, run_context.active_scopes) for path in paths] if paths else _scope_roots(root, run_context.active_scopes)
        matches: list[dict[str, Any]] = []
        for scan_root in scan_roots:
            candidates = [scan_root] if scan_root.is_file() else scan_root.rglob("*")
            for candidate in candidates:
                if len(matches) >= max_results:
                    break
                if not candidate.is_file() or _ignored(candidate, root) or candidate.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                try:
                    lines = candidate.read_text(encoding="utf-8").splitlines()
                except UnicodeDecodeError:
                    continue
                for line_number, line in enumerate(lines, start=1):
                    if query.lower() not in line.lower():
                        continue
                    matches.append(
                        {
                            "path": candidate.relative_to(root).as_posix(),
                            "line": line_number,
                            "preview": line.strip()[:300],
                        }
                    )
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break
        payload = {
            "query": query,
            "paths": [path.relative_to(root).as_posix() if path != root else "." for path in scan_roots],
            "match_count": len(matches),
            "matches": matches,
            "truncated": len(matches) >= max_results,
        }
        payload, refs = self._apply_result_budget(spec, run_context, payload)
        return ActionResult(
            status="ok",
            summary=f"search_files found {len(matches)} match(es).",
            output_ref=refs[0] if refs else None,
            payload=payload,
        )

    def _inspect_git_diff(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        root = Path(run_context.repo_root).resolve()
        paths = _string_list(spec.input.get("paths"))
        for path in paths:
            resolve_scoped_path(root, path, run_context.active_scopes)
        cmd = ["git", "-C", str(root), "diff", "--"]
        name_cmd = ["git", "-C", str(root), "diff", "--name-status", "--"]
        cmd.extend(paths)
        name_cmd.extend(paths)
        try:
            diff = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
            names = subprocess.run(name_cmd, text=True, capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ActionResult(status="failed", summary=str(exc), error_code="git_diff_failed")
        if diff.returncode != 0:
            message = (diff.stderr or diff.stdout or "git diff failed").strip()
            return ActionResult(status="failed", summary=message, error_code="git_diff_failed")
        files = _parse_name_status(names.stdout if names.returncode == 0 else "")
        payload = {
            "paths": paths,
            "files": files,
            "file_count": len(files),
            "diff": diff.stdout,
        }
        payload, refs = self._apply_result_budget(spec, run_context, payload)
        return ActionResult(
            status="ok",
            summary=f"inspect_git_diff found {len(files)} changed file(s).",
            output_ref=refs[0] if refs else None,
            payload=payload,
        )

    def _read_tool_output(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        output_ref = str(spec.input.get("output_ref") or "").strip()
        if not output_ref:
            return ActionResult(status="failed", summary="read_tool_output requires output_ref.", error_code="output_ref_required")
        data = run_context.mutable_data
        blobs = data.get("pending_blob_writes")
        if isinstance(blobs, dict) and output_ref in blobs:
            record = blobs[output_ref]
            content = record.get("content") if isinstance(record, dict) else None
            preview = record.get("preview") if isinstance(record, dict) else None
            text = str(content if content is not None else preview if preview is not None else "")
            return ActionResult(
                status="ok",
                summary=f"Read stored tool output {output_ref}.",
                output_ref=output_ref,
                payload={
                    "output_ref": output_ref,
                    "preview": text[:4000],
                    "original_chars": len(text),
                    "truncated": len(text) > 4000,
                },
            )
        outputs = data.get("tool_outputs")
        if isinstance(outputs, dict) and output_ref in outputs:
            text = str(outputs[output_ref])
            return ActionResult(
                status="ok",
                summary=f"Read stored tool output {output_ref}.",
                output_ref=output_ref,
                payload={
                    "output_ref": output_ref,
                    "preview": text[:4000],
                    "original_chars": len(text),
                    "truncated": len(text) > 4000,
                },
            )
        return ActionResult(status="failed", summary=f"Tool output not found: {output_ref}", error_code="output_ref_not_found")

    def _propose_patch(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        reservation = self.budget_broker.reserve_tool_call(
            run_id=run_context.run_id,
            agent_id=_agent_id(run_context),
            action_type=spec.action_type,
            estimated_tokens=spec.estimated_tokens,
        )
        if not reservation.approved:
            return _budget_blocked(reservation)
        changes = spec.input.get("changes", spec.input.get("proposed_changes", spec.input))
        preview = self.patch_service_factory(
            run_context.repo_root,
            run_context.active_scopes,
            run_context.mutable_data,
        ).preview(changes)
        self.budget_broker.commit(reservation.reservation_id, actual_tool_calls=1)
        status = "blocked" if preview.get("status") == "blocked" else "ok"
        return ActionResult(
            status=status,
            summary=str(preview.get("message") or "Patch preview generated."),
            error_code=preview.get("error_code") if status == "blocked" else None,
            payload={"reservation": reservation.model_dump(mode="json"), "preview": preview},
        )

    def _apply_patch_sandbox(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        reservation = self.budget_broker.reserve_tool_call(
            run_id=run_context.run_id,
            agent_id=_agent_id(run_context),
            action_type=spec.action_type,
            estimated_tokens=spec.estimated_tokens,
        )
        if not reservation.approved:
            return _budget_blocked(reservation)
        action_root, sandbox_unavailable = _action_root(run_context, sandbox=True)
        patch = spec.input.get("patch", spec.input.get("changes", spec.input.get("proposed_changes", spec.input)))
        result = self.patch_service_factory(
            action_root,
            run_context.active_scopes,
            run_context.mutable_data,
        ).apply(
            patch,
            approved=bool(spec.input.get("approved")) or not sandbox_unavailable,
        )
        self.budget_broker.commit(reservation.reservation_id, actual_tool_calls=1)
        if result.get("blocked") or result.get("status") == "blocked":
            status = "blocked"
        elif result.get("status") in {"rejected", "failed"}:
            status = "failed"
        else:
            status = "ok"
        payload = {
            "reservation": reservation.model_dump(mode="json"),
            "result": result,
            "sandbox_root": str(action_root),
            "sandbox_unavailable": sandbox_unavailable,
        }
        return ActionResult(
            status=status,
            summary=str(result.get("message") or "Sandbox patch apply completed."),
            error_code=result.get("error_code") if status != "ok" else None,
            payload=payload,
        )

    def _run_command(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        reservation = self.budget_broker.reserve_tool_call(
            run_id=run_context.run_id,
            agent_id=_agent_id(run_context),
            action_type=spec.action_type,
            estimated_tokens=spec.estimated_tokens,
        )
        if not reservation.approved:
            return _budget_blocked(reservation)
        command = str(spec.input.get("command") or "")
        sandbox = spec.action_type == "run_command_sandbox"
        action_root, sandbox_unavailable = _action_root(run_context, sandbox=sandbox)
        if "require_approval" in spec.input:
            require_approval = bool(spec.input.get("require_approval"))
        else:
            require_approval = not (sandbox and not sandbox_unavailable)
        argv_input = spec.input.get("argv")
        argv = None
        if isinstance(argv_input, list):
            argv = [str(item) for item in argv_input if str(item)]
        result = self.command_service_factory(
            action_root,
            run_context.active_scopes,
            run_context.mutable_data,
        ).run_check(
            command,
            argv=argv,
            cwd=str(spec.input.get("cwd") or "."),
            timeout_seconds=int(spec.input.get("timeout_seconds") or 120),
            require_approval=require_approval,
            shell=spec.input.get("shell"),
            source=str(spec.input.get("source") or "model"),
            sandbox=sandbox and not sandbox_unavailable,
        )
        self.budget_broker.commit(reservation.reservation_id, actual_tool_calls=1)
        return ActionResult(
            status="blocked" if result.get("blocked") else "ok",
            summary=str(result.get("message") or result.get("output") or "Command completed."),
            error_code="command_requires_approval" if result.get("blocked") else None,
            payload={
                "reservation": reservation.model_dump(mode="json"),
                "result": result,
                "sandbox_root": str(action_root) if sandbox else None,
                "sandbox_unavailable": sandbox_unavailable if sandbox else False,
            },
        )

    def _repo_index(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        reservation = self.budget_broker.reserve_tool_call(
            run_id=run_context.run_id,
            agent_id=_agent_id(run_context),
            action_type=spec.action_type,
            estimated_tokens=spec.estimated_tokens,
        )
        if not reservation.approved:
            return _budget_blocked(reservation)

        intelligence = build_repo_intelligence(str(run_context.repo_root))
        run_context.mutable_data["repo_intelligence"] = intelligence
        self.budget_broker.commit(reservation.reservation_id, actual_tool_calls=1)
        return ActionResult(
            status="ok",
            summary="Repository intelligence built.",
            payload={
                "reservation": reservation.model_dump(mode="json"),
                "repo_intelligence": intelligence,
            },
        )

    def _call_plugin(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        operation_id = str(
            spec.input.get("operation_id")
            or spec.input.get("plugin_operation_id")
            or ""
        ).strip()
        if not operation_id:
            return ActionResult(
                status="failed",
                summary="Plugin operation_id is required.",
                error_code="plugin_operation_id_required",
            )

        reservation = self.budget_broker.reserve_tool_call(
            run_id=run_context.run_id,
            agent_id=_agent_id(run_context),
            action_type=spec.action_type,
            estimated_tokens=spec.estimated_tokens,
        )
        if not reservation.approved:
            return _budget_blocked(reservation)

        runtime = self.extension_runtime_factory()
        capability = runtime.capability(operation_id) if hasattr(runtime, "capability") else None
        policy = merge_extension_policy(
            operation_id=operation_id,
            capability=capability,
            spec_risk_level=spec.risk_level,
            spec_requires_permission=spec.requires_permission,
            input_requires_permission=bool(spec.input.get("requires_permission")),
            input_requires_approval=bool(spec.input.get("requires_approval")),
        )

        if policy.requires_approval and not _action_is_approved(spec, run_context, operation_id, policy.risk_level):
            released = self.budget_broker.release(reservation.reservation_id)
            return ActionResult(
                status="blocked",
                summary="Plugin operation requires approval.",
                error_code="plugin_requires_approval",
                payload={
                    "reservation": released.model_dump(mode="json"),
                    "operation_id": operation_id,
                    "approval_key": _approval_key(spec, operation_id, policy.risk_level),
                    "policy": policy.as_dict(),
                },
            )

        try:
            result = runtime.execute_plugin_operation(
                operation_id,
                dict(spec.input.get("args") or {}),
                {
                    "run_id": run_context.run_id,
                    "repo_root": str(run_context.repo_root),
                    "scopes": run_context.active_scopes,
                    "data": run_context.mutable_data,
                },
            )
        except ValueError as exc:
            if str(exc).startswith("Unknown tool:"):
                released = self.budget_broker.release(reservation.reservation_id)
                return ActionResult(
                    status="failed",
                    summary=str(exc),
                    error_code="plugin_unknown_operation",
                    payload={
                        "reservation": released.model_dump(mode="json"),
                        "operation_id": operation_id,
                        "policy": policy.as_dict(),
                    },
                )
            raise
        self.budget_broker.commit(reservation.reservation_id, actual_tool_calls=1)

        status_value = str(result.get("status") or "")
        if status_value == "blocked":
            status = "blocked"
        elif status_value in {"failed", "error"}:
            status = "failed"
        else:
            status = "ok"
        return ActionResult(
            status=status,
            summary=f"Plugin operation {operation_id} completed with status {status_value or status}.",
            error_code=None if status == "ok" else f"plugin_{status}",
            payload={
                "reservation": reservation.model_dump(mode="json"),
                "operation": result,
                "policy": policy.as_dict(),
            },
        )

    def _call_mcp(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        mcp_spec = spec.model_copy(
            update={
                "action_type": "call_plugin",
                "input": {
                    "operation_id": "mcp_call",
                    "args": dict(spec.input.get("args") or spec.input),
                    "approved": spec.input.get("approved", False),
                    "requires_permission": spec.input.get("requires_permission", True),
                    "requires_approval": spec.input.get("requires_approval", True),
                    **({"approval_key": spec.input["approval_key"]} if "approval_key" in spec.input else {}),
                },
            }
        )
        result = self._call_plugin(mcp_spec, run_context)
        if result.error_code == "plugin_operation_id_required":
            return result.model_copy(
                update={
                    "summary": "MCP operation_id is required.",
                    "error_code": "mcp_operation_id_required",
                }
            )
        if result.error_code == "plugin_requires_approval":
            return result.model_copy(
                update={
                    "summary": "MCP operation requires approval.",
                    "error_code": "mcp_requires_approval",
                }
            )
        if result.error_code == "plugin_unknown_operation":
            return result.model_copy(update={"error_code": "mcp_unknown_operation"})
        return result

    def _validate_artifact(self, spec: ActionSpec) -> ActionResult:
        artifact_type = str(spec.input.get("expected_type") or spec.input.get("artifact_type") or "")
        try:
            artifact = validate_artifact(dict(spec.input.get("artifact") or {}), expected_type=artifact_type)
        except (ArtifactValidationError, ValueError) as exc:
            return ActionResult(status="failed", summary=str(exc), error_code="artifact_validation_failed")
        return ActionResult(status="ok", summary="Artifact validated.", payload={"artifact": artifact})

    def _repair_artifact(self, spec: ActionSpec, run_context: RunContext) -> ActionResult:
        if run_context.model is None:
            return ActionResult(status="blocked", summary="Repair requires a model.", error_code="model_required")
        repaired = self.repair_service.repair_once(
            run_context.model,
            expected_type=str(spec.input.get("expected_type") or ""),
            invalid_output=str(spec.input.get("invalid_output") or ""),
            agent_id=str(spec.input.get("agent_id") or _agent_id(run_context) or "agent"),
            emit=run_context.emit,
            work_item_id=str(spec.input.get("work_item_id") or "") or None,
            merge_index=spec.input.get("merge_index"),
            schema_notes=str(spec.input.get("schema_notes") or ""),
        )
        if repaired is None:
            return ActionResult(status="failed", summary="Artifact repair failed.", error_code="artifact_repair_failed")
        return ActionResult(status="ok", summary="Artifact repaired.", payload={"artifact": repaired})


def _scope_roots(root: Path, scopes: list[str]) -> list[Path]:
    if not scopes:
        return [root]
    return [resolve_scoped_path(root, scope, []) for scope in scopes]


def _ignored(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in DEFAULT_IGNORE_DIRS or part.endswith(".egg-info") for part in parts)


def _parse_name_status(value: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for line in value.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            files.append({"status": parts[0], "path": parts[-1]})
    return files


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _budget_blocked(reservation: Any) -> ActionResult:
    return ActionResult(
        status="blocked",
        summary="BudgetBroker denied the action.",
        error_code=reservation.reason,
        payload={"reservation": reservation.model_dump(mode="json")},
    )


def _agent_id(run_context: RunContext) -> str | None:
    item = run_context.item
    return str(getattr(item, "assignee_agent_id", "") or "") or None


def _action_root(run_context: RunContext, *, sandbox: bool) -> tuple[Path, bool]:
    if sandbox and run_context.sandbox_root is not None:
        return Path(run_context.sandbox_root), False
    return Path(run_context.repo_root), bool(sandbox)


def _action_is_approved(spec: ActionSpec, run_context: RunContext, operation_id: str, risk_level: str | None = None) -> bool:
    if bool(spec.input.get("approved")):
        return True
    data = run_context.mutable_data
    if data.get("preapprove_all"):
        return True
    approvals = data.get("plugin_approvals", {})
    return isinstance(approvals, dict) and approvals.get(_approval_key(spec, operation_id, risk_level)) is True


def _approval_key(spec: ActionSpec, operation_id: str, risk_level: str | None = None) -> str:
    return str(spec.input.get("approval_key") or f"plugin:{operation_id}:{risk_level or spec.risk_level}")


def _estimate_context_tokens(spec: ActionSpec, run_context: RunContext, skill_index: SkillIndex) -> int:
    item = _input_or_context(spec, run_context, "item")
    task_summary = str(getattr(item, "task_summary", "") or "")
    upstream_refs = " ".join(str(ref) for ref in (_input_or_context(spec, run_context, "upstream_refs") or []))
    text = " ".join(
        [
            str(_input_or_context(spec, run_context, "user_request") or ""),
            task_summary,
            upstream_refs,
            str(_input_or_context(spec, run_context, "planner_order_ref") or ""),
        ]
    )
    return estimate_tokens(text) + sum(skill.max_skill_tokens for skill in skill_index.enabled())


def _tool_execution_spec(spec: ActionSpec, run_context: RunContext) -> ToolExecutionSpec:
    timeout_seconds = float(spec.input.get("timeout_seconds") or 120)
    return ToolExecutionSpec(
        action_id=spec.action_id,
        action_type=spec.action_type,
        input=dict(spec.input),
        agent_id=_agent_id(run_context),
        work_item_id=str(getattr(run_context.item, "work_item_id", "") or "") or None,
        timeout_seconds=max(0.001, timeout_seconds),  # type: ignore[arg-type]
        concurrency_key=_concurrency_key(spec, run_context),
        requires_exclusive_access=_requires_exclusive_access(spec),
        is_read_only=_is_read_only_action(spec),
        can_cancel=True,
        cancel_pending_on_failure=bool(spec.input.get("cancel_pending_on_failure")),
    )


def _action_result_from_tool_execution(result: ToolExecutionResult, payload: dict[str, Any]) -> ActionResult:
    if result.status == "ok":
        status = "ok"
    elif result.status == "blocked":
        status = "blocked"
    elif result.status == "cancelled":
        status = "blocked"
    else:
        status = "failed"
    return ActionResult(
        status=status,
        summary=result.summary,
        error_code=result.error_code,
        payload={
            **payload,
            "tool_execution": {
                "action_id": result.action_id,
                "action_type": result.action_type,
                "status": result.status,
                "started_at": result.started_at,
                "completed_at": result.completed_at,
                "elapsed_ms": result.elapsed_ms,
                "error_code": result.error_code,
            },
        },
    )


def _requires_exclusive_access(spec: ActionSpec) -> bool:
    if "requires_exclusive_access" in spec.input:
        return bool(spec.input["requires_exclusive_access"])
    return spec.action_type in {
        "apply_patch_sandbox",
        "run_command",
        "run_command_sandbox",
        "call_plugin",
        "call_mcp",
    }


def _is_read_only_action(spec: ActionSpec) -> bool:
    if "is_read_only" in spec.input:
        return bool(spec.input["is_read_only"])
    return spec.action_type in {
        "repo_index",
        "read_file",
        "search_files",
        "inspect_git_diff",
        "read_tool_output",
    }


def _concurrency_key(spec: ActionSpec, run_context: RunContext) -> str:
    if spec.input.get("concurrency_key"):
        return str(spec.input["concurrency_key"])
    if spec.action_type in {"run_command", "run_command_sandbox"}:
        return f"repo:{Path(run_context.repo_root).resolve()}:command"
    if spec.action_type in {"apply_patch_sandbox", "propose_patch"}:
        return f"repo:{Path(run_context.repo_root).resolve()}:patch"
    return f"repo:{Path(run_context.repo_root).resolve()}:{spec.action_type}"


def _feature_enabled(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _input_or_context(spec: ActionSpec, run_context: RunContext, key: str) -> Any:
    if key in spec.input:
        return spec.input[key]
    return getattr(run_context, key)


def _required(value: Any, name: str) -> Any:
    if value is None:
        raise ValueError(f"{name} is required")
    return value
