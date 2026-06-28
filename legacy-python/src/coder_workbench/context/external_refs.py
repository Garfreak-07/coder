from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExternalRef:
    ref: str
    blob_id: str
    ref_type: str
    path: str
    original_chars: int
    preview: str


class ContextExternalRefStore:
    """Compatibility shim for tests and old callers.

    New durable context references are BlobStore-compatible ``sha256:<digest>``
    ids. This shim may keep full text in memory for immediate reads, but it no
    longer creates ``context:<run_id>:...`` references.
    """

    def __init__(self, backing: dict[str, Any] | None = None) -> None:
        self.backing = backing if backing is not None else {}

    def write(
        self,
        *,
        run_id: str,
        work_item_id: str,
        path: list[str],
        value: str,
        ref_type: str = "context",
        preview_chars: int = 600,
    ) -> ExternalRef:
        path_key = ".".join(path) or "packet"
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        blob_id = f"sha256:{digest}"
        preview = preview_text(value, preview_chars)
        self.backing[blob_id] = {
            "ref": blob_id,
            "blob_id": blob_id,
            "ref_type": ref_type,
            "run_id": run_id,
            "work_item_id": work_item_id,
            "field_path": path_key,
            "content": value,
            "original_chars": len(value),
            "preview": preview,
            "media_type": "text/plain; charset=utf-8",
        }
        return ExternalRef(
            ref=blob_id,
            blob_id=blob_id,
            ref_type=ref_type,
            path=path_key,
            original_chars=len(value),
            preview=preview,
        )

    def read(self, ref: str) -> dict[str, Any]:
        value = self.backing[ref]
        if not isinstance(value, dict):
            raise KeyError(ref)
        return value


def preview_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    head = max(1, limit // 2)
    tail = max(1, limit - head)
    return f"{value[:head]}\n...<truncated>...\n{value[-tail:]}"
