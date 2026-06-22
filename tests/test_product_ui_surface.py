from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductUISurfaceTests(unittest.TestCase):
    def test_workbench_app_does_not_expose_legacy_runtime_surface(self) -> None:
        source = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

        for token in [
            "legacy runtime",
            "runtimeJsonText",
            "showAdvancedRuntime",
            "compileLegacyRuntimePreview",
            "startLiveRun",
            "getLiveRun",
            "saveWorkflow",
            "validateWorkflow",
        ]:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

        self.assertIsNone(re.search(r"(?<!Agent)\bWorkflowSpec\b", source))

    def test_frontend_api_does_not_call_legacy_runtime_endpoints(self) -> None:
        source = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        for token in [
            "/api/v2/live-runs",
            "/api/v2/agent-workflows/compile",
            "/api/v2/library/workflows",
        ]:
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
