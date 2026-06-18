from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .graph import build_graph
from .module_map import build_module_map
from .project_index import annotate_recommendations, recommend_modules
from .specs import validate_workflow_spec
from .tools.filesystem import resolve_existing_dir, summarize_project


DEFAULT_WORKFLOW = {
    "id": "coding-review",
    "name": "Default Coding Workflow",
    "description": "Map project, plan with Planner Agent, review with Reviewer Agent, then stop before mutation.",
    "max_loops": 3,
    "agents": [
        {
            "id": "planner",
            "role": "Planner Agent",
            "goal": "Create a short, scoped implementation plan.",
            "input_keys": ["user_request", "modules", "allowed_paths", "repo_files"],
            "output_schema": {
                "summary": "string",
                "target_files": "list[string]",
                "steps": "list[string]",
                "risks": "list[string]",
                "checks": "list[string]",
                "needs_human": "boolean",
            },
            "model": None,
            "tools": [],
        },
        {
            "id": "reviewer",
            "role": "Reviewer Agent",
            "goal": "Reject scope escape, high risk, and unclear plans.",
            "input_keys": ["user_request", "planner_result", "allowed_paths", "modules"],
            "output_schema": {
                "approved": "boolean",
                "risk_level": "low|medium|high",
                "scope_escape": "boolean",
                "stop_reasons": "list[string]",
                "notes": "string",
            },
            "model": None,
            "tools": [],
        },
    ],
    "steps": [
        {"id": "scan", "kind": "deterministic", "uses": "scan_repo_node", "input_keys": ["repo_root"], "output_key": "repo_files"},
        {"id": "map", "kind": "deterministic", "uses": "module_map_node", "input_keys": ["repo_files"], "output_key": "modules"},
        {"id": "plan", "kind": "agent", "uses": "planner", "input_keys": ["user_request", "modules"], "output_key": "planner_result"},
        {"id": "review", "kind": "agent", "uses": "reviewer", "input_keys": ["planner_result"], "output_key": "reviewer_result"},
        {"id": "approve", "kind": "human_gate", "uses": "approval_node", "input_keys": ["planner_result", "reviewer_result"], "output_key": "approved"},
    ],
    "stop_conditions": ["scope_escape", "risk_level == high", "max_loops reached"],
}


def run_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), CoderWebHandler)
    print(f"Coder local web UI: http://{host}:{port}")
    server.serve_forever()


class CoderWebHandler(BaseHTTPRequestHandler):
    server_version = "CoderWeb/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            self._send_html(INDEX_HTML)
            return
        if self.path == "/api/workflow":
            self._send_json({"workflow": validate_workflow_spec(DEFAULT_WORKFLOW)})
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._read_json()
            if self.path == "/api/analyze":
                self._send_json(_analyze(body))
                return
            if self.path == "/api/run":
                self._send_json(_run_workflow(body))
                return
            self.send_error(404)
        except Exception as exc:  # pragma: no cover - defensive web boundary
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, html: str) -> None:
        payload = html.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _analyze(body: dict[str, Any]) -> dict[str, Any]:
    repo = str(body.get("repo", "")).strip()
    query = str(body.get("query", "")).strip()
    scope = _as_list(body.get("scope"))

    if not repo:
        return {"repo": "", "modules": [], "recommendations": [], "workflow": validate_workflow_spec(DEFAULT_WORKFLOW)}

    repo_root = resolve_existing_dir(repo)
    files = summarize_project(repo_root, scope, max_files=800)
    modules = build_module_map(files)
    recommendations = recommend_modules(query, modules, files) if query else []
    modules = annotate_recommendations(modules, recommendations) if recommendations else modules
    return {
        "repo": str(repo_root),
        "modules": modules,
        "recommendations": recommendations,
        "workflow": validate_workflow_spec(DEFAULT_WORKFLOW),
    }


def _run_workflow(body: dict[str, Any]) -> dict[str, Any]:
    repo = str(body.get("repo", "")).strip()
    request = str(body.get("request", "")).strip() or "Analyze this project and propose a safe improvement plan."
    scope = _as_list(body.get("scope"))
    if not repo:
        return {"error": "Project path is empty. Enter a project path before running."}

    state = {
        "user_request": request,
        "repo_root": str(resolve_existing_dir(repo)),
        "reference_roots": [],
        "target_scope": scope,
        "allowed_paths": scope,
        "check_command": "",
        "approved": False,
        "max_iterations": 3,
    }
    result = build_graph().invoke(state)
    return {
        "plan": result.get("plan", ""),
        "review": result.get("review_notes", ""),
        "status": {
            "status": result.get("status"),
            "risk_level": result.get("risk_level"),
            "check_passed": result.get("check_passed"),
            "changed_files": result.get("changed_files", []),
        },
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Coder Local UI</title>
  <style>
    :root { color-scheme: dark; }
    body { margin:0; font-family: ui-sans-serif, system-ui, "Segoe UI", sans-serif; background:#0f172a; color:#e5e7eb; }
    header { padding:20px 24px; background:#111827; border-bottom:1px solid #1f2937; }
    h1 { margin:0 0 6px; font-size:24px; }
    p { color:#94a3b8; line-height:1.5; }
    main { display:grid; grid-template-columns: 340px 1fr; min-height:calc(100vh - 82px); }
    aside { padding:18px; border-right:1px solid #1f2937; background:#111827; }
    section { padding:18px; }
    label { display:block; margin-top:14px; color:#cbd5e1; font-size:13px; }
    input, textarea, select { width:100%; box-sizing:border-box; margin-top:6px; padding:10px; border-radius:10px; border:1px solid #334155; background:#020617; color:#e5e7eb; }
    textarea { min-height:88px; resize:vertical; }
    button { margin-top:12px; width:100%; border:0; border-radius:10px; padding:11px 12px; background:#2563eb; color:white; cursor:pointer; }
    button.secondary { background:#334155; }
    .layout { display:grid; grid-template-columns: 1fr 420px; gap:16px; }
    .panel { border:1px solid #334155; background:#111827; border-radius:16px; padding:14px; }
    .modules { display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:10px; max-height:440px; overflow:auto; }
    .module { border:1px solid #334155; border-radius:14px; padding:12px; background:#020617; }
    .module.recommended { border-color:#22c55e; }
    .badge { display:inline-block; border-radius:999px; padding:3px 7px; margin:6px 4px 0 0; font-size:12px; border:1px solid #475569; }
    .high { background:#7f1d1d; color:#fecaca; } .medium { background:#713f12; color:#fde68a; } .low { background:#064e3b; color:#bbf7d0; }
    .workflow { display:flex; gap:10px; overflow:auto; padding-bottom:8px; }
    .node { min-width:150px; border:1px solid #334155; border-radius:14px; padding:12px; background:#020617; }
    .arrow { align-self:center; color:#38bdf8; }
    pre { white-space:pre-wrap; background:#020617; border:1px solid #334155; padding:12px; border-radius:12px; max-height:360px; overflow:auto; }
    .tabs { display:flex; gap:10px; }
    .tabs button { width:auto; padding:8px 12px; margin-top:0; }
  </style>
</head>
<body>
  <header>
    <h1>Coder Local UI</h1>
    <p>小而精的本地 agent 工作流界面：项目路径可以为空；模块地图常驻；选择默认工作流或自动化组合，最后运行。</p>
  </header>
  <main>
    <aside>
      <label>项目文件夹路径（可为空）</label>
      <input id="repo" placeholder="F:\bbb\coder 或 D:\projects\app" />
      <label>需求 / Query</label>
      <textarea id="request" placeholder="例如：优化聊天记录搜索"></textarea>
      <label>限制 scope（可选，逗号分隔）</label>
      <input id="scope" placeholder="src/features/chat" />
      <button onclick="analyze()">生成/刷新模块地图</button>
      <button class="secondary" onclick="runWorkflow()">运行当前工作流</button>
      <label>模式</label>
      <select id="mode" onchange="renderWorkflow()">
        <option value="default">默认工作流</option>
        <option value="automation">自动化：手动组合</option>
      </select>
      <p>自动化第一版只做安全预览：可以组合节点，但不会执行任意用户代码。</p>
    </aside>
    <section>
      <div class="layout">
        <div class="panel">
          <h2>模块地图</h2>
          <div id="modules" class="modules"></div>
        </div>
        <div class="panel">
          <h2>Agent 工作流图</h2>
          <div id="workflow" class="workflow"></div>
          <h3>运行结果</h3>
          <pre id="result">等待运行。</pre>
        </div>
      </div>
    </section>
  </main>
  <script>
    let current = { modules: [], workflow: null };
    const automationNodes = ["Project Index", "Module Map", "Planner Agent", "Reviewer Agent", "Human Gate"];

    async function post(url, data) {
      const res = await fetch(url, { method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify(data) });
      return await res.json();
    }

    async function analyze() {
      const repo = document.getElementById("repo").value;
      const query = document.getElementById("request").value;
      const scope = document.getElementById("scope").value;
      current = await post("/api/analyze", { repo, query, scope });
      renderModules();
      renderWorkflow();
    }

    async function runWorkflow() {
      document.getElementById("result").textContent = "运行中...";
      const data = await post("/api/run", {
        repo: document.getElementById("repo").value,
        request: document.getElementById("request").value,
        scope: document.getElementById("scope").value
      });
      document.getElementById("result").textContent = JSON.stringify(data, null, 2);
    }

    function renderModules() {
      const root = document.getElementById("modules");
      const modules = current.modules || [];
      if (!modules.length) {
        root.innerHTML = "<p>暂无模块。输入项目路径后点击生成；项目路径也可以先留空。</p>";
        return;
      }
      root.innerHTML = modules.map(m => `
        <article class="module ${m.recommended ? "recommended" : ""}">
          <strong>${escapeHtml(m.path)}</strong>
          <div>
            <span class="badge ${m.importance}">重要 ${m.importance}</span>
            <span class="badge ${m.risk}">风险 ${m.risk}</span>
            ${m.recommended ? `<span class="badge low">推荐 ${m.match_score}</span>` : ""}
          </div>
          <p>${m.file_count} files · ${m.size_bytes} bytes</p>
        </article>
      `).join("");
    }

    function renderWorkflow() {
      const root = document.getElementById("workflow");
      const mode = document.getElementById("mode").value;
      if (mode === "automation") {
        root.innerHTML = automationNodes.map((name, i) => `
          <div class="node"><span class="badge medium">可组合</span><strong>${name}</strong></div>${i < automationNodes.length - 1 ? '<div class="arrow">→</div>' : ''}
        `).join("");
        return;
      }
      const steps = current.workflow?.steps || [];
      root.innerHTML = steps.map((s, i) => `
        <div class="node"><span class="badge ${s.kind === "agent" ? "medium" : "low"}">${s.kind}</span><strong>${s.uses}</strong><p>out: ${s.output_key}</p></div>${i < steps.length - 1 ? '<div class="arrow">→</div>' : ''}
      `).join("") || "<p>默认工作流等待加载。</p>";
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    }

    analyze();
  </script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Coder local web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
