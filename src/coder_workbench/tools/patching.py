from __future__ import annotations

import difflib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from coder_workbench.tools.filesystem import resolve_scoped_path


PATCH_ACTIONS = {"create", "update", "delete"}


def propose_patch(args: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(runtime_context["repo_root"]).resolve()
    scopes = _list_value(runtime_context.get("scopes"))
    changes = _normalize_changes(args.get("changes") or args.get("files") or args)
    previews: list[dict[str, Any]] = []

    for change in changes:
        path = _change_path(change)
        action = _change_action(change)
        content = change.get("content")
        target = resolve_scoped_path(repo_root, path, scopes)
        current = _read_text_if_exists(target)

        if action == "create" and target.exists():
            action = "update"
        if action == "update" and current is None:
            action = "create"
        if action == "delete":
            next_content = None
        else:
            next_content = "" if content is None else str(content)

        previews.append(
            {
                "path": target.relative_to(repo_root).as_posix(),
                "action": action,
                "exists": target.exists(),
                "diff": _unified_diff(
                    path=target.relative_to(repo_root).as_posix(),
                    before=current,
                    after=next_content,
                ),
                "content": next_content,
            }
        )

    return {
        "status": "proposed",
        "patch_id": str(uuid4()),
        "requires_approval": True,
        "change_count": len(previews),
        "files": previews,
    }


def apply_patch(args: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    if not _is_approved(args, runtime_context):
        return {
            "status": "blocked",
            "blocked": True,
            "requires_approval": True,
            "message": "Patch apply requires explicit patch approval.",
        }

    repo_root = Path(runtime_context["repo_root"]).resolve()
    scopes = _list_value(runtime_context.get("scopes"))
    patch = args.get("patch") or runtime_context.get("data", {}).get(str(args.get("patch_key") or "patch_preview")) or args
    files = _patch_files(patch)
    snapshot_id = str(uuid4())
    snapshot_root = repo_root / ".coder_history" / "snapshots" / snapshot_id
    snapshot_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": [],
    }
    applied: list[dict[str, Any]] = []

    for item in files:
        path = _change_path(item)
        action = _change_action(item)
        target = resolve_scoped_path(repo_root, path, scopes)
        relative = target.relative_to(repo_root).as_posix()
        snapshot_file = snapshot_root / "files" / relative
        existed = target.exists()

        manifest["files"].append(
            {
                "path": relative,
                "existed": existed,
                "snapshot_path": f"files/{relative}" if existed else None,
            }
        )
        if existed:
            snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, snapshot_file)

        if action == "delete":
            if target.exists():
                target.unlink()
        else:
            content = item.get("content")
            if content is None:
                raise ValueError(f"Patch item for {relative} is missing content")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")

        applied.append({"path": relative, "action": action})

    (snapshot_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "status": "applied",
        "snapshot_id": snapshot_id,
        "applied": applied,
        "message": f"Applied {len(applied)} file change(s).",
    }


def rollback_patch(args: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(runtime_context["repo_root"]).resolve()
    snapshot_id = str(args.get("snapshot_id") or "").strip()
    if not snapshot_id:
        patch_result = args.get("patch_result") or runtime_context.get("data", {}).get("patch_apply")
        if isinstance(patch_result, dict):
            snapshot_id = str(patch_result.get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise ValueError("snapshot_id is required for rollback")

    snapshot_root = (repo_root / ".coder_history" / "snapshots" / snapshot_id).resolve()
    expected_root = (repo_root / ".coder_history" / "snapshots").resolve()
    if not str(snapshot_root).startswith(str(expected_root)):
        raise ValueError("Invalid snapshot_id")

    manifest_path = snapshot_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[dict[str, Any]] = []

    for item in manifest.get("files", []):
        relative = str(item["path"])
        target = resolve_scoped_path(repo_root, relative, _list_value(runtime_context.get("scopes")))
        if item.get("existed"):
            source = snapshot_root / str(item["snapshot_path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored.append({"path": relative, "action": "restored"})
        elif target.exists():
            target.unlink()
            restored.append({"path": relative, "action": "removed"})
        else:
            restored.append({"path": relative, "action": "unchanged"})

    return {
        "status": "rolled_back",
        "snapshot_id": snapshot_id,
        "restored": restored,
        "message": f"Rolled back {len(restored)} file change(s).",
    }


def _normalize_changes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("changes", "files", "patches"):
            if isinstance(value.get(key), list):
                return [dict(item) for item in value[key] if isinstance(item, dict)]
        if "path" in value:
            return [dict(value)]
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _patch_files(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("files"), list):
        return [dict(item) for item in value["files"] if isinstance(item, dict)]
    return _normalize_changes(value)


def _change_path(change: dict[str, Any]) -> str:
    path = str(change.get("path") or change.get("file") or "").strip()
    if not path:
        raise ValueError("Patch change requires path")
    return path


def _change_action(change: dict[str, Any]) -> str:
    action = str(change.get("action") or "update").strip().lower()
    if action not in PATCH_ACTIONS:
        raise ValueError(f"Unsupported patch action: {action}")
    return action


def _read_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise IsADirectoryError(f"Patch target is not a file: {path}")
    return path.read_text(encoding="utf-8")


def _unified_diff(path: str, before: str | None, after: str | None) -> str:
    before_lines = [] if before is None else before.splitlines(keepends=True)
    after_lines = [] if after is None else after.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )


def _is_approved(args: dict[str, Any], runtime_context: dict[str, Any]) -> bool:
    data = runtime_context.get("data", {})
    patch_approval = data.get("patch_approval", {})
    return bool(
        args.get("approved")
        or args.get("patch_approved")
        or data.get("patch_approved")
        or data.get("preapprove_all")
        or (isinstance(patch_approval, dict) and patch_approval.get("approved"))
    )


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
