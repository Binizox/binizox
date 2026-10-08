$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Push-Location (Join-Path $ProjectRoot 'web')
try {
    if (-not (Test-Path 'node_modules')) {
        conda run --name binizox-dev corepack pnpm@11.24.0 install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Binizox Vue 依赖安装失败。' }
    }
    conda run --name binizox-dev corepack pnpm@11.24.0 dev --host 127.0.0.1 --port 5173
    if ($LASTEXITCODE -ne 0) { throw 'Binizox Vue 开发服务退出。' }
} finally {
    Pop-Location
}
