from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from coder_workbench.memory.models import SECRET_MARKERS

from .repo_models import RepoEvidenceKind, RepoEvidenceRef
from .repo_safety import safe_store_segment


_KIND_PREFIX: dict[RepoEvidenceKind, str] = {
    "repo_file_list": "repo-file-list",
    "repo_text_search": "repo-text-search",
    "repo_read": "repo-read",
    "repo_test": "repo-test",
    "repo_diff": "repo-diff",
}
_MAX_STRING_CHARS = 16_000
_MAX_LIST_ITEMS = 300
_MAX_JSON_CHARS = 256_000
_EVIDENCE_SECRET_MARKERS = tuple(marker for marker in SECRET_MARKERS if marker != "token") + (
    "secret_key",
    "private_key",
)


class RepoEvidenceStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)

    def write_evidence(
        self,
        *,
        run_id: str,
        kind: str,
        repo_root: str,
        scope_paths: list[str],
        summary: str,
        payload: dict[str, Any],
    ) -> RepoEvidenceRef:
        parsed_kind = _parse_kind(kind)
        safe_run_id = safe_store_segment(run_id, label="run_id")
        evidence_dir = self.root / "runs" / safe_run_id / "repo_evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        prefix = _KIND_PREFIX[parsed_kind]
        suffix = uuid4().hex
        ref_id = f"{prefix}:{suffix}"
        payload_path = evidence_dir / f"{prefix}-{suffix}.json"
        sanitized_payload = _sanitize_payload(payload)
        payload_text = json.dumps(sanitized_payload, ensure_ascii=False, sort_keys=True, indent=2)
        if len(payload_text) > _MAX_JSON_CHARS:
            raise ValueError("repo evidence payload is too large")

        payload_path.write_text(payload_text + "\n", encoding="utf-8")
        ref = RepoEvidenceRef(
            ref_id=ref_id,
            kind=parsed_kind,
            repo_root=str(repo_root),
            scope_paths=list(scope_paths),
            summary=_compact_string(summary, limit=500),
            payload_path=str(payload_path),
            created_at=datetime.now(timezone.utc).isoformat(),
            token_estimate=_token_estimate(payload_text),
        )
        with (evidence_dir / "index.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(ref.model_dump_json(exclude_none=True) + "\n")
        return ref

    def read_evidence(self, ref_id: str) -> dict[str, Any]:
        safe_ref = safe_store_segment(ref_id, label="ref_id")
        for index_path in self.root.glob("runs/*/repo_evidence/index.jsonl"):
            for line in index_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("ref_id") != safe_ref:
                    continue
                payload_path = Path(str(record.get("payload_path") or ""))
                if not _is_relative_to(payload_path.resolve(strict=False), index_path.parent.resolve(strict=False)):
                    raise ValueError("evidence payload path escaped repo_evidence directory")
                return json.loads(payload_path.read_text(encoding="utf-8"))
        raise KeyError(ref_id)


def _parse_kind(kind: str) -> RepoEvidenceKind:
    text = str(kind)
    if text not in _KIND_PREFIX:
        raise ValueError(f"unsupported repo evidence kind {kind!r}")
    return text  # type: ignore[return-value]


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [_sanitize_payload(item) for item in value[:_MAX_LIST_ITEMS]]
        if len(value) > _MAX_LIST_ITEMS:
            items.append({"truncated": True, "omitted_items": len(value) - _MAX_LIST_ITEMS})
        return items
    if isinstance(value, tuple):
        return _sanitize_payload(list(value))
    if isinstance(value, str):
        _reject_secret_like_text(value)
        return _compact_string(value, limit=_MAX_STRING_CHARS)
    return value


def _compact_string(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _reject_secret_like_text(value: str) -> None:
    lowered = value.lower()
    for marker in _EVIDENCE_SECRET_MARKERS:
        if marker in lowered:
            raise ValueError("repo evidence payload contains secret-like text")


def _token_estimate(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = ["RepoEvidenceStore"]
