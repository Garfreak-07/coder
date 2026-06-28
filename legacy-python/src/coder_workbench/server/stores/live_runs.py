from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from coder_workbench.server.stores._paths import safe_object_id


class LiveRunStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.live_runs_dir = self.root / "live-runs"

    def write(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        safe_id = safe_object_id(run_id)
        path = self.live_runs_dir / f"{safe_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"run_id": safe_id, "path": str(path)}

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not self.live_runs_dir.exists():
            return items
        for path in sorted(self.live_runs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return items
