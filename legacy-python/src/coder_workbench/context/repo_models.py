from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RepoEvidenceKind = Literal[
    "repo_file_list",
    "repo_text_search",
    "repo_read",
    "repo_test",
    "repo_diff",
]


class RepoScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_root: str
    scope_paths: list[str] = Field(default_factory=list)


class RepoFileRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    normalized_path: str
    size_bytes: int | None = Field(default=None, ge=0)
    modified_at: str | None = None
    language: str | None = None


class RepoSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    line: int = Field(ge=1)
    column: int | None = Field(default=None, ge=1)
    text: str
    match: str | None = None


class RepoReadSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    text: str
    truncated: bool = False

    @model_validator(mode="after")
    def validate_line_range(self) -> "RepoReadSnippet":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class RepoEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_id: str
    kind: RepoEvidenceKind
    repo_root: str
    scope_paths: list[str] = Field(default_factory=list)
    summary: str
    payload_path: str | None = None
    created_at: str
    token_estimate: int = Field(default=0, ge=0)


__all__ = [
    "RepoEvidenceKind",
    "RepoEvidenceRef",
    "RepoFileRef",
    "RepoReadSnippet",
    "RepoScope",
    "RepoSearchHit",
]
