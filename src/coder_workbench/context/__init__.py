from .budget import ContextBudget, context_compaction_enabled
from .compaction import CompactionResult, ContextCompactor
from .external_refs import ContextExternalRefStore, ExternalRef
from .harness_packets import build_harness_context_packet
from .repo_context_service import NativeRepoContextService
from .repo_discovery import RepoFileDiscoveryService
from .repo_evidence import RepoEvidenceStore
from .repo_models import RepoEvidenceRef, RepoFileRef, RepoReadSnippet, RepoScope, RepoSearchHit
from .repo_read import RepoReadService
from .repo_search import RepoTextSearchService


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
    "NativeRepoContextService",
    "build_harness_context_packet",
    "context_compaction_enabled",
    "RepoEvidenceRef",
    "RepoEvidenceStore",
    "RepoFileDiscoveryService",
    "RepoFileRef",
    "RepoReadService",
    "RepoReadSnippet",
    "RepoScope",
    "RepoSearchHit",
    "RepoTextSearchService",
]
