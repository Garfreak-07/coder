param(
  [string]$ServerUrl = "",
  [string]$SessionApiKeyEnv = "",
  [ValidateSet("legacy-sdk", "default")]
  [string]$ApiProfile = "legacy-sdk",
  [string]$WorkRoot = ".tmp\openhands-live-smoke",
  [string]$Store = ".tmp\openhands-live-smoke\store",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8878,
  [switch]$SkipIfMissingOpenHands
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location -LiteralPath $repoRoot

function Write-Skip {
  param([string]$Reason)
  [pscustomobject]@{
    status = "skipped"
    reason = $Reason
  } | ConvertTo-Json -Depth 6
}

function Stop-Or-Skip {
  param([string]$Reason)
  if ($SkipIfMissingOpenHands) {
    Write-Skip -Reason $Reason
    exit 0
  }
  throw $Reason
}

function Get-FirstEnvValue {
  param([string[]]$Names)
  foreach ($name in $Names) {
    if ([string]::IsNullOrWhiteSpace($name)) {
      continue
    }
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($value)) {
      return [pscustomobject]@{ Name = $name; Value = $value }
    }
  }
  return $null
}

function Resolve-UnderRepo {
  param([string]$PathValue)
  $path = if ([System.IO.Path]::IsPathRooted($PathValue)) {
    $PathValue
  } else {
    Join-Path $repoRoot $PathValue
  }
  $full = [System.IO.Path]::GetFullPath($path)
  $rootFull = [System.IO.Path]::GetFullPath($repoRoot).TrimEnd('\') + '\'
  if (-not $full.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Path must stay under repository root: $full"
  }
  return $full
}

function Invoke-Native {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )
  & $FilePath @Arguments | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed: $FilePath $($Arguments -join ' ')"
  }
}

$liveSmokeFlag = [Environment]::GetEnvironmentVariable("OPENHANDS_LIVE_SMOKE", "Process")
if ($liveSmokeFlag -ne "1") {
  Stop-Or-Skip -Reason "Set OPENHANDS_LIVE_SMOKE=1 to run the live OpenHands smoke."
}

if ([string]::IsNullOrWhiteSpace($ServerUrl)) {
  $server = Get-FirstEnvValue -Names @("OPENHANDS_AGENT_SERVER_URL", "OPENHANDS_SERVER_URL")
  if ($null -ne $server) {
    $ServerUrl = $server.Value
  }
}
if ([string]::IsNullOrWhiteSpace($ServerUrl)) {
  Stop-Or-Skip -Reason "Set OPENHANDS_AGENT_SERVER_URL or pass -ServerUrl to run the live OpenHands smoke."
}

if ([string]::IsNullOrWhiteSpace($SessionApiKeyEnv)) {
  $sessionKey = Get-FirstEnvValue -Names @("OPENHANDS_SESSION_API_KEY", "SESSION_API_KEY")
  if ($null -ne $sessionKey) {
    $SessionApiKeyEnv = $sessionKey.Name
  }
}

$workRootPath = Resolve-UnderRepo -PathValue $WorkRoot
$storePath = Resolve-UnderRepo -PathValue $Store
$repoPath = Join-Path $workRootPath "repo"
$configPath = Join-Path $workRootPath "coder-openhands-smoke.yaml"

if (Test-Path -LiteralPath $workRootPath) {
  $resolvedWorkRoot = [System.IO.Path]::GetFullPath($workRootPath)
  $rootFull = [System.IO.Path]::GetFullPath($repoRoot).TrimEnd('\') + '\'
  if (-not $resolvedWorkRoot.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove path outside repository root: $resolvedWorkRoot"
  }
  Remove-Item -LiteralPath $workRootPath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $repoPath | Out-Null
New-Item -ItemType Directory -Force -Path $storePath | Out-Null

Set-Content -LiteralPath (Join-Path $repoPath "README.md") -Value @(
  "# OpenHands live smoke"
  ""
  "This temporary repository is used by Coder's opt-in live OpenHands smoke."
  "The task is documentation-only and must not commit or push."
) -Encoding UTF8

$git = (Get-Command git).Source
Invoke-Native -FilePath $git -Arguments @("-C", $repoPath, "init")
Invoke-Native -FilePath $git -Arguments @("-C", $repoPath, "config", "user.email", "coder-smoke@example.invalid")
Invoke-Native -FilePath $git -Arguments @("-C", $repoPath, "config", "user.name", "Coder Smoke")
Invoke-Native -FilePath $git -Arguments @("-C", $repoPath, "add", "README.md")
Invoke-Native -FilePath $git -Arguments @("-C", $repoPath, "commit", "-m", "initial smoke fixture")

$sessionLine = if ([string]::IsNullOrWhiteSpace($SessionApiKeyEnv)) {
  "      session_api_key_env:"
} else {
  "      session_api_key_env: $SessionApiKeyEnv"
}

if ($ApiProfile -eq "legacy-sdk") {
  $apiProfileYaml = @"
      api_paths:
        api_prefix: "/api"
        events_search_path: "/conversations/{conversation_id}/events/search"
        run_endpoint_path: "/conversations/{conversation_id}/run"
        websocket_path_template: "/sockets/events/{conversation_id}"
        auth_header: x_session_api_key
      run_start_strategy: post_run_endpoint
"@
} else {
  $apiProfileYaml = @"
      api_paths: {}
      run_start_strategy: post_user_event_with_run_true
"@
}

Set-Content -LiteralPath $configPath -Encoding UTF8 -Value @"
version: 1
models:
  default:
    provider: openai-compatible
    model: smoke
    base_url_env: LLM_BASE_URL
    api_key_env: LLM_API_KEY
agents:
  planner:
    role: planner
    model: default
    system: "Prepare the executor handoff only."
    output_contract: planner_conversation
  executor:
    role: executor
    model: default
    system: "Use OpenHands to inspect README.md. Keep work documentation-only and report evidence."
    output_contract: execution_result
harnesses:
  planner-conversation:
    backend: planner-model
    tools: [repo_search, read_file]
    permissions:
      read_files: allow
      write_files: deny
      run_commands: deny
      network: deny
      secrets: deny
      publish_external: deny
      git_commit: deny
      git_push: deny
      deploy: deny
  openhands-code-edit:
    backend: openhands
    openhands:
      server_url: "$ServerUrl"
$sessionLine
      workspace_mode: local
      prefer_websocket: false
      poll_interval_ms: 1000
      max_event_poll_seconds: 180
      max_events: 200
$apiProfileYaml
    tools: [terminal, file_editor, task_tracker]
    permissions:
      read_files: allow
      write_files: ask
      run_commands: ask
      network: ask
      secrets: ask
      publish_external: deny
      git_commit: deny
      git_push: deny
      deploy: deny
    verification:
      require_evidence: true
workflows:
  planner-led:
    name: OpenHands live smoke
    max_rounds: 2
    nodes:
      - id: planner
        agent: planner
        harness: planner-conversation
      - id: executor
        agent: executor
        harness: openhands-code-edit
    edges:
      - from: planner
        to: executor
        on: ready
      - from: executor
        to: planner
        on: completed
    stop:
      on_status: [completed, blocked, failed]
      final_report_agent: planner
"@

$processEnv = [Environment]::GetEnvironmentVariables("Process")
if ($processEnv.Contains("Path") -and $processEnv.Contains("PATH")) {
  [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
}
[Environment]::SetEnvironmentVariable("CARGO_TARGET_DIR", (Join-Path $repoRoot ".tmp\cargo-target"), "Process")

$cargo = (Get-Command cargo).Source
$doctorArgs = @("run", "-p", "coder-cli", "--bin", "coder-rust", "--", "openhands", "doctor", "--server", $ServerUrl)
if (-not [string]::IsNullOrWhiteSpace($SessionApiKeyEnv)) {
  $doctorArgs += @("--session-api-key-env", $SessionApiKeyEnv)
}
& $cargo @doctorArgs | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "OpenHands doctor failed for the configured server."
}

$task = "Live OpenHands smoke: inspect README.md in repo root '$repoPath'. If a small documentation-only edit is necessary, make it in README.md only. Do not commit, push, or publish. Return a concise final summary with evidence."
$runArgs = @(
  "run", "-p", "coder-cli", "--bin", "coder-rust", "--",
  "workflow", "run",
  "--config", $configPath,
  "--store", $storePath,
  "--repo", $repoPath,
  "planner-led",
  $task
)
$runOutput = & $cargo @runArgs 2>&1
if ($LASTEXITCODE -ne 0) {
  $text = ($runOutput | ForEach-Object { $_.ToString() }) -join "`n"
  throw "OpenHands workflow run failed.`n$text"
}

$runIdLine = $runOutput | ForEach-Object { $_.ToString() } | Where-Object { $_ -match "^run_id=" } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($runIdLine)) {
  throw "OpenHands workflow run did not print run_id."
}
$runId = $runIdLine.Substring("run_id=".Length).Trim()
$eventsPath = Join-Path $storePath "runs\$runId\events.jsonl"
$reportPath = Join-Path $storePath "runs\$runId\artifacts\final-report.json"
if (-not (Test-Path -LiteralPath $eventsPath)) {
  throw "Run events were not written: $eventsPath"
}
if (-not (Test-Path -LiteralPath $reportPath)) {
  throw "Final report was not written: $reportPath"
}

$events = @(Get-Content -LiteralPath $eventsPath | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_ | ConvertFrom-Json })
$reactKinds = @(
  "executor.reasoning_summary",
  "executor.action_selected",
  "tool.started",
  "tool.completed",
  "observation.recorded",
  "executor.next_step",
  "executor.completed",
  "executor.blocked",
  "executor.failed",
  "command.previewed",
  "command.completed",
  "command.failed",
  "patch.applied"
)
$reactEvents = @($events | Where-Object { $reactKinds -contains $_.kind })
if ($reactEvents.Count -lt 1) {
  throw "OpenHands run did not emit public ReAct timeline events."
}
$rawOpenHandsEvents = @($events | Where-Object { $_.kind -like "backend.openhands.*" })
if ($rawOpenHandsEvents.Count -lt 1) {
  throw "OpenHands run did not persist raw OpenHands event refs."
}

$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($report.summary)) {
  throw "Final report did not include a summary."
}

$changed = @(git -C $repoPath status --porcelain)
$reviewChangesCount = 0
if ($changed.Count -gt 0) {
  $outLog = Join-Path $workRootPath "server.out.log"
  $errLog = Join-Path $workRootPath "server.err.log"
  $server = Start-Process -FilePath $cargo `
    -ArgumentList @("run", "-p", "coder-cli", "--bin", "coder-rust", "--", "server", "--host", $HostName, "--port", "$Port", "--store", $storePath) `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -WindowStyle Hidden `
    -PassThru
  try {
    $base = "http://${HostName}:${Port}"
    $health = $null
    foreach ($attempt in 1..90) {
      try {
        $health = Invoke-RestMethod -Method Get -Uri "$base/api/v3/health"
        break
      } catch {
        Start-Sleep -Milliseconds 500
      }
    }
    if ($null -eq $health -or $health.status -ne "ok") {
      throw "Rust v3 health check failed while checking Review Changes. See $errLog"
    }
    $review = Invoke-RestMethod -Method Get -Uri "$base/api/v3/runs/$runId/changes"
    $reviewChangesCount = @($review.changes).Count
    if ($reviewChangesCount -lt 1) {
      throw "Files changed, but Review Changes returned no changes."
    }
  } finally {
    if ($server -and -not $server.HasExited) {
      Stop-Process -Id $server.Id -Force
    }
  }
}

[pscustomobject]@{
  status = "ok"
  server_url = $ServerUrl
  api_profile = $ApiProfile
  run_id = $runId
  events = $events.Count
  react_events = $reactEvents.Count
  raw_openhands_events = $rawOpenHandsEvents.Count
  final_summary = $report.summary
  files_changed = $changed.Count
  review_changes = $reviewChangesCount
  repo = $repoPath
  store = $storePath
} | ConvertTo-Json -Depth 10
