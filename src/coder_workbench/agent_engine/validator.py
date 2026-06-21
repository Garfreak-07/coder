from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .schema import AgentEngineSpec, HarnessBlock


class HarnessValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    block_id: str | None = None


class HarnessValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    issues: list[HarnessValidationIssue] = Field(default_factory=list)


class HarnessValidator:
    def validate(self, spec: AgentEngineSpec) -> HarnessValidationResult:
        issues: list[HarnessValidationIssue] = []
        block_types = {block.type for block in spec.harness_graph.nodes}
        for required in ("context_builder", "artifact_validator", "output_artifact"):
            if required not in block_types:
                issues.append(_issue("missing_required_block", f"Agent engine must include {required}."))
        if spec.token_budget.max_input_tokens <= 0:
            issues.append(_issue("token_budget_required", "Agent engine token budget must be positive."))

        for block in spec.harness_graph.nodes:
            issues.extend(_block_issues(spec, block))

        return HarnessValidationResult(valid=not issues, issues=issues)


def _block_issues(spec: AgentEngineSpec, block: HarnessBlock) -> list[HarnessValidationIssue]:
    issues: list[HarnessValidationIssue] = []
    if block.type == "model_loop" and not block.config.get("max_steps"):
        issues.append(_issue("loop_requires_max_steps", "Model loops require max_steps.", block.id))
    if spec.engine_type in {"worker", "tester", "final_tester"} and _block_asks_human(block):
        issues.append(_issue("non_planner_ask_human", "Only planner engines can ask the human.", block.id))
    if spec.engine_type == "tester" and _block_writes_files(block):
        issues.append(_issue("tester_cannot_write_files", "Tester engines cannot write files.", block.id))
    if _external_effect(block) and not block.config.get("requires_preview"):
        issues.append(_issue("external_effect_requires_preview", "External effects require preview metadata.", block.id))
    if _plugin_operation(block) and not block.config.get("permission_metadata"):
        issues.append(_issue("plugin_operation_requires_permission_metadata", "Plugin operations require permission metadata.", block.id))
    return issues


def _block_asks_human(block: HarnessBlock) -> bool:
    return block.type == "interrupt_gate" and bool(block.config.get("ask_human") or block.config.get("can_ask_human"))


def _block_writes_files(block: HarnessBlock) -> bool:
    return block.type in {"patch_preview", "sandbox_check"} and bool(
        block.config.get("can_write_files") or block.config.get("operation") == "patch_apply"
    )


def _external_effect(block: HarnessBlock) -> bool:
    return bool(block.config.get("external_effect")) or block.type in {"patch_preview", "sandbox_check", "tool_gate"}


def _plugin_operation(block: HarnessBlock) -> bool:
    return block.type == "tool_gate" and bool(block.config.get("plugin_operation"))


def _issue(code: str, message: str, block_id: str | None = None) -> HarnessValidationIssue:
    return HarnessValidationIssue(code=code, message=message, block_id=block_id)
