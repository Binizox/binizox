$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:BINIZOX_WORKSPACE_ROOT = Join-Path $ProjectRoot '.runtime\binizox\workspace'
$env:BINIZOX_TOOL_STATE_PATH = Join-Path $ProjectRoot '.runtime\binizox\tool-runner.sqlite3'

Push-Location (Join-Path $ProjectRoot 'services\personal-tool-runner')
try {
    conda run --name binizox-dev uvicorn app.main:app --host 127.0.0.1 --port 8091 --reload
} finally {
    Pop-Location
}
