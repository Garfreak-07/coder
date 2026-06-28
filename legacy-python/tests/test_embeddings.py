from __future__ import annotations

import unittest

from coder_workbench.memory.embeddings import HashingEmbeddingProvider


class HashingEmbeddingProviderTests(unittest.TestCase):
    def test_embeddings_are_deterministic(self) -> None:
        provider = HashingEmbeddingProvider(dimensions=32)

        self.assertEqual(provider.embed_query("PlannerTaskState"), provider.embed_query("PlannerTaskState"))

    def test_embeddings_have_fixed_dimensions(self) -> None:
        provider = HashingEmbeddingProvider(dimensions=64)

        vectors = provider.embed_documents(["one", "two"])

        self.assertEqual([len(vector) for vector in vectors], [64, 64])

    def test_identical_texts_produce_identical_vectors(self) -> None:
        provider = HashingEmbeddingProvider(dimensions=16)

        first, second = provider.embed_documents(["same text", "same text"])

        self.assertEqual(first, second)

    def test_empty_text_does_not_crash(self) -> None:
        provider = HashingEmbeddingProvider(dimensions=8)

        vector = provider.embed_query("")

        self.assertEqual(vector, [0.0] * 8)

    def test_invalid_dimensions_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            HashingEmbeddingProvider(dimensions=0)


if __name__ == "__main__":
    unittest.main()
