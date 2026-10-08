$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LocalEnv = Join-Path $ProjectRoot '.env.binizox.local'

if (-not (Test-Path -LiteralPath $LocalEnv)) {
    throw '缺少 .env.binizox.local。请复制 .env.binizox.example 并仅在本地填写开发凭据。'
}

docker compose --project-directory $ProjectRoot --env-file $LocalEnv `
    -f (Join-Path $ProjectRoot 'docker-compose.binizox-infra.yml') up -d
if ($LASTEXITCODE -ne 0) { throw 'Binizox 基础设施启动失败。' }
