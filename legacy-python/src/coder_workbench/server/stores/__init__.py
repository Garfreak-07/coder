from __future__ import annotations

from pathlib import Path

from .artifacts import ArtifactStore
from .blobs import BlobStore
from .cache import CacheStore
from .contexts import ContextPacketStore
from .extensions import ExtensionStore
from .ledgers import LedgerStore
from .live_runs import LiveRunStore
from .metadata import MetadataStore
from .results import ResultStore
from .run_events import RunEventStore
from .tool_results import ToolResultStore


class PartitionedRunStores:
    """Logical store facade over the existing .coder file layout."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.metadata = MetadataStore(self.root)
        self.results = ResultStore(self.root)
        self.events = RunEventStore(self.root)
        self.artifacts = ArtifactStore(self.root)
        self.blobs = BlobStore(self.root)
        self.ledgers = LedgerStore(self.root)
        self.contexts = ContextPacketStore(self.root)
        self.tool_results = ToolResultStore(self.root)
        self.live_runs = LiveRunStore(self.root)
        self.extensions = ExtensionStore(self.root)
        self.cache = CacheStore(self.root)


__all__ = [
    "ArtifactStore",
    "BlobStore",
    "CacheStore",
    "ContextPacketStore",
    "ExtensionStore",
    "LedgerStore",
    "LiveRunStore",
    "MetadataStore",
    "PartitionedRunStores",
    "ResultStore",
    "RunEventStore",
    "ToolResultStore",
]
