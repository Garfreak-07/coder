from .budget import ContextBudget, context_compaction_enabled
from .compaction import CompactionResult, ContextCompactor
from .external_refs import ContextExternalRefStore, ExternalRef
from .harness_packets import build_harness_context_packet


def __getattr__(name: str):
    if name in {"AgentContextBuildResult", "ContextService"}:
        from .service import AgentContextBuildResult, ContextService

        return {"AgentContextBuildResult": AgentContextBuildResult, "ContextService": ContextService}[name]
    raise AttributeError(name)

__all__ = [
    "AgentContextBuildResult",
    "CompactionResult",
    "ContextBudget",
    "ContextCompactor",
    "ContextExternalRefStore",
    "ContextService",
    "ExternalRef",
    "build_harness_context_packet",
    "context_compaction_enabled",
]
