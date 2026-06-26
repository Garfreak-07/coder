from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .contracts import harness_contract_for_id
from .native_events import NativeRuntimeEvent
from .profiles import OPENHANDS_PROVIDER_ID
from .runtime_context import HarnessRunRequest, HarnessRunResult
from .sandbox import SandboxPreparationError, collect_workspace_changes, prepare_sandbox_workspace
from .store import NativeRuntimeStore


_INSUFFICIENT_PLANNER_OUTPUT_MESSAGE = (
    "OpenHands workflow supervisor did not return an actionable planner_order or an explicit no-work rationale."
)


class OpenHandsRuntimeProvider:
    """Feature-flagged OpenHands SDK provider boundary.

    This module is the only place that may import OpenHands SDK modules. The
    provider dynamically loads the SDK, records native-provider lifecycle facts,
    and fails closed when the SDK, credentials, or sandbox workspace are not
    available.
    """

    provider_id = OPENHANDS_PROVIDER_ID

    def __init__(
        self,
        *,
        runtime_module_names: tuple[str, ...] | None = None,
        native_store: NativeRuntimeStore | None = None,
        sdk_loader: Callable[[], Any | None] | None = None,
    ) -> None:
        self.runtime_module_names = runtime_module_names or (
            "openhands.sdk",
            "openhands.tools.file_editor",
            "openhands.tools.task_tracker",
            "openhands.tools.terminal",
        )
        self.native_store = native_store or NativeRuntimeStore()
        self._sdk_loader = sdk_loader

    def is_available(self) -> bool:
        return self._load_sdk() is not None

    def run(self, request: HarnessRunRequest, *, emit: Any | None = None) -> HarnessRunResult:
        sdk = self._load_sdk()
        if sdk is None:
            return self._failed(
                request,
                emit=emit,
                code="openhands_sdk_unavailable",
                message="OpenHands SDK is not importable in this environment.",
                native_type="sdk.unavailable",
            )

        artifact_type, artifact_error = _artifact_type_for_request(request)
        if artifact_error is not None:
            return self._failed(
                request,
                emit=emit,
                code="invalid_requested_artifact_type",
                message=artifact_error,
                native_type="artifact_target.invalid",
            )

        self._emit(
            emit,
            "harness_runtime.openhands.started",
            "OpenHands runtime provider selected",
            mode=request.mode,
            profile_id=request.profile.id,
        )
        selected_event = self._record_event(
            request,
            native_type="provider.selected",
            status="completed",
            summary="OpenHands runtime provider selected.",
            payload={
                "mode": request.mode,
                "profile_id": request.profile.id,
            },
        )

        credentials = _llm_credentials()
        if credentials["api_key"] is None:
            return self._failed(
                request,
                emit=emit,
                code="openhands_llm_credentials_missing",
                message="OpenHands runtime requires LLM_API_KEY or DEEPSEEK_API_KEY.",
                native_type="credentials.missing",
                status="blocked",
                refs=[selected_event.event_id],
            )

        contract = harness_contract_for_id(request.contract_id)
        try:
            sandbox_context = prepare_sandbox_workspace(
                contract=contract,
                profile=request.profile,
                context=request.context,
            )
        except SandboxPreparationError as exc:
            return self._failed(
                request,
                emit=emit,
                code="openhands_sandbox_unavailable",
                message=str(exc),
                native_type="sandbox.unavailable",
                status="blocked",
                refs=[selected_event.event_id],
            )

        try:
            with sandbox_context as sandbox:
                workspace = sandbox.path
                sandbox_event = self._record_event(
                    request,
                    native_type="sandbox.prepared",
                    status="completed",
                    summary="Sandbox workspace prepared.",
                    payload={
                        "mode": request.mode,
                        "workspace_mode": sandbox.workspace_mode,
                        "temporary": sandbox.temporary,
                        "workspace": str(workspace),
                    },
                )
                started_event = self._record_event(
                    request,
                    native_type="conversation.started",
                    status="running",
                    summary="OpenHands conversation started.",
                    payload={
                        "mode": request.mode,
                        "workspace": str(workspace),
                        "tools": self._tool_names_for_request(request, sdk),
                        "model": credentials["model"],
                        "base_url_configured": bool(credentials["base_url"]),
                    },
                )
                prompt = _prompt_for_request(request)
                try:
                    tools = self._tools_for_request(request, sdk)
                    llm = sdk.LLM(
                        model=credentials["model"],
                        api_key=credentials["api_key"],
                        base_url=credentials["base_url"],
                    )
                    agent = sdk.Agent(llm=llm, tools=tools)
                    conversation = sdk.Conversation(agent=agent, workspace=str(workspace))
                    conversation.send_message(prompt)
                    run_output = conversation.run()
                    if artifact_type == "planner_order":
                        run_output = _with_conversation_event_sources(run_output, conversation)
                except Exception as exc:
                    return self._failed(
                        request,
                        emit=emit,
                        code="openhands_run_failed",
                        message=f"OpenHands conversation failed: {exc}",
                        native_type="conversation.failed",
                        refs=[selected_event.event_id, sandbox_event.event_id, started_event.event_id],
                        payload={"error_type": type(exc).__name__, "message": str(exc)},
                    )

                summary = _summarize_run_output(run_output)
                structured_artifact = _extract_structured_artifact(run_output, artifact_type=str(artifact_type or ""))
                facts = _merge_runtime_facts(
                    _runtime_facts(run_output),
                    self._sandbox_facts(request, sandbox),
                )
                facts["native_event_refs"] = _dedupe(
                    [sandbox_event.event_id, started_event.event_id, *facts["native_event_refs"]]
                )
                if artifact_type == "planner_order":
                    planner_artifact, planner_error = _planner_order_artifact_from_structured(
                        structured_artifact,
                        request=request,
                        summary=summary,
                    )
                    if planner_error is not None:
                        return self._failed(
                            request,
                            emit=emit,
                            code="insufficient_structured_planner_output",
                            message=_INSUFFICIENT_PLANNER_OUTPUT_MESSAGE,
                            native_type="planner_output.insufficient",
                            status="blocked",
                            refs=[
                                selected_event.event_id,
                                sandbox_event.event_id,
                                started_event.event_id,
                                *facts["native_event_refs"],
                            ],
                            payload={
                                "code": "insufficient_structured_planner_output",
                                "message": _INSUFFICIENT_PLANNER_OUTPUT_MESSAGE,
                                "reason": planner_error,
                                "structured_artifact_found": structured_artifact is not None,
                                "output_type": type(run_output).__name__,
                            },
                        )
                    structured_artifact = planner_artifact
        except SandboxPreparationError as exc:
            return self._failed(
                request,
                emit=emit,
                code="openhands_sandbox_unavailable",
                message=str(exc),
                native_type="sandbox.unavailable",
                status="blocked",
                refs=[selected_event.event_id],
            )

        completed_event = self._record_event(
            request,
            native_type="conversation.completed",
            status="completed",
            summary=summary,
            payload={
                "mode": request.mode,
                "output_type": type(run_output).__name__,
                "output_summary": summary,
                "changed_files": facts["changed_files"],
                "created_files": facts["created_files"],
                "deleted_files": facts["deleted_files"],
                "diff_refs": facts["diff_refs"],
                "log_refs": facts["log_refs"],
                "evidence_refs": facts["evidence_refs"],
            },
        )
        refs = [selected_event.event_id, *facts["native_event_refs"], completed_event.event_id]
        evidence_refs = _dedupe([*refs, *facts["evidence_refs"]])
        self._emit(
            emit,
            "harness_runtime.openhands.completed",
            summary,
            mode=request.mode,
            profile_id=request.profile.id,
            native_event_refs=refs,
        )
        return HarnessRunResult(
            status="completed",
            artifact_type=artifact_type,
            artifact=_artifact_for_success(
                request,
                artifact_type=artifact_type,
                summary=summary,
                evidence_refs=evidence_refs,
                facts=facts,
                structured_artifact=structured_artifact,
            ),
            native_event_refs=refs,
            evidence_refs=evidence_refs,
            diff_refs=facts["diff_refs"],
            log_refs=facts["log_refs"],
        )

    def _load_sdk(self) -> Any | None:
        if self._sdk_loader is not None:
            try:
                return self._sdk_loader()
            except Exception:
                return None
        for module_name in self.runtime_module_names:
            try:
                if importlib.util.find_spec(module_name) is None:
                    return None
            except (ImportError, ValueError):
                return None
        try:
            sdk = importlib.import_module("openhands.sdk")
            file_editor = importlib.import_module("openhands.tools.file_editor")
            task_tracker = importlib.import_module("openhands.tools.task_tracker")
            terminal = importlib.import_module("openhands.tools.terminal")
        except ImportError:
            return None
        return SimpleNamespace(
            LLM=sdk.LLM,
            Agent=sdk.Agent,
            Conversation=sdk.Conversation,
            Tool=sdk.Tool,
            FileEditorTool=file_editor.FileEditorTool,
            TaskTrackerTool=task_tracker.TaskTrackerTool,
            TerminalTool=terminal.TerminalTool,
        )

    def _workspace_for_request(self, request: HarnessRunRequest) -> Path | None:
        if request.mode == "task_execution":
            if request.context.sandbox_root:
                return Path(request.context.sandbox_root)
            if request.profile.sandbox_policy.get("allow_repo_root_for_tests") and request.context.repo_root:
                return Path(request.context.repo_root)
            return None
        if request.context.sandbox_root:
            return Path(request.context.sandbox_root)
        if request.context.repo_root:
            return Path(request.context.repo_root)
        return Path(".")

    def _tool_names_for_request(self, request: HarnessRunRequest, sdk: Any) -> list[str]:
        if request.mode == "task_execution":
            return [sdk.TerminalTool.name, sdk.FileEditorTool.name, sdk.TaskTrackerTool.name]
        return [sdk.TaskTrackerTool.name]

    def _tools_for_request(self, request: HarnessRunRequest, sdk: Any) -> list[Any]:
        return [sdk.Tool(name=name) for name in self._tool_names_for_request(request, sdk)]

    def _sandbox_facts(self, request: HarnessRunRequest, sandbox: Any) -> dict[str, list[str]]:
        facts = _empty_runtime_facts()
        if request.mode != "task_execution":
            return facts
        changes = collect_workspace_changes(sandbox)
        facts["changed_files"] = list(changes["changed_files"])
        facts["created_files"] = list(changes["created_files"])
        facts["deleted_files"] = list(changes["deleted_files"])
        has_changes = bool(facts["changed_files"] or facts["created_files"] or facts["deleted_files"])
        diff_text = str(changes.get("diff") or "")
        if request.profile.sandbox_policy.get("collect_diff_refs", True) and diff_text:
            diff_event = self._record_event(
                request,
                native_type="sandbox.diff",
                status="completed",
                summary="Sandbox workspace diff collected.",
                payload=diff_text,
            )
            facts["diff_refs"].append(diff_event.payload_ref or diff_event.event_id)
            facts["native_event_refs"].append(diff_event.event_id)
        if has_changes and request.profile.sandbox_policy.get("collect_log_refs", True):
            log_event = self._record_event(
                request,
                native_type="sandbox.summary",
                status="completed",
                summary="Sandbox workspace summary collected.",
                payload={
                    "workspace_mode": sandbox.workspace_mode,
                    "temporary": sandbox.temporary,
                    "changed_files": facts["changed_files"],
                    "created_files": facts["created_files"],
                    "deleted_files": facts["deleted_files"],
                    "diff_refs": facts["diff_refs"],
                },
            )
            facts["log_refs"].append(log_event.payload_ref or log_event.event_id)
            facts["native_event_refs"].append(log_event.event_id)
        facts["evidence_refs"] = _dedupe([*facts["diff_refs"], *facts["log_refs"]])
        return facts

    def _failed(
        self,
        request: HarnessRunRequest,
        *,
        emit: Any | None,
        code: str,
        message: str,
        native_type: str,
        status: str = "failed",
        refs: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> HarnessRunResult:
        event = self._record_event(
            request,
            native_type=native_type,
            status=status,
            summary=message,
            payload=payload or {"code": code, "message": message},
        )
        self._emit(
            emit,
            "harness_runtime.openhands.failed",
            message,
            mode=request.mode,
            profile_id=request.profile.id,
            native_event_ref=event.event_id,
        )
        native_event_refs = [*(refs or []), event.event_id]
        return HarnessRunResult(
            status=status,
            artifact_type=_artifact_type_for_request(request)[0] if status == "blocked" else None,
            artifact=_artifact_for_blocked(request, message=message, evidence_refs=native_event_refs)
            if status == "blocked"
            else None,
            native_event_refs=native_event_refs,
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


def _llm_credentials() -> dict[str, str | None]:
    base_url = os.getenv("LLM_BASE_URL") or "https://api.deepseek.com"
    model = _normalize_deepseek_model(os.getenv("LLM_MODEL") or "deepseek-v4-flash", base_url=base_url)
    return {
        "api_key": os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
        "model": model,
        "base_url": base_url,
    }


def _normalize_deepseek_model(model: str, *, base_url: str | None) -> str:
    text = model.strip() or "deepseek-v4-flash"
    if "/" in text:
        return text
    if text.startswith("deepseek-") or text in {"deepseek-chat", "deepseek-reasoner"}:
        return f"deepseek/{text}"
    if "deepseek.com" in str(base_url or "").lower() and text.startswith("v"):
        return f"deepseek/{text}"
    return text


def _prompt_for_request(request: HarnessRunRequest) -> str:
    context_packet = request.context.context_packet or {}
    artifact_type, _artifact_error = _artifact_type_for_request(request)
    artifact_target = artifact_type or "unknown"
    lines = [
        f"Runtime mode: {request.mode}",
        f"Workflow: {request.context.workflow_id}",
        f"Agent: {request.context.agent_id}",
        f"Current Coder artifact target: {artifact_target}",
    ]
    if request.mode == "task_execution":
        lines.extend(
            [
                "You are the Task Execution Harness.",
                "Stay inside the provided workspace.",
                "Perform only bounded task execution inside the sandbox workspace.",
                "Do not ask the user any questions.",
                "Do not commit, push, deploy, publish externally, or write long-term memory.",
                "Return enough structured information for Coder to project a valid execution_result artifact.",
                "Return a concise completion summary and verification evidence.",
            ]
        )
        _append_section(lines, "Work item", request.input_artifacts.get("work_item") or _dig(context_packet, "hot", "work_item"))
        _append_section(
            lines,
            "Task envelope",
            request.input_artifacts.get("task_envelope") or _dig(context_packet, "hot", "task_envelope"),
        )
        _append_section(lines, "Constraints", _dig(context_packet, "hot", "constraints"))
        _append_section(lines, "Success criteria", request.input_artifacts.get("success_criteria"))
        return "\n\n".join(lines)
    if request.mode == "workflow_supervisor":
        lines.extend(
            [
                "You are the Workflow Supervisor Harness.",
                "Do not write files or run commands.",
                f"Return enough structured information for Coder to project a valid {artifact_target} artifact.",
                "Use execution summaries and evidence refs to decide whether the workflow should continue or finish.",
            ]
        )
        _append_section(lines, "Confirmed goal", _dig(context_packet, "hot", "confirmed_goal") or _dig(context_packet, "hot", "user_goal"))
        _append_section(lines, "Round state", request.context.round_working_set or _dig(context_packet, "warm", "run_state_summary"))
        _append_section(lines, "Round summary", _dig(context_packet, "warm", "round_summary"))
        _append_section(lines, "Execution summaries", _dig(context_packet, "warm", "execution_result_summaries"))
        _append_section(lines, "Verification summaries", _dig(context_packet, "warm", "verification_summaries"))
        _append_section(lines, "Blocked reasons", _dig(context_packet, "warm", "blocked_reasons"))
        _append_section(lines, "Changed files summary", _dig(context_packet, "warm", "changed_files_summary"))
        _append_section(lines, "Evidence refs", request.input_artifacts.get("evidence_refs") or _cold_refs(context_packet, "evidence"))
        _append_section(lines, "Native runtime refs", _cold_refs(context_packet, "native_runtime"))
        _append_section(lines, "Diff refs", _cold_refs(context_packet, "diff"))
        _append_section(lines, "Log refs", _cold_refs(context_packet, "log"))
        _append_artifact_output_contract(lines, artifact_target)
        return "\n\n".join(lines)
    lines.extend(
        [
            "You are the Planning Chat Harness.",
            "Produce a draft only.",
            "Return enough structured information for Coder to project a valid project_plan_draft artifact.",
            "Do not execute commands, modify files, or start the live run.",
        ]
    )
    _append_section(lines, "User request", request.input_artifacts.get("user_request") or _dig(context_packet, "hot", "user_goal"))
    _append_section(lines, "Workflow summary", _dig(context_packet, "warm", "workflow_summary"))
    _append_section(lines, "Selected knowledge pack IDs", _dig(context_packet, "hot", "selected_knowledge_pack_ids"))
    _append_section(lines, "Selected skill pack IDs", _dig(context_packet, "hot", "selected_skill_pack_ids"))
    _append_section(lines, "Selected memory pack IDs", _dig(context_packet, "hot", "selected_memory_pack_ids"))
    return "\n\n".join(lines)


def _append_artifact_output_contract(lines: list[str], artifact_target: str) -> None:
    if artifact_target == "planner_order":
        _append_planner_order_output_contract(lines)


def _append_planner_order_output_contract(lines: list[str]) -> None:
    lines.extend(
        [
            "Output contract for Coder:",
            "Return exactly one JSON object.",
            "Do not return prose before or after the JSON object.",
            "Do not wrap the JSON in Markdown unless the runtime forces Markdown formatting.",
            "The JSON object must be one of the following two shapes.",
            "",
            "Shape A: actionable planner_order with executor work:",
            _safe_json(
                {
                    "artifact_type": "planner_order",
                    "round": 1,
                    "round_goal": "One concise sentence describing the current execution round.",
                    "plan_graph": {
                        "work_items": [
                            {
                                "work_item_id": "executor-work-1",
                                "merge_index": 1,
                                "assignee_agent_id": "executor",
                                "task_summary": "Concrete executor task summary.",
                                "depends_on": [],
                            }
                        ]
                    },
                    "instructions_for_executor": ["Concrete bounded implementation instructions."],
                    "allowed_actions": ["modify_files", "run_commands"],
                    "forbidden_actions": ["commit", "push", "deploy"],
                    "expected_outputs": ["execution_result with evidence refs"],
                    "risk_level": "low",
                    "requires_human_confirmation": False,
                }
            ),
            "",
            "Shape B: explicit no-work planner_order:",
            _safe_json(
                {
                    "artifact_type": "planner_order",
                    "round": 1,
                    "round_goal": "No executor action is required.",
                    "plan_graph": {"work_items": []},
                    "no_work_rationale": (
                        "Explain why the request is already satisfied or why no executor work is needed."
                    ),
                    "instructions_for_executor": [],
                    "allowed_actions": [],
                    "forbidden_actions": ["write_files", "run_commands", "commit", "push", "deploy"],
                    "expected_outputs": ["No executor output is expected."],
                    "risk_level": "low",
                    "requires_human_confirmation": False,
                }
            ),
            "",
            "Rules:",
            "- Use Shape A when the user request requires repository changes, checks, investigation, or implementation.",
            "- Use Shape B only when no executor work is genuinely needed.",
            "- Never return an empty work_items list unless no_work_rationale is present.",
            "- If you cannot produce one of these JSON objects, return the closest valid blocked planner_order JSON instead of prose.",
            "- The JSON is the answer. Do not add explanation outside it.",
        ]
    )

def _append_section(lines: list[str], title: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    lines.append(f"{title}:\n{_safe_json(value)}")


def _safe_json(value: Any, *, limit: int = 4000) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = str(value) if not isinstance(value, (dict, list)) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...<truncated>..."


def _dig(value: dict[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _cold_refs(context_packet: dict[str, Any], ref_type: str) -> list[str]:
    refs: list[str] = []
    for record in context_packet.get("cold_refs", []):
        if isinstance(record, dict) and record.get("ref_type") == ref_type and isinstance(record.get("refs"), list):
            refs.extend(str(ref) for ref in record["refs"])
    return refs


def _with_conversation_event_sources(run_output: Any, conversation: Any) -> Any:
    event_texts = _conversation_agent_event_texts(conversation)
    if not event_texts:
        return run_output
    if run_output is None:
        return event_texts
    return [run_output, *event_texts]


def _conversation_agent_event_texts(conversation: Any) -> list[str]:
    state = getattr(conversation, "state", None)
    events = getattr(state, "events", None)
    if events is None:
        return []
    try:
        event_list = list(events)
    except TypeError:
        return []

    texts: list[str] = []
    for event in reversed(event_list):
        if str(getattr(event, "source", "")).lower() != "agent":
            continue
        message = getattr(event, "llm_message", None)
        text = _content_text(getattr(message, "content", None))
        if text:
            texts.append(text)
    return texts


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
            continue
        text = getattr(item, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(part.strip() for part in parts if part.strip())


def _artifact_type_for_request(request: HarnessRunRequest) -> tuple[str | None, str | None]:
    requested = request.input_artifacts.get("requested_artifact_type")
    if requested:
        return _validate_requested_artifact_type(request.mode, str(requested))

    legacy_operation = str(request.input_artifacts.get("legacy_operation") or "")
    mapped = _artifact_type_from_legacy_operation(legacy_operation)
    if mapped:
        return _validate_requested_artifact_type(request.mode, mapped)

    if request.mode == "task_execution":
        return "execution_result", None
    if request.mode == "planning_chat":
        return "project_plan_draft", None
    return "final_report", None


def _artifact_type_from_legacy_operation(operation: str) -> str | None:
    return {
        "planner_order": "planner_order",
        "planner_decision": "planner_decision",
        "final_report": "final_report",
        "task_execution": "execution_result",
        "planning_chat": "project_plan_draft",
    }.get(operation)


def _validate_requested_artifact_type(mode: str, artifact_type: str) -> tuple[str | None, str | None]:
    allowed = {
        "planning_chat": {"project_plan_draft"},
        "task_execution": {"execution_result"},
        "workflow_supervisor": {"planner_order", "planner_decision", "final_report"},
    }.get(mode, set())
    if artifact_type in allowed:
        return artifact_type, None
    expected = ", ".join(sorted(allowed)) or "none"
    return None, f"{artifact_type!r} is not a valid artifact target for mode {mode!r}; expected one of: {expected}."


def _artifact_for_success(
    request: HarnessRunRequest,
    *,
    artifact_type: str,
    summary: str,
    evidence_refs: list[str],
    facts: dict[str, Any],
    structured_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if structured_artifact is not None:
        if artifact_type == "planner_order":
            return structured_artifact
        if artifact_type == "planner_decision":
            return _planner_decision_artifact_from_structured(structured_artifact, request=request, summary=summary)
        if artifact_type == "final_report":
            return _final_report_artifact_from_structured(structured_artifact, summary=summary, evidence_refs=evidence_refs)
        if artifact_type == "project_plan_draft":
            return _project_plan_draft_from_structured(structured_artifact, request=request, summary=summary)

    if artifact_type == "execution_result":
        checks_run = _check_records(facts.get("checks_run"))
        verification_status = "pass" if _has_passing_check(checks_run) else "skipped"
        no_check_rationale = (
            None
            if verification_status == "pass"
            else "OpenHands conversation completed; no explicit passing check evidence was extracted."
        )
        return {
            "artifact_type": "execution_result",
            "round": request.context.round or 1,
            "work_item_id": str(request.input_artifacts.get("work_item_id") or "") or None,
            "agent_id": request.context.agent_id,
            "status": "completed",
            "summary": summary,
            "changed_files": facts["changed_files"],
            "created_files": facts["created_files"],
            "deleted_files": facts["deleted_files"],
            "patch_refs": facts["diff_refs"],
            "attempted_actions": facts["commands_run"],
            "evidence_refs": evidence_refs,
            "no_op_rationale": None
            if _has_runtime_evidence(facts)
            else "OpenHands conversation completed without extracted file changes, command results, or check evidence.",
            "verification": {
                "status": verification_status,
                "checks_run": checks_run,
                "evidence_refs": evidence_refs,
                "confidence": "medium",
                "no_check_rationale": no_check_rationale,
            },
        }
    if artifact_type == "project_plan_draft":
        draft_id = str(request.input_artifacts.get("draft_id") or request.request_id)
        return {
            "artifact_type": "project_plan_draft",
            "draft_id": draft_id,
            "summary": summary,
            "proposed_scope": [],
            "success_criteria": ["Confirm the draft before execution."],
            "risks": [],
            "requires_confirmation": True,
        }
    if artifact_type == "planner_order":
        return {
            "artifact_type": "planner_order",
            "round": request.context.round or 1,
            "round_goal": summary or "Workflow supervisor found no executor work.",
            "plan_graph": {"work_items": []},
            "instructions_for_executor": [
                "No task_execution work item was created because OpenHands returned only supervisor-level information."
            ],
            "allowed_actions": [],
            "forbidden_actions": ["write_files", "run_commands"],
            "expected_outputs": ["No executor output is expected for this no-work planner_order."],
            "risk_level": "low",
            "requires_human_confirmation": False,
        }
    if artifact_type == "planner_decision":
        return {
            "artifact_type": "planner_decision",
            "round": request.context.round or 1,
            "task_done": True,
            "next_action": "finish",
            "final_status": "completed",
            "risk_level": "low",
            "requires_human_confirmation": False,
            "reason": summary or "OpenHands workflow supervisor completed.",
            "next_round_goal": "",
            "remaining_auto_rounds": 0,
            "human_message": None,
        }
    return {
        "artifact_type": "final_report",
        "status": "completed",
        "summary": summary,
        "checks": [],
        "completed": [summary],
        "blocked_by": [],
        "failed_by": [],
        "warnings": [],
        "notes": [],
        "next_steps": [],
        "evidence_refs": evidence_refs,
    }


def _artifact_for_blocked(request: HarnessRunRequest, *, message: str, evidence_refs: list[str]) -> dict[str, Any]:
    artifact_type = _artifact_type_for_request(request)[0]
    if artifact_type == "execution_result":
        return {
            "artifact_type": "execution_result",
            "round": request.context.round or 1,
            "work_item_id": str(request.input_artifacts.get("work_item_id") or "") or None,
            "agent_id": request.context.agent_id,
            "status": "blocked",
            "summary": message,
            "evidence_refs": evidence_refs,
            "remaining_work": ["Resolve the OpenHands runtime blocker."],
            "unexpected_issues": [message],
            "needs_planner_decision": True,
            "blocker_type": "missing_secret" if "API_KEY" in message else "sandbox_unavailable",
            "executor_recovery_exhausted": True,
            "blocker_reason": message,
            "planner_recommendation": "finish",
            "verification": {
                "status": "blocked",
                "checks_run": [],
                "evidence_refs": evidence_refs,
                "confidence": "medium",
                "remaining_work": ["Resolve the OpenHands runtime blocker."],
            },
        }
    if artifact_type == "project_plan_draft":
        draft_id = str(request.input_artifacts.get("draft_id") or request.request_id)
        return {
            "artifact_type": "project_plan_draft",
            "draft_id": draft_id,
            "summary": message,
            "proposed_scope": [],
            "success_criteria": [],
            "risks": [message],
            "requires_confirmation": True,
        }
    if artifact_type == "planner_order":
        return {
            "artifact_type": "planner_order",
            "round": request.context.round or 1,
            "round_goal": f"OpenHands workflow supervisor blocked: {message}",
            "plan_graph": {"work_items": []},
            "instructions_for_executor": [message],
            "allowed_actions": [],
            "forbidden_actions": ["write_files", "run_commands"],
            "expected_outputs": ["Resolve the OpenHands runtime blocker before creating executor work."],
            "risk_level": "medium",
            "requires_human_confirmation": False,
        }
    if artifact_type == "planner_decision":
        return {
            "artifact_type": "planner_decision",
            "round": request.context.round or 1,
            "task_done": False,
            "next_action": "finish",
            "final_status": "blocked",
            "risk_level": "medium",
            "requires_human_confirmation": False,
            "reason": message,
            "next_round_goal": "",
            "remaining_auto_rounds": 0,
            "human_message": None,
        }
    return {
        "artifact_type": "final_report",
        "status": "blocked",
        "summary": message,
        "checks": [],
        "completed": [],
        "blocked_by": [message],
        "failed_by": [],
        "warnings": [],
        "notes": [],
        "next_steps": ["Resolve the OpenHands runtime blocker."],
        "evidence_refs": evidence_refs,
    }


def _summarize_run_output(run_output: Any) -> str:
    if isinstance(run_output, str) and run_output.strip():
        return run_output.strip()
    for attr in ("summary", "final_message", "message", "content"):
        value = getattr(run_output, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if run_output is None:
        return "OpenHands conversation completed."
    return "OpenHands conversation completed."


def _runtime_facts(run_output: Any) -> dict[str, Any]:
    return {
        "changed_files": _string_list_fact(run_output, "changed_files"),
        "created_files": _string_list_fact(run_output, "created_files"),
        "deleted_files": _string_list_fact(run_output, "deleted_files"),
        "diff_refs": _string_list_fact(run_output, "diff_refs", "patch_refs"),
        "log_refs": _string_list_fact(run_output, "log_refs"),
        "evidence_refs": _string_list_fact(run_output, "evidence_refs"),
        "commands_run": _string_list_fact(run_output, "commands_run", "attempted_actions"),
        "checks_run": _check_records(_fact_value(run_output, "checks_run")),
        "native_event_refs": [],
    }


def _empty_runtime_facts() -> dict[str, Any]:
    return {
        "changed_files": [],
        "created_files": [],
        "deleted_files": [],
        "diff_refs": [],
        "log_refs": [],
        "evidence_refs": [],
        "commands_run": [],
        "checks_run": [],
        "native_event_refs": [],
    }


def _merge_runtime_facts(*records: dict[str, Any]) -> dict[str, Any]:
    merged = _empty_runtime_facts()
    for record in records:
        for key in merged:
            if key == "checks_run":
                merged[key] = _dedupe_checks([*merged[key], *record.get(key, [])])
            else:
                merged[key] = _dedupe([*merged[key], *record.get(key, [])])
    return merged


def _has_runtime_evidence(facts: dict[str, Any]) -> bool:
    return any(
        facts.get(key)
        for key in (
            "changed_files",
            "created_files",
            "deleted_files",
            "diff_refs",
            "log_refs",
            "evidence_refs",
            "commands_run",
            "checks_run",
        )
    )


def _extract_structured_artifact(run_output: Any, *, artifact_type: str) -> dict[str, Any] | None:
    seen: set[int] = set()
    for source in _structured_sources(run_output):
        candidate = _structured_candidate(source, artifact_type=artifact_type, seen=seen)
        if candidate is not None:
            return candidate
    return None


def _structured_sources(run_output: Any) -> list[Any]:
    sources = [run_output]
    for attr in (
        "artifact",
        "artifacts",
        "structured_output",
        "output",
        "result",
        "final_message",
        "message",
        "content",
        "summary",
    ):
        if isinstance(run_output, dict):
            if attr in run_output:
                sources.append(run_output[attr])
            continue
        value = getattr(run_output, attr, None)
        if value is not None:
            sources.append(value)
    return sources


def _structured_candidate(value: Any, *, artifact_type: str, seen: set[int]) -> dict[str, Any] | None:
    if value is None:
        return None
    value_id = id(value)
    if value_id in seen:
        return None
    seen.add(value_id)

    if isinstance(value, dict):
        artifact = _artifact_like_dict(value, artifact_type=artifact_type)
        if artifact is not None:
            return artifact
        for key in ("artifact", "structured_output", "output", "result"):
            nested = _structured_candidate(value.get(key), artifact_type=artifact_type, seen=seen)
            if nested is not None:
                return nested
        artifacts = value.get("artifacts")
        nested = _structured_candidate(artifacts, artifact_type=artifact_type, seen=seen)
        if nested is not None:
            return nested
        return None

    if isinstance(value, list):
        for item in value:
            nested = _structured_candidate(item, artifact_type=artifact_type, seen=seen)
            if nested is not None:
                return nested
        return None

    if isinstance(value, tuple):
        for item in value:
            nested = _structured_candidate(item, artifact_type=artifact_type, seen=seen)
            if nested is not None:
                return nested
        return None

    if isinstance(value, str):
        for record in _json_objects_from_text(value):
            nested = _structured_candidate(record, artifact_type=artifact_type, seen=seen)
            if nested is not None:
                return nested
    return None


def _artifact_like_dict(value: dict[str, Any], *, artifact_type: str) -> dict[str, Any] | None:
    current_type = str(value.get("artifact_type") or "").strip()
    if current_type:
        return dict(value) if current_type == artifact_type else None
    if artifact_type == "planner_order" and any(
        key in value for key in ("plan_graph", "work_items", "no_work_rationale", "no_work_reason", "no_executor_work_rationale")
    ):
        artifact = dict(value)
        artifact["artifact_type"] = "planner_order"
        return artifact
    if artifact_type == "planner_decision" and any(key in value for key in ("next_action", "task_done", "final_status")):
        artifact = dict(value)
        artifact["artifact_type"] = "planner_decision"
        return artifact
    if artifact_type == "final_report" and any(key in value for key in ("completed", "blocked_by", "failed_by", "checks")):
        artifact = dict(value)
        artifact["artifact_type"] = "final_report"
        return artifact
    if artifact_type == "project_plan_draft" and any(key in value for key in ("draft_id", "proposed_scope", "success_criteria")):
        artifact = dict(value)
        artifact["artifact_type"] = "project_plan_draft"
        return artifact
    return None


def _json_objects_from_text(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.IGNORECASE | re.DOTALL):
        parsed = _parse_json_object(match.group(1))
        if parsed is not None:
            records.append(parsed)

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _planner_order_artifact_from_structured(
    structured_artifact: dict[str, Any] | None,
    *,
    request: HarnessRunRequest,
    summary: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if structured_artifact is None:
        return None, "no structured planner_order artifact was found"

    work_items, work_item_error = _planner_order_work_items(structured_artifact)
    no_work_rationale = _no_work_rationale(structured_artifact)
    if work_items is None:
        return None, work_item_error or "planner_order work_items are invalid"
    if not work_items and not no_work_rationale:
        return None, "planner_order has no work_items and no explicit no-work rationale"

    round_goal = _string_value(structured_artifact.get("round_goal")) or no_work_rationale or summary
    artifact = {
        "artifact_type": "planner_order",
        "round": _positive_int(structured_artifact.get("round"), request.context.round or 1),
        "round_goal": round_goal or "OpenHands workflow supervisor produced a planner_order.",
        "plan_graph": {"work_items": work_items},
        "instructions_for_executor": _string_list_value(structured_artifact.get("instructions_for_executor")),
        "allowed_actions": _string_list_value(structured_artifact.get("allowed_actions")),
        "forbidden_actions": _string_list_value(structured_artifact.get("forbidden_actions")),
        "target_files_or_outputs": _string_list_value(structured_artifact.get("target_files_or_outputs")),
        "expected_outputs": _string_list_value(structured_artifact.get("expected_outputs")),
        "risk_level": _risk_level(structured_artifact.get("risk_level")),
        "requires_human_confirmation": bool(structured_artifact.get("requires_human_confirmation") or False),
        "stop_and_return_to_planner_when": _string_list_value(
            structured_artifact.get("stop_and_return_to_planner_when")
        ),
    }
    if no_work_rationale and not work_items:
        artifact["no_work_rationale"] = no_work_rationale
        artifact["instructions_for_executor"] = _dedupe(
            [*artifact["instructions_for_executor"], no_work_rationale]
        )
        artifact["expected_outputs"] = _dedupe(
            [*artifact["expected_outputs"], "No executor output is expected because no executor work is needed."]
        )
    return artifact, None


def _planner_order_work_items(structured_artifact: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    plan_graph = structured_artifact.get("plan_graph")
    if isinstance(plan_graph, dict):
        raw_items = plan_graph.get("work_items")
    else:
        raw_items = structured_artifact.get("work_items")
    if raw_items is None:
        return [], None
    if not isinstance(raw_items, list):
        return None, "planner_order work_items must be a list"

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            return None, f"work_item {index} is not an object"
        work_item_id = _string_value(item.get("work_item_id"))
        assignee_agent_id = _string_value(item.get("assignee_agent_id"))
        task_summary = _string_value(item.get("task_summary"))
        if not (work_item_id and assignee_agent_id and task_summary):
            return None, f"work_item {index} missing work_item_id, assignee_agent_id, or task_summary"
        merge_index = _positive_int(item.get("merge_index", item.get("order_index")), index)
        depends_on = _string_list_value(item.get("depends_on"))
        items.append(
            {
                "work_item_id": work_item_id,
                "merge_index": merge_index,
                "assignee_agent_id": assignee_agent_id,
                "task_summary": task_summary,
                "depends_on": depends_on,
            }
        )
    return items, None


def _no_work_rationale(value: dict[str, Any]) -> str:
    for key in ("no_work_rationale", "no_work_reason", "no_executor_work_rationale"):
        text = _string_value(value.get(key))
        if text:
            return text
    return ""


def _planner_decision_artifact_from_structured(
    structured_artifact: dict[str, Any],
    *,
    request: HarnessRunRequest,
    summary: str,
) -> dict[str, Any]:
    artifact = dict(structured_artifact)
    artifact["artifact_type"] = "planner_decision"
    artifact.setdefault("round", request.context.round or 1)
    artifact.setdefault("task_done", artifact.get("next_action") == "finish")
    artifact.setdefault("next_action", "finish")
    artifact.setdefault("risk_level", "low")
    artifact.setdefault("requires_human_confirmation", False)
    artifact.setdefault("reason", summary or "OpenHands workflow supervisor completed.")
    artifact.setdefault("next_round_goal", "")
    artifact.setdefault("remaining_auto_rounds", 0)
    artifact.setdefault("human_message", None)
    return artifact


def _final_report_artifact_from_structured(
    structured_artifact: dict[str, Any],
    *,
    summary: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    artifact = dict(structured_artifact)
    artifact["artifact_type"] = "final_report"
    artifact.setdefault("status", "completed")
    artifact.setdefault("summary", summary or "OpenHands workflow supervisor completed.")
    artifact.setdefault("checks", [])
    artifact.setdefault("completed", [artifact["summary"]] if artifact.get("status") == "completed" else [])
    artifact.setdefault("blocked_by", [])
    artifact.setdefault("failed_by", [])
    artifact.setdefault("warnings", [])
    artifact.setdefault("notes", [])
    artifact.setdefault("next_steps", [])
    artifact.setdefault("evidence_refs", evidence_refs)
    return artifact


def _project_plan_draft_from_structured(
    structured_artifact: dict[str, Any],
    *,
    request: HarnessRunRequest,
    summary: str,
) -> dict[str, Any]:
    artifact = dict(structured_artifact)
    artifact["artifact_type"] = "project_plan_draft"
    artifact.setdefault("draft_id", request.request_id)
    artifact.setdefault("summary", summary or "OpenHands produced a planning draft.")
    artifact.setdefault("proposed_scope", [])
    artifact.setdefault("success_criteria", ["Confirm the draft before execution."])
    artifact.setdefault("risks", [])
    artifact.setdefault("requires_confirmation", True)
    return artifact


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _string_list_value(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _positive_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return max(1, int(default))


def _risk_level(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"low", "medium", "high"} else "low"


def _string_list_fact(run_output: Any, *names: str) -> list[str]:
    for name in names:
        value = _fact_value(run_output, name)
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
        if isinstance(value, tuple):
            return [str(item) for item in value if str(item)]
    return []


def _fact_value(run_output: Any, name: str) -> Any:
    if isinstance(run_output, dict):
        return run_output.get(name)
    return getattr(run_output, name, None)


def _check_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            records.append(
                {
                    "check_id": f"check-{index}",
                    "kind": "command",
                    "status": "pass" if "pass" in item.lower() else "skipped",
                    "summary": item,
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        record = dict(item)
        record["status"] = _check_status(record.get("status"))
        record.setdefault("kind", "command" if record.get("command") else "model")
        record.setdefault("summary", str(record.get("command") or record.get("check_id") or f"Check {index}"))
        records.append(record)
    return records


def _check_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"pass", "passed", "success", "succeeded", "ok"}:
        return "pass"
    if status in {"fail", "failed", "failure", "error"}:
        return "fail"
    if status == "blocked":
        return "blocked"
    return "skipped"


def _has_passing_check(checks_run: list[dict[str, Any]]) -> bool:
    return any(check.get("status") == "pass" for check in checks_run)


def _dedupe_checks(values: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for record in _check_records(values):
        key = json.dumps(record, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


__all__ = ["OpenHandsRuntimeProvider"]
