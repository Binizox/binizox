$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'BinizoxDev.Common.ps1')
Import-BinizoxEnvironment -Path (Join-Path $ProjectRoot '.env.binizox.local')
$env:PYTHONPATH = "$ProjectRoot\backend;$ProjectRoot\backend\package"
$env:BINIZOX_TOOL_RUNNER_URL = 'http://127.0.0.1:8091'
$env:BINIZOX_PARSER_URL = 'http://127.0.0.1:8090'
$env:BINIZOX_USER_DATA_DIR = Join-Path $ProjectRoot '.runtime\binizox\user-data'

Push-Location (Join-Path $ProjectRoot 'backend')
try {
    conda run --name binizox-dev arq server.worker_main.WorkerSettings
} finally {
    Pop-Location
}
