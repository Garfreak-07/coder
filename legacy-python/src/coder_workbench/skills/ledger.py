from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TokenLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    round: int
    agent_id: str
    work_item_id: str
    artifact_type: str
    model: str = ""
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    skill_tokens_available: int = 0
    skill_tokens_loaded: int = 0
    memory_tokens_loaded: int = 0
    upstream_tokens_loaded: int = 0
    omitted_tokens: int = 0
    compression_ratio: float = 0.0
    repair_used: bool = False


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)
