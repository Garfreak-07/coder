from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextBudget:
    max_input_tokens: int = 18_000
    max_skill_tokens: int = 4_000
    max_artifact_tokens: int = 6_000
    max_tool_result_tokens: int = 2_000

    @classmethod
    def from_data(cls, data: dict[str, Any] | None = None) -> "ContextBudget":
        values = dict(data.get("context_budget") or {}) if isinstance(data, dict) else {}
        return cls(
            max_input_tokens=_int_setting("CODER_CONTEXT_MAX_INPUT_TOKENS", values.get("max_input_tokens"), cls.max_input_tokens),
            max_skill_tokens=_int_setting("CODER_CONTEXT_MAX_SKILL_TOKENS", values.get("max_skill_tokens"), cls.max_skill_tokens),
            max_artifact_tokens=_int_setting("CODER_CONTEXT_MAX_ARTIFACT_TOKENS", values.get("max_artifact_tokens"), cls.max_artifact_tokens),
            max_tool_result_tokens=_int_setting("CODER_CONTEXT_MAX_TOOL_RESULT_TOKENS", values.get("max_tool_result_tokens"), cls.max_tool_result_tokens),
        )


def context_compaction_enabled(data: dict[str, Any] | None = None) -> bool:
    if isinstance(data, dict) and data.get("enable_context_compaction") is not None:
        return bool(data.get("enable_context_compaction"))
    return str(os.getenv("CODER_ENABLE_CONTEXT_COMPACTION") or "").strip().lower() in {"1", "true", "yes", "on"}


def _int_setting(env_name: str, value: Any, default: int) -> int:
    selected = value if value is not None else os.getenv(env_name)
    try:
        return max(0, int(selected))
    except (TypeError, ValueError):
        return default
