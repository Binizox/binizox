$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Push-Location (Join-Path $ProjectRoot 'services\parser-sidecar')
try {
    conda run --name binizox-parser uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
} finally {
    Pop-Location
}
