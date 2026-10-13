$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'BinizoxDev.Common.ps1')
Import-BinizoxEnvironment -Path (Join-Path $ProjectRoot '.env.binizox.local')
$env:BINIZOX_WORKSPACE_ROOT = Join-Path $ProjectRoot '.runtime\binizox\user-data'
$env:BINIZOX_TOOL_STATE_PATH = Join-Path $ProjectRoot '.runtime\binizox\tool-runner.sqlite3'

Push-Location (Join-Path $ProjectRoot 'services\personal-tool-runner')
try {
    conda run --name binizox-dev uvicorn app.main:app --host 127.0.0.1 --port 8091 --reload
} finally {
    Pop-Location
}
