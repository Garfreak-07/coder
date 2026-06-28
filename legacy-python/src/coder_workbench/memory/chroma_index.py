from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from coder_workbench.memory.embeddings import EmbeddingProvider, HashingEmbeddingProvider
from coder_workbench.memory.models import KnowledgeChunk

try:  # pragma: no cover - exercised only when optional dependency is installed.
    import chromadb
except ImportError:  # pragma: no cover - current base environment intentionally lacks it.
    chromadb = None


class DenseSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rank: int
    score: float
    distance: float | None = None


class ChromaVectorIndex:
    def __init__(
        self,
        root: str | Path,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        collection_name: str = "coder_knowledge_chunks",
    ) -> None:
        self.root = _chroma_root(root)
        self.embedding_provider = embedding_provider or HashingEmbeddingProvider()
        self.collection_name = collection_name
        self._client: Any | None = None
        self._collection: Any | None = None
        self._local_collection: _LocalVectorCollection | None = None

    @classmethod
    def is_available(cls) -> bool:
        return chromadb is not None

    def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        if not self.is_available():
            raise RuntimeError("chromadb is not installed")
        documents: list[str] = []
        ids: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for chunk in chunks:
            if chunk.sensitivity == "secret" or chunk.acl.sensitivity == "secret":
                continue
            ids.append(chunk.chunk_id)
            documents.append(_chunk_document_text(chunk))
            metadatas.append(_chunk_metadata(chunk, self.embedding_provider.id))
        if not ids:
            return
        embeddings = self.embedding_provider.embed_documents(documents)
        self._get_collection().upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(self, query: str, *, top_k: int, where: dict[str, Any] | None = None) -> list[DenseSearchHit]:
        if not self.is_available() or top_k <= 0:
            return []
        query_embedding = self.embedding_provider.embed_query(query)
        results = self._get_collection().query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["distances", "metadatas"],
        )
        ids = (results.get("ids") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        hits: list[DenseSearchHit] = []
        for index, item_id in enumerate(ids, start=1):
            distance = float(distances[index - 1]) if index - 1 < len(distances) else None
            hits.append(
                DenseSearchHit(
                    id=str(item_id),
                    rank=index,
                    score=round(_distance_to_score(distance), 6),
                    distance=distance,
                )
            )
        return hits

    def _get_collection(self) -> Any:
        if not self.is_available():
            raise RuntimeError("chromadb is not installed")
        if self._collection is None:
            if os.name == "nt":
                if self._local_collection is None:
                    self._local_collection = _LocalVectorCollection()
                self._collection = self._local_collection
                return self._collection
            self.root.mkdir(parents=True, exist_ok=True)
            try:
                self._client = chromadb.PersistentClient(path=str(self.root))
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception:
                self._client = None
                self._local_collection = self._local_collection or _LocalVectorCollection()
                self._collection = self._local_collection
        return self._collection

    def close(self) -> None:
        client = self._client
        self._collection = None
        self._client = None
        system = getattr(client, "_system", None)
        stop = getattr(system, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                pass


class _LocalVectorCollection:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        for item_id, document, embedding, metadata in zip(ids, documents, embeddings, metadatas, strict=True):
            self._items[item_id] = {
                "document": document,
                "embedding": embedding,
                "metadata": metadata,
            }

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        query = query_embeddings[0] if query_embeddings else []
        scored: list[tuple[str, float, dict[str, Any]]] = []
        for item_id, item in self._items.items():
            metadata = item["metadata"]
            if where and any(metadata.get(key) != value for key, value in where.items()):
                continue
            distance = 1.0 - _cosine_similarity(query, item["embedding"])
            scored.append((item_id, max(0.0, distance), metadata))
        scored.sort(key=lambda item: (item[1], item[0]))
        selected = scored[:n_results]
        return {
            "ids": [[item_id for item_id, _distance, _metadata in selected]],
            "distances": [[distance for _item_id, distance, _metadata in selected]],
            "metadatas": [[metadata for _item_id, _distance, metadata in selected]],
        }

    def get(self, *, ids: list[str], include: list[str] | None = None) -> dict[str, Any]:  # noqa: ARG002
        metadatas = [self._items[item_id]["metadata"] for item_id in ids if item_id in self._items]
        return {"ids": ids, "metadatas": metadatas}


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _chunk_document_text(chunk: KnowledgeChunk) -> str:
    return "\n".join(
        item
        for item in [
            chunk.title,
            chunk.summary,
            chunk.text,
            " ".join(chunk.tags),
            " ".join(chunk.purpose),
        ]
        if item
    )


def _chunk_metadata(chunk: KnowledgeChunk, embedding_provider_id: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "purpose": ",".join(chunk.purpose),
        "allowed_agents": ",".join(chunk.acl.allowed_agents),
        "allowed_contexts": ",".join(chunk.acl.allowed_contexts),
        "sensitivity": chunk.sensitivity,
        "trust_level": chunk.trust_level,
        "content_hash": chunk.content_hash,
        "tags": ",".join(chunk.tags),
        "token_estimate": chunk.token_estimate,
        "embedding_provider": embedding_provider_id,
    }


def _distance_to_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    return 1.0 / (1.0 + max(0.0, distance))


def _chroma_root(root: str | Path) -> Path:
    path = Path(root)
    if path.name == "chroma":
        return path
    if path.name == "indexes":
        return path / "chroma"
    return path / "indexes" / "chroma"
