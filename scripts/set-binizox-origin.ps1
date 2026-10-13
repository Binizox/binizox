param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$RepositoryUrl
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if ($RepositoryUrl -notmatch '^(https://|ssh://|git@|[A-Za-z]:\\|\\\\)') {
    throw 'RepositoryUrl 必须是 HTTPS、SSH 或明确的本地仓库路径。'
}
if ($RepositoryUrl -match '^https://[^/]+@') {
    throw '不要把用户名、密码或 token 写进 remote URL；请使用凭据管理器或 SSH。'
}

Push-Location $ProjectRoot
try {
    $originExists = $null -ne (git remote | Where-Object { $_ -eq 'origin' })
    if ($originExists) {
        git remote set-url origin $RepositoryUrl
    } else {
        git remote add origin $RepositoryUrl
    }
    if ($LASTEXITCODE -ne 0) {
        throw '设置 Binizox origin 失败。'
    }

    Write-Output 'Binizox origin 已设置：'
    git remote -v
} finally {
    Pop-Location
}
