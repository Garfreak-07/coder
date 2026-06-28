from __future__ import annotations

import json
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.agent_harness.contracts import harness_contract_for_id


class PromptLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer_id: str
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def render(self) -> str:
        return f"{self.title}:\n{self.content}"


def output_contract_layer(*, artifact_type: str, schema_notes: str) -> PromptLayer:
    return PromptLayer(
        layer_id="output_contract",
        title="Output Contract",
        content=(
            "Return JSON only. Do not include markdown, commentary, transcript, or code fences.\n"
            f"The JSON object must have artifact_type={artifact_type!r}.\n"
            f"{schema_notes}"
        ),
        metadata={"artifact_type": artifact_type},
    )


def instruction_layer(*, layer_id: str, title: str, instructions: Iterable[str]) -> PromptLayer:
    return PromptLayer(
        layer_id=layer_id,
        title=title,
        content="\n".join(str(item).strip() for item in instructions if str(item).strip()),
    )


def harness_contract_layer(harness_id: str) -> PromptLayer:
    contract = harness_contract_for_id(harness_id)
    return PromptLayer(
        layer_id="harness_contract",
        title="Harness Contract JSON",
        content=_compact_json(contract.model_dump(mode="json")),
        metadata={"harness_id": harness_id},
    )


def text_layer(*, layer_id: str, title: str, content: Any) -> PromptLayer:
    return PromptLayer(layer_id=layer_id, title=title, content=str(content))


def json_layer(*, layer_id: str, title: str, value: Any, max_chars: int = 8000) -> PromptLayer:
    return PromptLayer(
        layer_id=layer_id,
        title=title,
        content=_compact_json(value, max_chars=max_chars),
    )


def render_prompt_layers(layers: Iterable[PromptLayer | None]) -> str:
    return "\n\n".join(layer.render() for layer in layers if layer is not None)


def default_prompt_layer_config(role: str) -> dict[str, Any]:
    if role == "planner":
        return {
            "schema_version": "prompt-layers/v1",
            "layer_order": [
                "output_contract",
                "planner_rules",
                "harness_contract",
                "task_context",
                "state_view",
                "capability_set",
                "memory_context",
            ],
            "max_layer_chars": 8000,
        }
    return {
        "schema_version": "prompt-layers/v1",
        "layer_order": [
            "output_contract",
            "executor_rules",
            "harness_contract",
            "agent_context",
            "work_item",
            "task_envelope",
            "coding_context",
            "capability_set",
            "skill_context",
        ],
        "max_layer_chars": 8000,
    }


def _compact_json(value: Any, *, max_chars: int = 8000) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)[:max_chars]
