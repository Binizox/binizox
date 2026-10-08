$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Key = "smoke-$([Guid]::NewGuid().ToString('N'))"
$RelativePath = "smoke/$Key.md"
$Body = @{
    run_id = 'local-smoke-run'
    tool_name = 'workspace.write_note'
    parameters = @{
        relative_path = $RelativePath
        content = "# Binizox 本地冒烟测试`n"
        source_citations = @('本地测试证据')
    }
    idempotency_key = $Key
} | ConvertTo-Json -Depth 5

$Health = Invoke-RestMethod 'http://127.0.0.1:8091/health'
$First = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8091/v1/invocations' `
    -ContentType 'application/json' -Body $Body
$Replay = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8091/v1/invocations' `
    -ContentType 'application/json' -Body $Body
$Target = Join-Path $ProjectRoot ".runtime\binizox\workspace\$($RelativePath.Replace('/', '\'))"

if ($Health.status -ne 'ok') { throw '工具服务健康检查失败。' }
if ($First.status -ne 'succeeded') { throw '首次写笔记失败。' }
if (-not $Replay.idempotent_replay) { throw '重复调用没有返回幂等重放。' }
if (-not (Test-Path -LiteralPath $Target)) { throw "未找到输出文件：$Target" }

Write-Host "Binizox 冒烟测试通过：$Target"
