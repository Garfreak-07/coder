from .budget import ContextBudget, context_compaction_enabled
from .compaction import CompactionResult, ContextCompactor
from .evidence_policy import EvidenceKind, KnowledgeHint
from .external_refs import ContextExternalRefStore, ExternalRef
from .harness_packets import build_harness_context_packet
from .agentic_router import AgenticContextRouter
from .repo_context_service import NativeRepoContextService
from .repo_discovery import RepoFileDiscoveryService
from .repo_evidence import RepoEvidenceStore
from .repo_models import RepoEvidenceRef, RepoFileRef, RepoReadSnippet, RepoScope, RepoSearchHit
from .repo_read import RepoReadService
from .repo_search import RepoTextSearchService
from .retrieval_router import ContextRetrievalDecision, ContextRetrievalRouter, RetrievalIntent
from .router_models import AgenticContextRouterState, RouterRoleProfile, RouterSource
from .router_profiles import router_profile_for_mode


def __getattr__(name: str):
    if name in {"AgentContextBuildResult", "ContextService"}:
        from .service import AgentContextBuildResult, ContextService

        return {"AgentContextBuildResult": AgentContextBuildResult, "ContextService": ContextService}[name]
    raise AttributeError(name)

__all__ = [
    "AgentContextBuildResult",
    "AgenticContextRouter",
    "AgenticContextRouterState",
    "CompactionResult",
    "ContextBudget",
    "ContextCompactor",
    "ContextRetrievalDecision",
    "ContextRetrievalRouter",
    "EvidenceKind",
    "ContextExternalRefStore",
    "ContextService",
    "ExternalRef",
    "KnowledgeHint",
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
    "RetrievalIntent",
    "RouterRoleProfile",
    "RouterSource",
    "router_profile_for_mode",
]
