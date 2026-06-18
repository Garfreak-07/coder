from __future__ import annotations

import subprocess
from pathlib import Path


def run_check(command: str, cwd: Path, timeout_seconds: int = 120) -> tuple[bool, str]:
    if not command.strip():
        return True, "No check command provided; skipped."

    completed = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    output = "\n".join(
        part
        for part in [completed.stdout.strip(), completed.stderr.strip()]
        if part
    )
    return completed.returncode == 0, output or f"Command exited with code {completed.returncode}."
