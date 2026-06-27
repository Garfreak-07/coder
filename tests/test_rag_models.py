from __future__ import annotations

import unittest

from pydantic import ValidationError

from coder_workbench.memory.rag_models import HybridRagRequest


class HybridRagModelTests(unittest.TestCase):
    def test_request_rejects_unknown_fields(self) -> None:
        payload = _request_payload()
        payload["role_override"] = "task_execution"

        with self.assertRaises(ValidationError):
            HybridRagRequest.model_validate(payload)

    def test_top_k_bounds_are_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            HybridRagRequest(**_request_payload(top_k=0))
        with self.assertRaises(ValidationError):
            HybridRagRequest(**_request_payload(top_k=21))

    def test_weight_bounds_are_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            HybridRagRequest(**_request_payload(dense_weight=-0.1))
        with self.assertRaises(ValidationError):
            HybridRagRequest(**_request_payload(bm25_weight=1.1))

    def test_content_preview_bounds_are_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            HybridRagRequest(**_request_payload(content_preview_chars=2001))


def _request_payload(**overrides):
    values = {
        "role": "task_execution",
        "requested_context": "execution_prompt",
        "query": "PlannerTaskState readiness",
    }
    values.update(overrides)
    return values


if __name__ == "__main__":
    unittest.main()
