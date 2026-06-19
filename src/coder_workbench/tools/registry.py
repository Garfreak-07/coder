from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from coder_workbench.module_map import build_module_map
from coder_workbench.project_index import annotate_recommendations, recommend_modules
from coder_workbench.tools.filesystem import resolve_scoped_path, summarize_project


ToolFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolFn] = {}

    def register(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    def run(self, name: str, args: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return self._tools[name](args, runtime_context)

    def names(self) -> list[str]:
        return sorted(self._tools)


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("project_index", _project_index)
    registry.register("recommend_modules", _recommend_modules)
    registry.register("dry_run_patch", _dry_run_patch)
    registry.register("run_check", _run_check)
    return registry


def _project_index(args: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(runtime_context["repo_root"]).resolve()
    scope = _list_value(args.get("scope")) or _list_value(runtime_context.get("scopes"))
    files = summarize_project(repo_root, scope, max_files=int(args.get("max_files", 800)))
    modules = build_module_map(files)
    return {"files": files, "modules": modules, "file_count": len(files), "scopes": scope}


def _recommend_modules(args: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or runtime_context.get("request") or "")
    files = args.get("files") or runtime_context.get("data", {}).get("project_index", {}).get("files", [])
    modules = args.get("modules") or runtime_context.get("data", {}).get("project_index", {}).get("modules", [])
    recommendations = recommend_modules(query, modules, files) if query else []
    annotated = annotate_recommendations(modules, recommendations) if recommendations else modules
    return {"query": query, "recommendations": recommendations, "modules": annotated}


def _dry_run_patch(args: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "dry_run",
        "message": "Patch generation is intentionally disabled until patch approval and rollback are implemented.",
        "requested_changes": args.get("changes", []),
    }


def _run_check(args: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command") or "").strip()
    if not command:
        return {"passed": True, "output": "No check command configured.", "skipped": True}
    if not bool(args.get("approved", False)):
        return {
            "passed": False,
            "output": f"Check command requires explicit approval: {command}",
            "blocked": True,
        }
    repo_root = Path(runtime_context["repo_root"]).resolve()
    scopes = _list_value(runtime_context.get("scopes"))
    default_cwd = scopes[0] if scopes else "."
    cwd = resolve_scoped_path(repo_root, str(args.get("cwd") or default_cwd), scopes)
    completed = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
        timeout=int(args.get("timeout_seconds", 120)),
    )
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "cwd": cwd.relative_to(repo_root).as_posix() if cwd != repo_root else ".",
        "output": (completed.stdout + completed.stderr)[-8000:],
    }


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
