from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from pprint import pprint

from dotenv import load_dotenv

from .graph import build_graph
from .module_map import build_module_map, write_module_map
from .project_index import annotate_recommendations, recommend_modules
from .specs import load_workflow_spec, summarize_workflow_spec
from .state import CodingState
from .tools.filesystem import resolve_existing_dir, summarize_project
from .workflow_graph import write_workflow_graph
from coder_graph_v2.core import load_workflow as load_v2_workflow
from coder_graph_v2.runtime import run_workflow as run_v2_workflow


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
    parser.add_argument("--provider", help="Override CODER_PROVIDER for this run.")
    parser.add_argument("--model", help="Override CODER_MODEL for this run.")
    parser.add_argument("--base-url", help="Override CODER_BASE_URL for this run.")
    parser.add_argument("--map-only", action="store_true", help="Generate a clickable module map and exit.")
    parser.add_argument("--query", default="", help="User goal used to highlight recommended modules in the module map.")
    parser.add_argument("--output-dir", default="outputs", help="Output directory for generated artifacts.")
    parser.add_argument("--workflow-spec", help="Load and validate a declarative workflow JSON spec.")
    parser.add_argument("--describe-workflow", action="store_true", help="Print workflow spec summary and exit.")
    parser.add_argument("--graph-only", action="store_true", help="Generate a workflow graph HTML from a workflow spec and exit.")
    parser.add_argument("--v2-workflow", help="Run an experimental JSON-driven v2 workflow spec.")
    parser.add_argument("--v2-approve", action="store_true", help="Approve v2 human gates for this run.")
    args = parser.parse_args()

    if args.provider:
        os.environ["CODER_PROVIDER"] = args.provider
    if args.model:
        os.environ["CODER_MODEL"] = args.model
    if args.base_url:
        os.environ["CODER_BASE_URL"] = args.base_url

    if args.v2_workflow:
        workflow = load_v2_workflow(args.v2_workflow)
        repo_root = resolve_existing_dir(args.repo)
        result = run_v2_workflow(
            workflow=workflow,
            request=args.request,
            repo_root=str(repo_root),
            initial_data={"request": args.request, "approved": args.v2_approve},
        )
        print("\n=== V2 STATUS ===")
        pprint(
            {
                "status": result.status,
                "agent_calls": result.agent_calls,
                "tool_calls": result.tool_calls,
                "estimated_tokens_used": result.estimated_tokens_used,
            }
        )
        print("\n=== V2 SUMMARIES ===")
        print(json.dumps(result.summaries, ensure_ascii=False, indent=2))
        print("\n=== V2 EVENTS ===")
        for event in result.events:
            print(f"{event.created_at.isoformat()} {event.type} {event.node_id or '-'} {event.message}")
        return

    if args.workflow_spec:
        spec = load_workflow_spec(args.workflow_spec)
        if args.describe_workflow:
            print(summarize_workflow_spec(spec))
            return
        if args.graph_only:
            html_path = write_workflow_graph(Path(args.output_dir), spec)
            print(f"Workflow graph HTML: {html_path}")
            return

    if args.map_only:
        repo_root = resolve_existing_dir(args.repo)
        files = summarize_project(repo_root, args.scope, max_files=800)
        modules = build_module_map(files)
        recommendations = recommend_modules(args.query, modules, files) if args.query else []
        modules = annotate_recommendations(modules, recommendations) if recommendations else modules
        json_path, html_path = write_module_map(Path(args.output_dir), modules, args.query, recommendations, str(repo_root))
        print(f"Module map JSON: {json_path}")
        print(f"Module map HTML: {html_path}")
        return

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
