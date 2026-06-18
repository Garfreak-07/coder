from __future__ import annotations

from typing import Literal, TypedDict


class FileSummary(TypedDict):
    path: str
    size_bytes: int
    kind: str


class CodingState(TypedDict, total=False):
    user_request: str

    repo_root: str
    reference_roots: list[str]
    target_scope: list[str]
    allowed_paths: list[str]

    repo_files: list[FileSummary]
    reference_files: dict[str, list[FileSummary]]

    plan: str
    approval_required: bool
    approved: bool

    proposed_changes: list[str]
    changed_files: list[str]

    check_command: str
    check_output: str
    check_passed: bool

    review_notes: str
    risk_level: Literal["low", "medium", "high"]

    iteration: int
    max_iterations: int
    status: Literal["created", "planned", "approved", "executed", "checked", "done", "blocked"]
    next_step: Literal["execute", "retry", "done", "blocked"]
