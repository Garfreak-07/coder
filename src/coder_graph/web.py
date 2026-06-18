from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    server_version = "CoderWeb/0.2"

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
            if self.path == "/api/select-folder":
                self._send_json({"path": _select_folder()})
                return
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

    if not repo:
        return {"repo": "", "modules": [], "recommendations": [], "workflow": validate_workflow_spec(DEFAULT_WORKFLOW)}

    repo_root = resolve_existing_dir(repo)
    files = summarize_project(repo_root, [], max_files=800)
    modules = build_module_map(files)
    recommendations = recommend_modules(query, modules, files) if query else []
    modules = annotate_recommendations(modules, recommendations) if recommendations else modules
    return {
        "repo": str(repo_root),
        "modules": modules,
        "tree": _build_project_tree(files),
        "recommendations": recommendations,
        "workflow": validate_workflow_spec(DEFAULT_WORKFLOW),
    }


def _run_workflow(body: dict[str, Any]) -> dict[str, Any]:
    repo = str(body.get("repo", "")).strip()
    request = str(body.get("request", "")).strip() or "Analyze this project and propose a safe improvement plan."
    if not repo:
        return {"error": "Project path is empty. Select a project folder before running."}

    state = {
        "user_request": request,
        "repo_root": str(resolve_existing_dir(repo)),
        "reference_roots": [],
        "target_scope": [],
        "allowed_paths": [],
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


def _select_folder() -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="Select project folder")
        root.destroy()
        return selected or ""
    except Exception as exc:  # pragma: no cover - depends on desktop availability
        return f"ERROR: {exc}"


def _build_project_tree(files: list[dict]) -> dict[str, Any]:
    root: dict[str, Any] = {"name": ".", "path": "", "type": "dir", "children": {}, "file_count": 0}
    for item in files:
        parts = item["path"].replace("\\", "/").split("/")
        node = root
        node["file_count"] += 1
        current_path: list[str] = []
        for index, part in enumerate(parts):
            current_path.append(part)
            is_file = index == len(parts) - 1
            children = node.setdefault("children", {})
            if part not in children:
                children[part] = {
                    "name": part,
                    "path": "/".join(current_path),
                    "type": "file" if is_file else "dir",
                    "children": {},
                    "file_count": 0,
                }
            node = children[part]
            node["file_count"] = int(node.get("file_count", 0)) + 1
    return _sort_tree(root)


def _sort_tree(node: dict[str, Any]) -> dict[str, Any]:
    children = node.get("children", {})
    if isinstance(children, dict):
        sorted_children = sorted(
            (_sort_tree(child) for child in children.values()),
            key=lambda child: (child["type"] == "file", child["name"].lower()),
        )
        node["children"] = sorted_children
    return node


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Coder Local UI</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, system-ui, "Segoe UI", sans-serif; background:#0f172a; color:#e5e7eb; }
    header { padding:18px 24px; background:#111827; border-bottom:1px solid #1f2937; }
    h1 { margin:0 0 6px; font-size:24px; }
    h2 { margin:0 0 12px; font-size:18px; }
    h3 { margin:0 0 8px; font-size:15px; }
    p { color:#94a3b8; line-height:1.5; }
    main { display:grid; grid-template-rows: 1fr auto; min-height:calc(100vh - 82px); }
    .workspace { display:grid; grid-template-columns: 300px minmax(360px,1fr) 420px; gap:14px; padding:14px; min-height:0; }
    .panel { border:1px solid #334155; background:#111827; border-radius:16px; padding:14px; min-height:0; }
    label { display:block; margin-top:12px; color:#cbd5e1; font-size:13px; }
    input, textarea, select { width:100%; margin-top:6px; padding:10px; border-radius:10px; border:1px solid #334155; background:#020617; color:#e5e7eb; }
    textarea { min-height:88px; resize:vertical; }
    button { margin-top:10px; width:100%; border:0; border-radius:10px; padding:10px 12px; background:#2563eb; color:white; cursor:pointer; }
    button.secondary { background:#334155; }
    .modules { max-height:calc(100vh - 210px); overflow:auto; border:1px solid #1f2937; border-radius:14px; padding:10px; background:#020617; }
    .tree-row { display:flex; align-items:center; gap:8px; min-height:28px; border-radius:8px; padding:4px 7px; cursor:pointer; }
    .tree-row:hover { background:#1e293b; }
    .tree-row.focused { background:#1d4ed8; }
    .tree-children { margin-left:18px; border-left:1px solid #1f2937; padding-left:8px; }
    .tree-meta { color:#94a3b8; font-size:12px; margin-left:auto; }
    .breadcrumb { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px; }
    .crumb { border:1px solid #334155; border-radius:999px; padding:4px 8px; background:#0f172a; cursor:pointer; color:#cbd5e1; }
    .badge { display:inline-block; border-radius:999px; padding:3px 7px; margin:6px 4px 0 0; font-size:12px; border:1px solid #475569; }
    .high { background:#7f1d1d; color:#fecaca; } .medium { background:#713f12; color:#fde68a; } .low { background:#064e3b; color:#bbf7d0; }
    .agent-list, .canvas { display:flex; flex-wrap:wrap; gap:10px; align-content:flex-start; min-height:150px; border:1px dashed #334155; border-radius:14px; padding:10px; background:#020617; }
    .agent { width:150px; min-height:86px; border:1px solid #334155; border-radius:14px; padding:10px; background:#0f172a; cursor:grab; user-select:none; }
    .agent.selected { border-color:#38bdf8; }
    .canvas { min-height:210px; margin-top:12px; }
    .config { white-space:pre-wrap; background:#020617; border:1px solid #334155; padding:12px; border-radius:12px; max-height:260px; overflow:auto; }
    .bottom { border-top:1px solid #1f2937; background:#111827; padding:14px; display:grid; grid-template-columns: minmax(300px,1fr) 220px 420px; gap:14px; align-items:end; }
    pre { white-space:pre-wrap; background:#020617; border:1px solid #334155; padding:12px; border-radius:12px; max-height:180px; overflow:auto; margin:0; }
  </style>
</head>
<body>
  <header>
    <h1>Coder Local UI</h1>
    <p>本地、小巧、模块化的 agent 工作流界面。选择项目 → 查看模块地图 → 搭配 agent → 输入需求 → 运行。</p>
  </header>
  <main>
    <div class="workspace">
      <section class="panel">
        <h2>项目</h2>
        <label>项目文件夹路径（可为空）</label>
        <input id="repo" placeholder="F:\bbb\coder 或 D:\projects\app" />
        <button onclick="selectFolder()">选择文件夹</button>
        <button class="secondary" onclick="analyze()">刷新模块地图</button>
        <label>模式</label>
        <select id="mode" onchange="renderAgents()">
          <option value="default">默认工作流</option>
          <option value="automation">自动化：自己组合</option>
        </select>
        <label>导入 workflow / agent JSON</label>
        <input id="importFile" type="file" accept=".json,application/json" onchange="importWorkflow(event)" />
        <p>限制范围不让用户手填。后续由模块选择、Project Index 和 Reviewer Agent 自动生成与审查边界。</p>
      </section>

      <section class="panel">
        <h2>项目树</h2>
        <div id="modules" class="modules"></div>
      </section>

      <section class="panel">
        <h2>Agent 图</h2>
        <h3>可用 agents</h3>
        <div id="agentList" class="agent-list" ondragover="event.preventDefault()" ondrop="dropToList(event)"></div>
        <h3 style="margin-top:14px">当前工作流</h3>
        <div id="agentCanvas" class="canvas" ondragover="event.preventDefault()" ondrop="dropToCanvas(event)"></div>
        <h3 style="margin-top:14px">Agent 配置 / Skills</h3>
        <pre id="agentConfig" class="config">点击一个 agent 查看配置。</pre>
      </section>
    </div>

    <div class="bottom">
      <div>
        <label>需求 / Query</label>
        <textarea id="request" placeholder="例如：优化聊天记录搜索"></textarea>
      </div>
      <div>
        <button onclick="analyze()">根据需求推荐模块</button>
        <button class="secondary" onclick="runWorkflow()">运行当前工作流</button>
      </div>
      <div>
        <label>运行结果</label>
        <pre id="result">等待运行。</pre>
      </div>
    </div>
  </main>

  <script>
    let current = { modules: [], workflow: null };
    let availableAgents = [];
    let canvasAgents = [];
    let draggedAgentId = null;
    let focusedTreePath = "";

    async function post(url, data = {}) {
      const res = await fetch(url, { method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify(data) });
      return await res.json();
    }

    async function selectFolder() {
      const result = await post("/api/select-folder");
      if (result.path && !String(result.path).startsWith("ERROR:")) {
        document.getElementById("repo").value = result.path;
        await analyze();
      } else if (result.path) {
        document.getElementById("result").textContent = result.path;
      }
    }

    async function analyze() {
      const repo = document.getElementById("repo").value;
      const query = document.getElementById("request").value;
      current = await post("/api/analyze", { repo, query });
      if (current.workflow) {
        const agents = current.workflow.agents || [];
        availableAgents = mergeAgents(availableAgents, agents);
        if (!canvasAgents.length) canvasAgents = [...agents];
      }
      renderProjectTree();
      renderAgents();
    }

    async function runWorkflow() {
      document.getElementById("result").textContent = "运行中...";
      const data = await post("/api/run", {
        repo: document.getElementById("repo").value,
        request: document.getElementById("request").value
      });
      document.getElementById("result").textContent = JSON.stringify(data, null, 2);
    }

    async function importWorkflow(event) {
      const file = event.target.files[0];
      if (!file) return;
      const text = await file.text();
      const spec = JSON.parse(text);
      const agents = spec.agents || (spec.id ? [spec] : []);
      availableAgents = mergeAgents(availableAgents, agents);
      renderAgents();
    }

    function mergeAgents(existing, incoming) {
      const byId = new Map(existing.map(agent => [agent.id, agent]));
      incoming.forEach(agent => byId.set(agent.id, agent));
      return [...byId.values()];
    }

    function renderProjectTree() {
      const root = document.getElementById("modules");
      if (!current.tree || !current.tree.children || !current.tree.children.length) {
        root.innerHTML = "<p>暂无项目树。可以先不选择项目；选择项目后这里会显示至少两层目录。</p>";
        return;
      }
      const focused = findTreeNode(current.tree, focusedTreePath) || current.tree;
      root.innerHTML = renderBreadcrumb(focused.path || "") + renderTreeNode(focused, 0, 2);
    }

    function renderBreadcrumb(path) {
      const parts = path ? path.split("/") : [];
      let acc = "";
      const crumbs = [`<span class="crumb" onclick="focusTree('')">root</span>`];
      for (const part of parts) {
        acc = acc ? `${acc}/${part}` : part;
        crumbs.push(`<span class="crumb" onclick="focusTree('${escapeAttr(acc)}')">${escapeHtml(part)}</span>`);
      }
      return `<div class="breadcrumb">${crumbs.join("")}</div>`;
    }

    function renderTreeNode(node, depth, autoDepth) {
      const icon = node.type === "dir" ? "📁" : "📄";
      const draggable = node.type === "dir" ? "true" : "false";
      const children = node.children || [];
      const row = `
        <div class="tree-row ${node.path === focusedTreePath ? "focused" : ""}" draggable="${draggable}"
             onclick="treeClick('${escapeAttr(node.path)}', '${node.type}')"
             ondragstart="dragTree('${escapeAttr(node.path)}')"
             ondragover="event.preventDefault()"
             ondrop="dropTree(event)">
          <span>${icon}</span>
          <span>${escapeHtml(node.name || ".")}</span>
          <span class="tree-meta">${node.type === "dir" ? `${node.file_count || 0} files` : ""}</span>
        </div>`;
      if (node.type !== "dir" || !children.length || depth >= autoDepth) return row;
      return row + `<div class="tree-children">${children.map(child => renderTreeNode(child, depth + 1, autoDepth)).join("")}</div>`;
    }

    function treeClick(path, type) {
      if (type === "dir") focusTree(path);
    }

    function focusTree(path) {
      focusedTreePath = path || "";
      renderProjectTree();
    }

    function dragTree(path) {
      focusedTreePath = path || "";
    }

    function dropTree(event) {
      event.preventDefault();
      renderProjectTree();
    }

    function findTreeNode(node, path) {
      if (!path || node.path === path) return node;
      for (const child of node.children || []) {
        const found = findTreeNode(child, path);
        if (found) return found;
      }
      return null;
    }

    function renderAgents() {
      const list = document.getElementById("agentList");
      const canvas = document.getElementById("agentCanvas");
      const mode = document.getElementById("mode").value;
      if (mode === "default" && current.workflow) {
        canvasAgents = current.workflow.agents || [];
      }
      list.innerHTML = availableAgents.map(agent => agentCard(agent)).join("");
      canvas.innerHTML = canvasAgents.map(agent => agentCard(agent)).join("");
    }

    function agentCard(agent) {
      const encoded = encodeURIComponent(JSON.stringify(agent));
      return `
        <article class="agent" draggable="true" onclick="showAgent('${encoded}')" ondragstart="dragAgent('${agent.id}')">
          <strong>${escapeHtml(agent.role || agent.id)}</strong>
          <p>${escapeHtml(agent.goal || "")}</p>
          ${(agent.tools || []).map(tool => `<span class="badge low">${escapeHtml(tool)}</span>`).join("")}
        </article>
      `;
    }

    function showAgent(encoded) {
      const agent = JSON.parse(decodeURIComponent(encoded));
      document.getElementById("agentConfig").textContent = JSON.stringify(agent, null, 2);
    }

    function dragAgent(id) { draggedAgentId = id; }

    function dropToCanvas(event) {
      event.preventDefault();
      const agent = availableAgents.find(item => item.id === draggedAgentId);
      if (agent && !canvasAgents.find(item => item.id === agent.id)) {
        canvasAgents.push(agent);
        renderAgents();
      }
    }

    function dropToList(event) {
      event.preventDefault();
      canvasAgents = canvasAgents.filter(item => item.id !== draggedAgentId);
      renderAgents();
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#096;");
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
