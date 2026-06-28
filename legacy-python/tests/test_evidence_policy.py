from __future__ import annotations

import unittest

from coder_workbench.context.evidence_policy import (
    EvidenceKind,
    code_fact_supported_by_evidence_kind,
    is_code_like_text,
    rag_evidence_metadata,
)


class EvidencePolicyTests(unittest.TestCase):
    def test_rag_metadata_marks_knowledge_hint(self) -> None:
        metadata = rag_evidence_metadata("PlannerTaskState is in src/app.py")

        self.assertEqual(metadata["evidence_kind"], EvidenceKind.KNOWLEDGE_HINT.value)
        self.assertTrue(metadata["requires_repo_verification"])

    def test_code_like_text_detection(self) -> None:
        self.assertTrue(is_code_like_text("test_openhands_provider"))
        self.assertTrue(is_code_like_text("src/coder_workbench/context/harness_packets.py"))
        self.assertFalse(is_code_like_text("roadmap and design notes"))

    def test_knowledge_hint_does_not_support_code_fact(self) -> None:
        self.assertFalse(code_fact_supported_by_evidence_kind("knowledge_hint"))
        self.assertTrue(code_fact_supported_by_evidence_kind("repo_evidence"))
        self.assertTrue(code_fact_supported_by_evidence_kind("run_evidence"))


if __name__ == "__main__":
    unittest.main()
