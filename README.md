# LangGraph Coder

一个偏保守的本地代码改进编排器骨架，用 LangGraph 把“读项目 → 计划 → 人工确认 → 小步执行 → 检查 → 复盘/循环”拆成明确节点。

第一版默认以安全为先：

- 可以读取任意你传入的本地项目路径。
- 默认不直接修改代码，除非显式使用执行模式。
- 修改前需要人工确认允许范围。
- 修改范围必须限制在你批准的文件或目录内。
- 检查命令默认也需要你显式传入。

## 安装

建议在这个目录下创建 Python 虚拟环境：

```powershell
cd langgraph_coder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

如果要启用 LLM 规划，请复制环境变量文件：

```powershell
Copy-Item .env.example .env
```

然后填写：

```env
OPENAI_API_KEY=你的 key
CODER_MODEL=gpt-4.1-mini
```

没有 `OPENAI_API_KEY` 时，程序仍然可以跑，但会使用保守的本地占位计划，不会假装自己理解了项目。

## 最小使用

只分析当前仓库：

```powershell
python -m coder_graph.cli --repo ..
```

或者：

```powershell
langgraph-coder --repo ..
```

分析其他本地项目：

```powershell
python -m coder_graph.cli --repo "D:\projects\some-app"
```

限制目标范围：

```powershell
python -m coder_graph.cli --repo "D:\projects\some-app" --scope src/features/chat --scope src/shared
```

带参考项目：

```powershell
python -m coder_graph.cli --repo "D:\projects\my-app" --reference "D:\projects\reference-app"
```

带检查命令：

```powershell
python -m coder_graph.cli --repo .. --check "npm run typecheck"
```

## 设计

```text
START
  ↓
intake
  ↓
scan_repo
  ↓
plan
  ↓
approval
  ↓
execute
  ↓
check
  ↓
review
  ↓
route
    ├─ done
    ├─ retry
    └─ blocked
```

当前版本的 `execute` 节点默认是 dry-run，只输出建议，不直接写文件。后续可以把它升级成“生成 patch → 显示 diff → 人工确认 → 应用 patch”的执行器。

## 为什么这样设计

自动改代码最危险的不是“写不出来”，而是“写太多、写偏、写了不该写的地方”。所以第一版先把安全边界做硬：

- repo 路径显式传入；
- scope 显式传入；
- 修改需要人工批准；
- 检查命令显式传入；
- 循环次数有限制；
- executor 默认不落盘。
