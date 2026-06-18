from __future__ import annotations

import argparse
from pprint import pprint

from dotenv import load_dotenv

from .graph import build_graph
from .state import CodingState


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Safe LangGraph coding workflow")
    parser.add_argument("--repo", required=True, help="Target local project path to read/analyze.")
    parser.add_argument("--request", default="Improve the selected module safely.", help="Coding request.")
    parser.add_argument("--reference", action="append", default=[], help="Reference project path. Can be repeated.")
    parser.add_argument("--scope", action="append", default=[], help="Target scope inside repo. Can be repeated.")
    parser.add_argument("--allow", action="append", default=[], help="Allowed writable path inside repo. Can be repeated.")
    parser.add_argument("--check", default="", help="Check command to run in repo root.")
    parser.add_argument("--approve", action="store_true", help="Approve dry-run execution after planning.")
    parser.add_argument("--max-iterations", type=int, default=2)
    args = parser.parse_args()

    initial_state: CodingState = {
        "user_request": args.request,
        "repo_root": args.repo,
        "reference_roots": args.reference,
        "target_scope": args.scope,
        "allowed_paths": args.allow or args.scope,
        "check_command": args.check,
        "approved": args.approve,
        "max_iterations": args.max_iterations,
    }

    app = build_graph()
    result = app.invoke(initial_state)

    print("\n=== PLAN ===")
    print(result.get("plan", "No plan produced."))
    print("\n=== REVIEW ===")
    print(result.get("review_notes", "No review notes."))
    print("\n=== STATUS ===")
    pprint(
        {
            "status": result.get("status"),
            "risk_level": result.get("risk_level"),
            "check_passed": result.get("check_passed"),
            "changed_files": result.get("changed_files", []),
        }
    )
    if result.get("check_output"):
        print("\n=== CHECK OUTPUT ===")
        print(result["check_output"])


if __name__ == "__main__":
    main()
