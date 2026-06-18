from __future__ import annotations

import html
import json
from pathlib import Path

from .specs import WorkflowSpec


def write_workflow_graph(outputs_dir: Path, spec: WorkflowSpec) -> Path:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    html_path = outputs_dir / "workflow-graph.html"
    html_path.write_text(_render_html(spec), encoding="utf-8")
    return html_path


def _render_html(spec: WorkflowSpec) -> str:
    agent_by_id = {agent["id"]: agent for agent in spec["agents"]}
    nodes = []
    for index, step in enumerate(spec["steps"]):
        agent = agent_by_id.get(step["uses"])
        nodes.append(
            {
                "id": step["id"],
                "kind": step["kind"],
                "uses": step["uses"],
                "title": agent["role"] if agent else step["uses"],
                "subtitle": agent["goal"] if agent else f"Built-in: {step['uses']}",
                "input_keys": step["input_keys"],
                "output_key": step["output_key"],
                "x": 80 + index * 230,
                "y": 160,
            }
        )

    data = html.escape(json.dumps({"spec": spec, "nodes": nodes}, ensure_ascii=False))
    node_cards = "\n".join(_node_card(node) for node in nodes)
    connectors = "\n".join(_connector(nodes[index], nodes[index + 1]) for index in range(len(nodes) - 1))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Coder Workflow Graph</title>
  <style>
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f172a;
      color: #e5e7eb;
    }}
    header {{
      padding: 24px;
      background: #111827;
      border-bottom: 1px solid #1f2937;
    }}
    .subtitle {{ color: #94a3b8; line-height: 1.5; }}
    .canvas {{
      position: relative;
      min-height: 430px;
      overflow: auto;
      padding: 32px;
    }}
    .node {{
      position: absolute;
      width: 190px;
      min-height: 128px;
      border: 1px solid #334155;
      border-radius: 16px;
      background: #111827;
      padding: 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,.2);
    }}
    .node h3 {{ margin: 0 0 8px; font-size: 16px; }}
    .node p {{ margin: 0; color: #cbd5e1; font-size: 13px; line-height: 1.4; }}
    .badge {{
      display: inline-block;
      margin-bottom: 10px;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      border: 1px solid #475569;
    }}
    .agent {{ background: #1e3a8a; color: #bfdbfe; }}
    .deterministic {{ background: #064e3b; color: #bbf7d0; }}
    .human_gate {{ background: #713f12; color: #fde68a; }}
    svg {{
      position: absolute;
      left: 0;
      top: 0;
      width: 1300px;
      height: 430px;
      pointer-events: none;
    }}
    aside {{
      margin: 0 32px 32px;
      padding: 18px;
      border: 1px solid #334155;
      border-radius: 16px;
      background: #111827;
    }}
    code {{
      color: #93c5fd;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(spec['name'])}</h1>
    <p class="subtitle">{html.escape(spec['description'])}</p>
    <p class="subtitle">Max loops: {spec['max_loops']} · Spec ID: <code>{html.escape(spec['id'])}</code></p>
  </header>
  <main class="canvas">
    <svg>{connectors}</svg>
    {node_cards}
  </main>
  <aside>
    <h2>Stop conditions</h2>
    <ul>
      {"".join(f"<li>{html.escape(item)}</li>" for item in spec["stop_conditions"])}
    </ul>
    <p class="subtitle">First version is intentionally read-only: this graph explains the default workflow before arbitrary imported workflows are executable.</p>
  </aside>
  <script type="application/json" id="workflow-data">{data}</script>
</body>
</html>"""


def _node_card(node: dict) -> str:
    return f"""
    <article class="node" style="left:{node['x']}px; top:{node['y']}px">
      <span class="badge {html.escape(node['kind'])}">{html.escape(node['kind'])}</span>
      <h3>{html.escape(node['title'])}</h3>
      <p>{html.escape(node['subtitle'])}</p>
      <p style="margin-top:10px">out: <code>{html.escape(node['output_key'])}</code></p>
    </article>
    """


def _connector(left: dict, right: dict) -> str:
    x1 = left["x"] + 220
    y1 = left["y"] + 68
    x2 = right["x"] - 8
    y2 = right["y"] + 68
    return f"""
      <path d="M{x1},{y1} C{x1 + 40},{y1} {x2 - 40},{y2} {x2},{y2}" stroke="#38bdf8" stroke-width="2" fill="none" marker-end="url(#arrow)" />
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z" fill="#38bdf8" />
        </marker>
      </defs>
    """
