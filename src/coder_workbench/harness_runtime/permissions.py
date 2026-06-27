from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


HarnessPermissionCode = Literal[
    "allowed",
    "planner_read_only_violation",
    "executor_outside_sandbox",
    "sensitive_path_denied",
    "dangerous_command_denied",
    "commit_push_deploy_denied",
    "user_interaction_denied",
    "long_term_memory_denied",
    "tool_denied",
]


class HarnessPermissionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    requires_confirmation: bool = False
    reason: str = ""
    code: HarnessPermissionCode = "allowed"


_PLANNER_MODES = {"planning_chat", "workflow_supervisor"}
_PLANNER_DENIED_ACTIONS = {"write_file", "apply_patch", "run_command", "run_test"}
_PLANNER_DENIED_TOOLS = {"terminal", "file_editor"}
_EXECUTOR_ALLOWED_TOOLS = {"terminal", "file_editor", "task_tracker", "coder_hybrid_rag_search"}
_LONG_TERM_MEMORY_ACTIONS = {"write_memory", "write_long_term_memory", "long_term_memory_write", "memory_write"}
_USER_INTERACTION_TOOLS = {"ask_human", "browser", "user_input"}


def evaluate_harness_permission(
    *,
    mode: str,
    harness_id: str,
    role: str | None = None,
    tool_name: str | None = None,
    action_type: str | None = None,
    file_path: str | None = None,
    command: str | None = None,
    sandbox_root: str | None = None,
) -> HarnessPermissionDecision:
    action = _normalized(action_type)
    tool = _normalized(tool_name)
    effective_role = _normalized(role) or ("planner" if mode in _PLANNER_MODES else "executor")

    if effective_role == "planner" or mode in _PLANNER_MODES:
        if action in _PLANNER_DENIED_ACTIONS or tool in _PLANNER_DENIED_TOOLS:
            return _deny("planner_read_only_violation", "Conversation Harness is read-only.")

    if action in _LONG_TERM_MEMORY_ACTIONS or tool == "long_term_memory":
        return _deny("long_term_memory_denied", "Harnesses cannot write long-term memory directly.")

    if tool in _USER_INTERACTION_TOOLS:
        return _deny("user_interaction_denied", "Harness tool call would require user interaction.")

    if mode == "task_execution" or effective_role == "executor":
        if tool and tool not in _EXECUTOR_ALLOWED_TOOLS:
            return _deny("tool_denied", f"Tool {tool_name!r} is not allowed for Task Execution Harness.")
        if file_path:
            path_decision = _evaluate_executor_path(file_path=file_path, sandbox_root=sandbox_root)
            if not path_decision.allowed:
                return path_decision
        if command:
            command_decision = _evaluate_command(command)
            if not command_decision.allowed:
                return command_decision

    return HarnessPermissionDecision(allowed=True, reason="Allowed by harness permission policy.")


def _evaluate_executor_path(*, file_path: str, sandbox_root: str | None) -> HarnessPermissionDecision:
    sandbox = _resolved_path(sandbox_root) if sandbox_root else None
    candidate = Path(file_path)
    if sandbox is not None and not candidate.is_absolute():
        candidate = sandbox / candidate
    resolved = _resolved_path(candidate)

    if sandbox is None or not _is_relative_to(resolved, sandbox):
        return _deny("executor_outside_sandbox", "Task Execution Harness file access must stay inside sandbox_root.")
    if _is_sensitive_path(resolved, sandbox):
        return _deny("sensitive_path_denied", "Path matches a sensitive credential or local secret policy.")
    return HarnessPermissionDecision(allowed=True, reason="Path is inside sandbox and not sensitive.")


def _evaluate_command(command: str) -> HarnessPermissionDecision:
    text = _command_text(command)
    if _is_commit_push_deploy_command(text):
        return _deny("commit_push_deploy_denied", "Command attempts commit, push, deploy, or external publish.")
    if _is_interactive_command(text):
        return _deny("user_interaction_denied", "Command is interactive or opens an editor/pager.")
    if _is_dangerous_command(text):
        return _deny("dangerous_command_denied", "Command is dangerous for harness execution.")
    return HarnessPermissionDecision(allowed=True, reason="Command is allowed by harness permission policy.")


def _is_commit_push_deploy_command(text: str) -> bool:
    patterns = (
        r"\bgit\s+(commit|push|tag)\b",
        r"\bgh\s+release\b",
        r"\bnpm\s+publish\b",
        r"\bpnpm\s+publish\b",
        r"\byarn\s+publish\b",
        r"\btwine\s+upload\b",
        r"\bdocker\s+push\b",
        r"\bkubectl\s+(apply|delete)\b",
        r"\bterraform\s+(apply|destroy)\b",
        r"\bvercel\s+deploy\b(?=.*\s--prod\b)",
        r"\bnetlify\s+deploy\b(?=.*\s--prod\b)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _is_interactive_command(text: str) -> bool:
    return bool(
        re.search(r"(^|[;&|]\s*)(vim|vi|nano|emacs|less|more)(\s|$)", text)
        or re.search(r"\bread\s+-p\b", text)
        or re.search(r"(^|[;&|]\s*)pause(\s|$)", text)
    )


def _is_dangerous_command(text: str) -> bool:
    return bool(
        re.search(r"\brm\s+-[a-z]*r[a-z]*f[a-z]*\s+/(?:\s|$)", text)
        or re.search(r"\brm\s+-[a-z]*f[a-z]*r[a-z]*\s+/(?:\s|$)", text)
        or re.search(r"\bformat\s+c:", text)
        or re.search(r"\bshutdown\b", text)
        or re.search(r"\breboot\b", text)
    )


def _is_sensitive_path(path: Path, sandbox_root: Path) -> bool:
    try:
        parts = [part.lower() for part in path.relative_to(sandbox_root).parts]
    except ValueError:
        parts = [part.lower() for part in path.parts]
    name = parts[-1] if parts else ""

    if name in {".env", ".local-env.ps1", "id_rsa", "id_ed25519"} or name.startswith(".env."):
        return True
    if any(part in {".ssh", ".azure", ".gnupg"} for part in parts):
        return True
    if _has_suffix(parts, [".aws", "credentials"]) or _has_suffix(parts, [".aws", "config"]):
        return True
    if _has_suffix(parts, [".config", "gcloud"]) or ".config" in parts and "gcloud" in parts:
        return True
    if _has_suffix(parts, [".docker", "config.json"]):
        return True
    if _has_suffix(parts, [".kube", "config"]):
        return True
    if _has_suffix(parts, [".openharness", "credentials.json"]):
        return True
    return _has_suffix(parts, [".openharness", "copilot_auth.json"])


def _has_suffix(parts: list[str], suffix: list[str]) -> bool:
    if len(parts) < len(suffix):
        return False
    return parts[-len(suffix) :] == suffix


def _resolved_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _command_text(command: str) -> str:
    return " ".join(command.strip().lower().split())


def _normalized(value: str | None) -> str:
    return str(value or "").strip().lower()


def _deny(code: HarnessPermissionCode, reason: str) -> HarnessPermissionDecision:
    return HarnessPermissionDecision(allowed=False, code=code, reason=reason)


__all__ = [
    "HarnessPermissionCode",
    "HarnessPermissionDecision",
    "evaluate_harness_permission",
]
