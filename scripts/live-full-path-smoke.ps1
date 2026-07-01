param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8878,
  [string]$WorkRoot = ".tmp\live-full-path-smoke",
  [string]$Provider = "deepseek",
  [string]$BaseUrl = "",
  [string]$Model = "",
  [string]$ProviderProxyUrl = "",
  [string]$ApiKeyEnv = "",
  [string]$OpenHandsServerUrl = "",
  [string]$OpenHandsSessionApiKey = "",
  [string]$OpenHandsSessionApiKeyEnv = "OPENHANDS_SESSION_API_KEY",
  [switch]$Live,
  [switch]$LoadLocalEnv,
  [switch]$SkipIfMissingLiveConfig
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location -LiteralPath $repoRoot

function Stop-Or-Skip {
  param([string]$Reason)
  if ($SkipIfMissingLiveConfig) {
    [pscustomobject]@{
      status = "skipped"
      reason = $Reason
    } | ConvertTo-Json -Depth 4
    exit 0
  }
  throw $Reason
}

function Assert-Smoke {
  param(
    [bool]$Condition,
    [string]$Message
  )
  if (-not $Condition) {
    throw $Message
  }
}

if ($LoadLocalEnv) {
  $localEnvPath = Join-Path $repoRoot ".local-env.ps1"
  if (-not (Test-Path -LiteralPath $localEnvPath)) {
    Stop-Or-Skip -Reason "Local env file not found: $localEnvPath"
  }
  . $localEnvPath
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

function Invoke-Native {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )
  & $FilePath @Arguments | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "$FilePath $($Arguments -join ' ') failed"
  }
}

function Set-Utf8NoBomContent {
  param(
    [string]$LiteralPath,
    [string[]]$Value
  )
  $encoding = New-Object System.Text.UTF8Encoding($false)
  $text = ($Value -join [Environment]::NewLine) + [Environment]::NewLine
  [System.IO.File]::WriteAllText($LiteralPath, $text, $encoding)
}

function Resolve-UnderRepo {
  param([string]$PathValue)
  $fullPath = if ([System.IO.Path]::IsPathRooted($PathValue)) {
    [System.IO.Path]::GetFullPath($PathValue)
  } else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PathValue))
  }
  $repoFullPath = [System.IO.Path]::GetFullPath($repoRoot).TrimEnd('\', '/')
  if (-not $fullPath.StartsWith($repoFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Path must stay under repository root: $PathValue"
  }
  $fullPath
}

function New-SmokeRepo {
  param([string]$Parent)
  $path = Join-Path $Parent "repo"
  New-Item -ItemType Directory -Force -Path $path | Out-Null
  Set-Utf8NoBomContent -LiteralPath (Join-Path $path "README.md") -Value @(
    "# Full path smoke"
    ""
    "This temporary repository is used by Coder's live full path smoke."
  )
  $docsPath = Join-Path $path "docs"
  New-Item -ItemType Directory -Force -Path $docsPath | Out-Null
  Set-Utf8NoBomContent -LiteralPath (Join-Path $docsPath "FULL_PATH_SMOKE_RESULT.md") -Value @(
    "# Full Path Smoke Result"
    ""
    "Initial fixture. OpenHands must update this file."
  )
  $git = (Get-Command git).Source
  Invoke-Native -FilePath $git -Arguments @("-C", $path, "init")
  Invoke-Native -FilePath $git -Arguments @("-C", $path, "config", "core.autocrlf", "false")
  Invoke-Native -FilePath $git -Arguments @("-C", $path, "config", "core.safecrlf", "false")
  Invoke-Native -FilePath $git -Arguments @("-C", $path, "config", "user.email", "coder-full-path-smoke@example.invalid")
  Invoke-Native -FilePath $git -Arguments @("-C", $path, "config", "user.name", "Coder Full Path Smoke")
  Invoke-Native -FilePath $git -Arguments @("-C", $path, "add", "README.md", "docs/FULL_PATH_SMOKE_RESULT.md")
  Invoke-Native -FilePath $git -Arguments @("-C", $path, "commit", "-m", "initial full path smoke fixture")
  $path
}

function ConvertTo-JsonBody {
  param([hashtable]$Value)
  $Value | ConvertTo-Json -Depth 80
}

function Invoke-RestJsonWithRetry {
  param(
    [string]$Method,
    [string]$Uri,
    [hashtable]$Headers = @{},
    [string]$Body = $null,
    [int]$Attempts = 3
  )
  for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    try {
      if ($PSBoundParameters.ContainsKey("Body")) {
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers -Body $Body
      }
      return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers
    } catch {
      if ($attempt -ge $Attempts) {
        throw
      }
      Start-Sleep -Seconds $attempt
    }
  }
}

function Get-SerializedArtifactsText {
  param(
    [object[]]$Objects,
    [string[]]$Files
  )
  $parts = @()
  foreach ($object in $Objects) {
    if ($null -ne $object) {
      $parts += ($object | ConvertTo-Json -Depth 80)
    }
  }
  foreach ($file in $Files) {
    if (Test-Path -LiteralPath $file) {
      $parts += [System.IO.File]::ReadAllText($file)
    }
  }
  $parts -join "`n"
}

function Assert-NoSecretLeak {
  param(
    [string]$Text,
    [object[]]$Secrets
  )
  foreach ($secret in $Secrets) {
    if ($null -eq $secret) {
      continue
    }
    $value = if ($secret.PSObject.Properties.Name -contains "Value") {
      [string]$secret.Value
    } else {
      [string]$secret
    }
    if ($value.Trim().Length -ge 4 -and $Text.Contains($value)) {
      throw "Secret value from live full path smoke appeared in serialized artifacts."
    }
  }
}

$liveFlag = [Environment]::GetEnvironmentVariable("CODER_FULL_PATH_LIVE_SMOKE", "Process")
if ($liveFlag -ne "1" -and -not $Live) {
  Stop-Or-Skip -Reason "Set CODER_FULL_PATH_LIVE_SMOKE=1 to run the live full path smoke."
}

$normalizedProvider = $Provider.Trim().ToLowerInvariant()
if ([string]::IsNullOrWhiteSpace($normalizedProvider)) {
  $normalizedProvider = "deepseek"
}

$apiKeyCandidates = @()
if (-not [string]::IsNullOrWhiteSpace($ApiKeyEnv)) {
  $apiKeyCandidates += $ApiKeyEnv
}
switch ($normalizedProvider) {
  "deepseek" { $apiKeyCandidates += @("DEEPSEEK_API_KEY", "LLM_API_KEY") }
  "openai" { $apiKeyCandidates += @("OPENAI_API_KEY", "LLM_API_KEY") }
  default { $apiKeyCandidates += @("LLM_API_KEY", "DEEPSEEK_API_KEY", "CODER_API_KEY") }
}
$apiKey = Get-FirstEnvValue -Names $apiKeyCandidates
if ($null -eq $apiKey) {
  Stop-Or-Skip -Reason "No live provider API key found in: $($apiKeyCandidates -join ', ')"
}

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
  $BaseUrl = [Environment]::GetEnvironmentVariable("LLM_BASE_URL", "Process")
}
if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
  if ($normalizedProvider -eq "openai") {
    $BaseUrl = "https://api.openai.com/v1"
  } else {
    $BaseUrl = "https://api.deepseek.com"
  }
}

if ([string]::IsNullOrWhiteSpace($Model)) {
  $Model = [Environment]::GetEnvironmentVariable("LLM_MODEL", "Process")
}
if ([string]::IsNullOrWhiteSpace($Model)) {
  $Model = if ($normalizedProvider -eq "openai") { "gpt-5.5" } else { "deepseek-v4-flash" }
}

if ([string]::IsNullOrWhiteSpace($ProviderProxyUrl)) {
  $ProviderProxyUrl = [Environment]::GetEnvironmentVariable("HTTPS_PROXY", "Process")
}
if ([string]::IsNullOrWhiteSpace($ProviderProxyUrl)) {
  $ProviderProxyUrl = [Environment]::GetEnvironmentVariable("HTTP_PROXY", "Process")
}

if ([string]::IsNullOrWhiteSpace($OpenHandsServerUrl)) {
  $OpenHandsServerUrl = [Environment]::GetEnvironmentVariable("OPENHANDS_AGENT_SERVER_URL", "Process")
}
if ([string]::IsNullOrWhiteSpace($OpenHandsServerUrl)) {
  Stop-Or-Skip -Reason "Set OPENHANDS_AGENT_SERVER_URL or pass -OpenHandsServerUrl."
}
$OpenHandsServerUrl = $OpenHandsServerUrl.TrimEnd('/')

$openHandsSessionKey = $null
if (-not [string]::IsNullOrWhiteSpace($OpenHandsSessionApiKey)) {
  $openHandsSessionKey = [pscustomobject]@{
    Name = "OpenHandsSessionApiKey"
    Value = $OpenHandsSessionApiKey
  }
} elseif (-not [string]::IsNullOrWhiteSpace($OpenHandsSessionApiKeyEnv)) {
  $openHandsSessionKey = Get-FirstEnvValue -Names @($OpenHandsSessionApiKeyEnv)
}

$workRootPath = Resolve-UnderRepo -PathValue $WorkRoot
$storePath = Join-Path $workRootPath "store"
$repoPath = Join-Path $workRootPath "repo"
$outLog = Join-Path $workRootPath "server.out.log"
$errLog = Join-Path $workRootPath "server.err.log"

if (Test-Path -LiteralPath $workRootPath) {
  Remove-Item -LiteralPath $workRootPath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $workRootPath | Out-Null
New-Item -ItemType Directory -Force -Path $storePath | Out-Null
$repoPath = New-SmokeRepo -Parent $workRootPath
$resultDocPath = Join-Path $repoPath "docs\FULL_PATH_SMOKE_RESULT.md"
$initialResultDoc = [System.IO.File]::ReadAllText($resultDocPath)

$processEnv = [Environment]::GetEnvironmentVariables("Process")
if ($processEnv.Contains("Path") -and $processEnv.Contains("PATH")) {
  [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
}
[Environment]::SetEnvironmentVariable("CARGO_TARGET_DIR", (Join-Path $repoRoot ".tmp\cargo-target"), "Process")
[Environment]::SetEnvironmentVariable("LLM_BASE_URL", $BaseUrl, "Process")
[Environment]::SetEnvironmentVariable("LLM_MODEL", $Model, "Process")
[Environment]::SetEnvironmentVariable("LLM_API_KEY", $apiKey.Value, "Process")
if ($null -ne $openHandsSessionKey) {
  [Environment]::SetEnvironmentVariable("OPENHANDS_SESSION_API_KEY", $openHandsSessionKey.Value, "Process")
}
[Environment]::SetEnvironmentVariable("NO_PROXY", "127.0.0.1,localhost,::1", "Process")
[Environment]::SetEnvironmentVariable("no_proxy", "127.0.0.1,localhost,::1", "Process")

$cargo = (Get-Command cargo).Source
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
  foreach ($attempt in 1..120) {
    try {
      $health = Invoke-RestMethod -Method Get -Uri "$base/api/v3/health"
      break
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  if ($null -eq $health -or $health.status -ne "ok") {
    throw "Rust v3 health check failed. See $errLog"
  }

  $jsonHeaders = @{ "Content-Type" = "application/json" }

  $providerBaseUrls = @{}
  $providerBaseUrls[$normalizedProvider] = $BaseUrl
  $providerProxyUrls = @{}
  if (-not [string]::IsNullOrWhiteSpace($ProviderProxyUrl)) {
    $providerProxyUrls[$normalizedProvider] = $ProviderProxyUrl
  }
  $providerApiKeys = @{}
  $providerApiKeys[$normalizedProvider] = $apiKey.Value
  $providerSettingsBody = ConvertTo-JsonBody @{
    default_provider = $normalizedProvider
    default_model = $Model
    base_urls = $providerBaseUrls
    proxy_urls = $providerProxyUrls
    api_keys = $providerApiKeys
    mock_mode = $false
  }
  $providerSettings = Invoke-RestJsonWithRetry -Method Post -Uri "$base/api/v3/providers/settings" -Headers $jsonHeaders -Body $providerSettingsBody
  Assert-Smoke ($providerSettings.status.default_status.credential_configured -eq $true) "Provider Settings did not detect configured credentials."

  $providerTest = Invoke-RestJsonWithRetry -Method Post -Uri "$base/api/v3/providers/test" -Headers $jsonHeaders -Body (ConvertTo-JsonBody @{
    provider = $normalizedProvider
    mock = $false
  })
  Assert-Smoke ($providerTest.test.ok -eq $true) "Live provider test failed: $($providerTest.test.message)"
  Assert-Smoke ($providerTest.test.mode -eq "live") "Provider test did not use live mode."

  $openHandsSettingsBody = @{
    enabled = $true
    server_url = $OpenHandsServerUrl
    workspace_mode = "local"
    allow_native_fallback = $false
  }
  if ($null -ne $openHandsSessionKey) {
    $openHandsSettingsBody["session_api_key"] = $openHandsSessionKey.Value
  }
  $openHandsSettings = Invoke-RestJsonWithRetry -Method Post -Uri "$base/api/v3/openhands/settings" -Headers $jsonHeaders -Body (ConvertTo-JsonBody $openHandsSettingsBody)
  Assert-Smoke ($openHandsSettings.status.status -eq "connected") "OpenHands Settings test did not connect: $($openHandsSettings.status.detail)"

  $defaultWorkflow = Invoke-RestJsonWithRetry -Method Get -Uri "$base/api/v3/workflows/default"
  $config = $defaultWorkflow.config
  $config.workflows."planner-led".max_rounds = 1
  $config.workflows."planner-led".edges = @(
    @{
      from = "planner"
      to = "executor"
      on = "ready"
    }
  )
  $config.harnesses."openhands-code-edit".openhands.prefer_websocket = $false
  $config.harnesses."openhands-code-edit".openhands.poll_interval_ms = 1000
  $config.harnesses."openhands-code-edit".openhands.max_event_poll_seconds = 300
  $config.harnesses."openhands-code-edit".openhands.max_events = 100
  $config.harnesses."openhands-code-edit".openhands.api_paths = @{
    api_prefix = "/api"
    events_search_path = "/conversations/{conversation_id}/events/search"
    run_endpoint_path = "/conversations/{conversation_id}/run"
    websocket_path_template = "/sockets/events/{conversation_id}"
    auth_header = "x_session_api_key"
  }
  $config.harnesses."openhands-code-edit".openhands.run_start_strategy = "post_run_endpoint"

  $sessionResponse = Invoke-RestJsonWithRetry -Method Post -Uri "$base/api/v3/planner-chat/sessions" -Headers $jsonHeaders -Body (ConvertTo-JsonBody @{
    workflow_id = $defaultWorkflow.workflow_id
    planner_agent_id = "planner"
    config = $config
    mode = "discuss"
  })
  $sessionId = $sessionResponse.session.session_id
  Assert-Smoke (-not [string]::IsNullOrWhiteSpace($sessionId)) "Planner session creation did not return session_id."

  function Send-PlannerTurn {
    param(
      [string]$Message,
      [bool]$Confirmed,
      [string]$Mode = "discuss"
    )
    Invoke-RestJsonWithRetry -Method Post -Uri "$base/api/v3/planner-chat/sessions/$sessionId/turn" -Headers $jsonHeaders -Body (ConvertTo-JsonBody @{
      message = $Message
      confirmed = $Confirmed
      mode = $Mode
      planner_agent_id = "planner"
      config = $config
    })
  }

  $firstTurn = Send-PlannerTurn -Message "Live full path smoke: plan a documentation-only update to docs/FULL_PATH_SMOKE_RESULT.md. OpenHands must leave the change uncommitted for Coder Review Changes and Undo verification. Do not start work yet." -Confirmed $false
  Assert-Smoke (-not [string]::IsNullOrWhiteSpace($firstTurn.assistant_message)) "First Planner turn did not return assistant text."
  Assert-Smoke ($firstTurn.should_start_workflow -eq $false) "First Planner turn unexpectedly requested execution."

  $secondTurn = Send-PlannerTurn -Message "Confirm the scope. Acceptance: OpenHands updates docs/FULL_PATH_SMOKE_RESULT.md, runs git status --short, timeline/final summary appear, Review Changes appears, and Undo works. Do not commit, push, publish, or clean the working tree. Leave docs/FULL_PATH_SMOKE_RESULT.md as an uncommitted change so Coder can verify Review Changes and Undo after execution." -Confirmed $true -Mode "work"
  Assert-Smoke (-not [string]::IsNullOrWhiteSpace($secondTurn.assistant_message)) "Second Planner turn did not return assistant text."
  Assert-Smoke ($secondTurn.should_start_workflow -eq $false) "Second Planner turn unexpectedly requested execution."
  Assert-Smoke (@($secondTurn.session.turns).Count -ge 4) "Planner did not retain two user/assistant turns."
  Assert-Smoke ($secondTurn.ready -eq $true) "Planner did not mark the plan ready."

  $startWork = Invoke-RestJsonWithRetry -Method Post -Uri "$base/api/v3/planner-chat/sessions/$sessionId/start-work" -Headers $jsonHeaders -Body (ConvertTo-JsonBody @{
    repo = $repoPath
    workflow_id = $defaultWorkflow.workflow_id
    planner_agent_id = "planner"
    config = $config
    scopes = @("docs/FULL_PATH_SMOKE_RESULT.md")
  })
  Assert-Smoke (-not [string]::IsNullOrWhiteSpace($startWork.run_id)) "Start Work did not return run_id: $($startWork | ConvertTo-Json -Depth 20)"
  Assert-Smoke ($startWork.status -eq "completed") "Start Work did not complete: $($startWork | ConvertTo-Json -Depth 20)"

  $runId = $startWork.run_id
  $events = Invoke-RestJsonWithRetry -Method Get -Uri "$base$($startWork.events_url)"
  $timeline = Invoke-RestJsonWithRetry -Method Get -Uri "$base$($startWork.timeline_url)"
  $timelineItems = @($timeline.items)
  Assert-Smoke ($timelineItems.Count -ge 1) "Timeline was empty."
  $backendItems = @($timelineItems | Where-Object { $_.title -eq "Executor backend: OpenHands" })
  Assert-Smoke ($backendItems.Count -ge 1) "Timeline did not show Executor backend: OpenHands."
  $reactItems = @($timelineItems | Where-Object {
    $_.type -in @("reasoning", "tool", "command_execution", "file_change", "executor_step")
  })
  Assert-Smoke ($reactItems.Count -ge 1) "Timeline did not include public ReAct items."
  $finalItems = @($timelineItems | Where-Object { $_.type -eq "final_summary" })
  Assert-Smoke ($finalItems.Count -ge 1) "Timeline did not include final summary."

  $report = Invoke-RestJsonWithRetry -Method Get -Uri "$base/api/v3/runs/$runId/report/preview"
  Assert-Smoke ($report.report.status -eq "completed") "Final report preview did not complete."

  $gitStatus = @(git -C $repoPath status --porcelain)
  $resultDocChanged = @($gitStatus | Where-Object { $_ -match "docs/FULL_PATH_SMOKE_RESULT\.md$" })
  $resultDocText = [System.IO.File]::ReadAllText($resultDocPath)
  Assert-Smoke ($resultDocText -ne $initialResultDoc) "OpenHands did not update docs/FULL_PATH_SMOKE_RESULT.md content."
  if ($resultDocChanged.Count -lt 1) {
    $headFiles = @(git -C $repoPath show --name-only --format="" HEAD)
    if ($headFiles -contains "docs/FULL_PATH_SMOKE_RESULT.md") {
      throw "OpenHands committed docs/FULL_PATH_SMOKE_RESULT.md; expected an uncommitted diff for Review Changes and Undo."
    }
  }
  Assert-Smoke ($resultDocChanged.Count -ge 1) "OpenHands updated docs/FULL_PATH_SMOKE_RESULT.md content, but did not leave an uncommitted diff."

  $changes = Invoke-RestJsonWithRetry -Method Get -Uri "$base/api/v3/runs/$runId/changes"
  $changeSets = @($changes.changes)
  Assert-Smoke ($changeSets.Count -ge 1) "Review Changes returned no change set."
  $changeSetId = $changeSets[0].change_set_id
  $diff = Invoke-RestJsonWithRetry -Method Get -Uri "$base/api/v3/runs/$runId/changes/$changeSetId/diff"
  Assert-Smoke ($diff.diff.Contains("FULL_PATH_SMOKE_RESULT.md")) "Review diff did not mention FULL_PATH_SMOKE_RESULT.md."
  $undo = Invoke-RestJsonWithRetry -Method Post -Uri "$base/api/v3/runs/$runId/changes/$changeSetId/undo"
  Assert-Smoke ($undo.status -eq "undone" -or $undo.status -eq "unsupported" -or $undo.status -eq "conflict") "Undo returned unexpected status: $($undo.status)"

  $eventsPath = Join-Path $storePath "runs\$runId\events.jsonl"
  $reportPath = Join-Path $storePath "runs\$runId\artifacts\final-report.json"
  $serialized = Get-SerializedArtifactsText -Objects @($providerSettings, $providerTest, $openHandsSettings, $firstTurn, $secondTurn, $startWork, $events, $timeline, $report, $changes, $diff, $undo) -Files @($eventsPath, $reportPath)
  Assert-NoSecretLeak -Text $serialized -Secrets @($apiKey, $openHandsSessionKey)

  [pscustomobject]@{
    status = "ok"
    validation = "live_full_path_api"
    provider = $normalizedProvider
    model = $Model
    provider_test = $providerTest.test.mode
    openhands_status = $openHandsSettings.status.status
    server_url = $OpenHandsServerUrl
    session_id = $sessionId
    turns = @($secondTurn.session.turns).Count
    run_id = $runId
    start_work_status = $startWork.status
    events = @($events.events).Count
    timeline_items = $timelineItems.Count
    timeline_backend_items = $backendItems.Count
    timeline_react_items = $reactItems.Count
    final_summary_items = $finalItems.Count
    report_status = $report.report.status
    result_doc_changed = $resultDocChanged.Count
    review_changes = $changeSets.Count
    undo_status = $undo.status
    secrets_check = "passed"
    repo = $repoPath
    store = $storePath
  } | ConvertTo-Json -Depth 20
} finally {
  if ($server -and -not $server.HasExited) {
    Stop-Process -Id $server.Id -Force
  }
}
