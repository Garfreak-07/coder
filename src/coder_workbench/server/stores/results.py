from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from coder_workbench.server.stores._paths import run_dir


class ResultStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def write(self, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
        path = run_dir(self.root, run_id) / "result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"run_id": run_id, "path": str(path)}

    def read(self, run_id: str) -> dict[str, Any]:
        path = run_dir(self.root, run_id) / "result.json"
        if not path.exists():
            raise KeyError(run_id)
        return json.loads(path.read_text(encoding="utf-8"))
