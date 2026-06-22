from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_PATHS = [ROOT / "src" / "coder_workbench", ROOT / "frontend" / "src"]

FORBIDDEN_GLOBAL_SYMBOLS = [
    "SynthesizerEngine",
    "FinalReviewEngine",
    "synthesis_artifact",
    "do_work",
    "organize_information",
    "research_sources",
    "write_draft",
    "final_tester",
    "aggregate_tests",
    "summarizer",
    "researcher",
    "writer",
    "reviewer",
]

FORBIDDEN_ROLE_SURFACE_PATTERNS = [
    re.compile(r"role_card['\"]?\s*[:=]\s*['\"](?:do_work|check_result|organize_information|research_sources|write_draft|worker|custom)['\"]"),
    re.compile(r"\brole['\"]?\s*[:=]\s*['\"](?:worker|reviewer|writer|researcher|summarizer|custom)['\"]"),
    re.compile(r"<option\s+value=['\"]['\"]>\s*Custom\s*</option>"),
    re.compile(r"\b(?:Do work|Research|Writer|Summarizer|Reviewer|Final reviewer|Synthesizer)\b"),
]


class NoRemovedEngineSymbolsTests(unittest.TestCase):
    def test_removed_engine_and_role_symbols_are_absent_from_product_code(self) -> None:
        offenders: list[str] = []
        for path, text in _product_sources():
            for symbol in FORBIDDEN_GLOBAL_SYMBOLS:
                if symbol in text:
                    offenders.append(f"{path.relative_to(ROOT)} contains {symbol}")

        self.assertEqual(offenders, [])

    def test_removed_role_surfaces_are_absent_from_product_code(self) -> None:
        offenders: list[str] = []
        for path, text in _product_sources():
            for pattern in FORBIDDEN_ROLE_SURFACE_PATTERNS:
                for match in pattern.finditer(text):
                    offenders.append(f"{path.relative_to(ROOT)} contains removed role surface {match.group(0)!r}")

        self.assertEqual(offenders, [])


def _product_sources() -> list[tuple[Path, str]]:
    sources: list[tuple[Path, str]] = []
    for root in PRODUCT_PATHS:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            sources.append((path, path.read_text(encoding="utf-8")))
    return sources


if __name__ == "__main__":
    unittest.main()
