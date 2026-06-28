from __future__ import annotations

import difflib
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import HarnessContract
from .profiles import HarnessRuntimeProfile
from .runtime_context import HarnessRuntimeContext


WorkspaceMode = Literal["none", "readonly", "temp_worktree", "docker", "remote_workspace"]


class SandboxPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_mode: WorkspaceMode = "none"
    command_timeout_seconds: int = 120
    allowed_scopes: list[str] = Field(default_factory=list)
    enforce_scope_restrictions: bool = True
    collect_diff_refs: bool = True
    collect_log_refs: bool = True


class SandboxPreparationError(ValueError):
    """Raised when a harness request cannot obtain its required workspace."""


@dataclass(frozen=True)
class PreparedSandboxWorkspace:
    path: Path
    workspace_mode: WorkspaceMode
    source_repo: Path | None = None
    temporary: bool = False
    baseline: dict[str, bytes] | None = None


def sandbox_policy_for_profile(profile: HarnessRuntimeProfile) -> SandboxPolicy:
    raw = dict(profile.sandbox_policy)
    workspace = raw.pop("workspace", raw.pop("workspace_mode", None))
    if workspace is not None:
        raw["workspace_mode"] = workspace
    return SandboxPolicy(**raw)


def enforce_sandbox_policy(contract: HarnessContract, profile: HarnessRuntimeProfile) -> None:
    policy = sandbox_policy_for_profile(profile)
    if contract.role == "planner" and policy.workspace_mode not in {"none", "readonly"}:
        raise ValueError("Conversation Harness workspace must be none or readonly.")
    if contract.role == "executor" and policy.workspace_mode != "temp_worktree":
        raise ValueError("Task Execution Harness requires temp_worktree isolated workspace.")


@contextmanager
def prepare_sandbox_workspace(
    *,
    contract: HarnessContract,
    profile: HarnessRuntimeProfile,
    context: HarnessRuntimeContext,
) -> PreparedSandboxWorkspace:
    policy = sandbox_policy_for_profile(profile)
    if contract.role == "planner":
        path = _readonly_workspace_path(context)
        yield PreparedSandboxWorkspace(path=path, workspace_mode=policy.workspace_mode)
        return

    if policy.workspace_mode != "temp_worktree":
        raise SandboxPreparationError("Task Execution Harness requires temp_worktree isolated workspace.")

    sandbox_root = _resolved_optional_path(context.sandbox_root)
    repo_root = _resolved_repo_root(context, required=sandbox_root is None)
    if sandbox_root is not None:
        if repo_root is not None and _same_path(sandbox_root, repo_root):
            raise SandboxPreparationError("Task Execution Harness sandbox_root must not be the source repo root.")
        sandbox_root.mkdir(parents=True, exist_ok=True)
        yield PreparedSandboxWorkspace(
            path=sandbox_root,
            workspace_mode="temp_worktree",
            source_repo=repo_root,
            temporary=False,
            baseline=_snapshot_tree(sandbox_root),
        )
        return

    if repo_root is None:
        raise SandboxPreparationError("Task Execution Harness requires repo_root to create temp_worktree.")

    temp_dir = tempfile.TemporaryDirectory(prefix="coder-openhands-")
    workspace = Path(temp_dir.name) / "workspace"
    try:
        _copy_repo_to_workspace(repo_root, workspace, scopes=_active_scopes(policy, context))
        yield PreparedSandboxWorkspace(
            path=workspace,
            workspace_mode="temp_worktree",
            source_repo=repo_root,
            temporary=True,
            baseline=_snapshot_tree(workspace),
        )
    finally:
        temp_dir.cleanup()


def collect_workspace_changes(prepared: PreparedSandboxWorkspace) -> dict[str, object]:
    baseline = prepared.baseline or {}
    current = _snapshot_tree(prepared.path)
    before_paths = set(baseline)
    after_paths = set(current)
    created = sorted(after_paths - before_paths)
    deleted = sorted(before_paths - after_paths)
    changed = sorted(
        path
        for path in before_paths & after_paths
        if baseline[path] != current[path]
    )
    return {
        "changed_files": changed,
        "created_files": created,
        "deleted_files": deleted,
        "diff": _diff_snapshot(baseline, current, changed=changed, created=created, deleted=deleted),
    }


def _readonly_workspace_path(context: HarnessRuntimeContext) -> Path:
    if context.sandbox_root:
        return Path(context.sandbox_root).resolve()
    if context.repo_root:
        return Path(context.repo_root).resolve()
    return Path(".").resolve()


def _resolved_repo_root(context: HarnessRuntimeContext, *, required: bool) -> Path | None:
    if not context.repo_root:
        return None
    path = Path(context.repo_root).resolve()
    if not path.exists() or not path.is_dir():
        if not required:
            return None
        raise SandboxPreparationError(f"repo_root does not exist: {context.repo_root}")
    return path


def _resolved_optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).resolve()


def _same_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except OSError:
        return str(first) == str(second)


def _copy_repo_to_workspace(repo_root: Path, workspace: Path, *, scopes: list[str]) -> None:
    if not scopes:
        shutil.copytree(repo_root, workspace, ignore=_copy_ignore())
        return
    workspace.mkdir(parents=True, exist_ok=True)
    for scope in scopes:
        source = (repo_root / scope).resolve()
        if not _is_relative_to(source, repo_root):
            raise SandboxPreparationError(f"Scope escapes repo root: {scope}")
        if not source.exists():
            raise SandboxPreparationError(f"Scope does not exist: {scope}")
        target = workspace / scope
        if source.is_dir():
            shutil.copytree(source, target, ignore=_copy_ignore())
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _copy_ignore() -> object:
    return shutil.ignore_patterns(
        ".git",
        ".venv",
        "__pycache__",
        "*.pyc",
        ".mypy_cache",
        ".pytest_cache",
        "outputs-test",
    )


def _active_scopes(policy: SandboxPolicy, context: HarnessRuntimeContext) -> list[str]:
    if policy.allowed_scopes:
        return [scope for scope in policy.allowed_scopes if scope.strip()]
    value = context.initial_data.get("scopes") or context.initial_data.get("scope")
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    if not root.exists():
        return snapshot
    for path in sorted(root.rglob("*")):
        if not path.is_file() or _ignored_snapshot_path(path, root):
            continue
        try:
            snapshot[_relative_posix(path, root)] = path.read_bytes()
        except OSError:
            continue
    return snapshot


def _ignored_snapshot_path(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return any(part in {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"} for part in rel_parts)


def _diff_snapshot(
    before: dict[str, bytes],
    after: dict[str, bytes],
    *,
    changed: list[str],
    created: list[str],
    deleted: list[str],
) -> str:
    chunks: list[str] = []
    for path in [*changed, *created, *deleted]:
        before_text = _decode_text(before.get(path, b""))
        after_text = _decode_text(after.get(path, b""))
        if before_text is None or after_text is None:
            chunks.append(f"Binary file changed: {path}\n")
            continue
        chunks.extend(
            difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
    return "".join(chunks)


def _decode_text(value: bytes) -> str | None:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


__all__ = [
    "PreparedSandboxWorkspace",
    "SandboxPolicy",
    "SandboxPreparationError",
    "WorkspaceMode",
    "collect_workspace_changes",
    "enforce_sandbox_policy",
    "prepare_sandbox_workspace",
    "sandbox_policy_for_profile",
]
