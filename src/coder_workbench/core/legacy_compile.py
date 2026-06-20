from __future__ import annotations

from coder_workbench.core.agent_workflow import AgentWorkflowSpec, _compile_agent_workflow_legacy_impl
from coder_workbench.core.schema import WorkflowSpec


def compile_agent_workflow(spec: AgentWorkflowSpec) -> WorkflowSpec:
    """Legacy AgentWorkflow -> WorkflowSpec compiler.

    This remains for advanced runtime preview and legacy compatibility only.
    The normal AgentGraphRuntime path must call AgentGraphRunner directly.
    """

    return _compile_agent_workflow_legacy_impl(spec)
