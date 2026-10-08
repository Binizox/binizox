$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$EnvFile = Join-Path $ProjectRoot '.env'

# 这里只停止容器，不使用 -v，个人数据、数据库和对象存储均保留。
docker compose --project-directory $ProjectRoot --env-file $EnvFile `
    -f (Join-Path $ProjectRoot 'docker-compose.yml') `
    -f (Join-Path $ProjectRoot 'docker-compose.binizox.yml') `
    stop
if ($LASTEXITCODE -ne 0) { throw 'Binizox Docker 服务停止失败。' }
