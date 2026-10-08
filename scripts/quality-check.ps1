param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Push-Location $ProjectRoot
try {
    conda run --name binizox-dev ruff check `
        services/personal-tool-runner `
        backend/package/yuxi/binizox `
        backend/package/yuxi/asterdesk/document_service.py `
        backend/package/yuxi/agents/toolkits/binizox.py `
        backend/server/routers/binizox_router.py `
        backend/test/unit/binizox
    if ($LASTEXITCODE -ne 0) { throw 'Binizox Python 静态检查失败。' }

    conda run --name binizox-dev pytest -q services/personal-tool-runner/test
    if ($LASTEXITCODE -ne 0) { throw '个人工具服务测试失败。' }

    $env:PYTHONPATH = (Join-Path $ProjectRoot 'services\parser-sidecar')
    conda run --name binizox-parser pytest -q services/parser-sidecar/test
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) { throw '解析服务测试失败。' }

    $env:PYTHONPATH = (Join-Path $ProjectRoot 'backend\package')
    conda run --name binizox-dev pytest -q backend/test/unit/binizox/test_integrations_and_tool_policy.py
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) { throw 'Binizox 后端契约测试失败。' }

    conda run --name binizox-dev python scripts/verify_engineering_contracts.py
    if ($LASTEXITCODE -ne 0) { throw '工程契约检查失败。' }
    conda run --name binizox-dev python -m unittest scripts.test_verify_engineering_contracts
    if ($LASTEXITCODE -ne 0) { throw '工程契约负向测试失败。' }

    if (-not $SkipFrontend) {
        Push-Location (Join-Path $ProjectRoot 'web')
        try {
            conda run --name binizox-dev corepack pnpm@11.24.0 run lint:check
            if ($LASTEXITCODE -ne 0) { throw 'Vue lint 失败。' }
            conda run --name binizox-dev corepack pnpm@11.24.0 run test:unit
            if ($LASTEXITCODE -ne 0) { throw 'Vue 单元测试失败。' }
            conda run --name binizox-dev corepack pnpm@11.24.0 run build
            if ($LASTEXITCODE -ne 0) { throw 'Vue 构建失败。' }
        } finally {
            Pop-Location
        }
    }

    Write-Host 'Binizox 质量检查通过。'
} finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Pop-Location
}
