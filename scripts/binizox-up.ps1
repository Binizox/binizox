$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$EnvFile = Join-Path $ProjectRoot '.env'

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw '缺少 .env。请根据 .env.binizox.example 与 Binizox 原始 .env.template 创建本地配置。'
}

docker compose --project-directory $ProjectRoot --env-file $EnvFile `
    -f (Join-Path $ProjectRoot 'docker-compose.yml') `
    -f (Join-Path $ProjectRoot 'docker-compose.binizox.yml') `
    up --build -d
if ($LASTEXITCODE -ne 0) { throw 'Binizox Docker 全栈启动失败。' }
