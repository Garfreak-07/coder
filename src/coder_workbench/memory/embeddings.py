from __future__ import annotations

import hashlib
import math
import re


class EmbeddingProvider:
    id: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class HashingEmbeddingProvider(EmbeddingProvider):
    id = "hashing-v1"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = -1.0 if digest[4] & 1 else 1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def _tokenize(text: str) -> list[str]:
    normalized = text.replace("\\", "/")
    raw_tokens = re.findall(r"[A-Za-z0-9_./:-]+", normalized)
    tokens: list[str] = []
    for raw in raw_tokens:
        lowered = raw.lower()
        if len(lowered) > 1:
            tokens.append(lowered)
        path_parts = [part for part in re.split(r"[/.:]+", raw) if part]
        for part in path_parts:
            tokens.extend(_split_identifier(part))
    return list(dict.fromkeys(token for token in tokens if token))


def _split_identifier(value: str) -> list[str]:
    parts: list[str] = []
    for segment in re.split(r"[-_]+", value):
        if not segment:
            continue
        camel = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", segment)
        camel = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", camel)
        for item in camel.split():
            lowered = item.lower()
            if len(lowered) > 1:
                parts.append(lowered)
    return parts
