from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    model: str
    has_openai_key: bool


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        model=os.getenv("CODER_MODEL", "gpt-4.1-mini"),
        has_openai_key=bool(os.getenv("OPENAI_API_KEY")),
    )
