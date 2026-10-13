$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Read-TestEnv {
    param([Parameter(Mandatory = $true)][string]$Path)

    $result = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^([^#=]+)=(.*)$') {
            $result[$Matches[1].Trim()] = $Matches[2]
        }
    }
    return $result
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$migrationScript = Join-Path $PSScriptRoot 'migrate-binizox-local-state.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("binizox-migration-test-" + [Guid]::NewGuid().ToString('N'))
$sourceRoot = Join-Path $testRoot 'source'
$sourceState = Join-Path $sourceRoot 'phase5'
$targetRoot = Join-Path $testRoot 'target'
$originalUserProfile = $env:USERPROFILE

try {
    New-Item -ItemType Directory -Path $sourceState, $targetRoot -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $sourceState 'postgresql') -Force | Out-Null
    [IO.File]::WriteAllText(
        (Join-Path $sourceRoot '.env'),
        "POSTGRES_PASSWORD=db-secret-for-test`nMINIO_ACCESS_KEY=minio-user-for-test`nMINIO_SECRET_KEY=minio-secret-for-test`nNEO4J_PASSWORD=neo4j-secret-for-test`n",
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        (Join-Path $sourceState 'phase5.env'),
        "JWT_SECRET_KEY=jwt-secret-for-test`nAPI_KEY_DERIVATION_SECRET=api-secret-for-test`nSANDBOX_PROVISIONER_TOKEN=sandbox-secret-for-test`nBINIZOX_TOOL_RUNNER_TOKEN=jwt-secret-for-test`n",
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        (Join-Path $targetRoot '.env.binizox.example'),
        "BINIZOX_TOOL_RUNNER_TOKEN=change-me-local-only`n",
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        (Join-Path $sourceState 'postgresql\sample.dat'),
        'migration-state-test',
        [Text.UTF8Encoding]::new($false)
    )

    $env:USERPROFILE = Join-Path $testRoot 'profile'
    New-Item -ItemType Directory -Path $env:USERPROFILE -Force | Out-Null
    $firstOutput = & $migrationScript `
        -SourceProjectEnv (Join-Path $sourceRoot '.env') `
        -SourcePhaseState $sourceState `
        -TargetProjectRoot $targetRoot | Out-String

    $composeEnv = Read-TestEnv -Path (Join-Path $targetRoot '.env')
    $localEnv = Read-TestEnv -Path (Join-Path $targetRoot '.env.binizox.local')
    $token = [string]$composeEnv['BINIZOX_TOOL_RUNNER_TOKEN']
    Assert-True ($token -match '^[a-f0-9]{64}$') '缺失或复用的 Tool Runner token 必须生成 32 字节随机十六进制值'
    Assert-True ($localEnv['BINIZOX_TOOL_RUNNER_TOKEN'] -eq $token) 'Compose 与本地环境必须使用同一个迁移后 token'
    foreach ($secretName in @('JWT_SECRET_KEY', 'API_KEY_DERIVATION_SECRET', 'SANDBOX_PROVISIONER_TOKEN')) {
        Assert-True ($token -ne $composeEnv[$secretName]) "Tool Runner token 不得复用 $secretName"
        Assert-True (-not $firstOutput.Contains([string]$composeEnv[$secretName])) "迁移输出不得泄露 $secretName"
    }
    Assert-True (-not $firstOutput.Contains($token)) '迁移输出不得泄露 Tool Runner token'
    Assert-True (Test-Path -LiteralPath (Join-Path $targetRoot '.runtime\binizox\full\postgresql\sample.dat')) '状态文件未复制'

    Start-Sleep -Milliseconds 1100
    $secondOutput = & $migrationScript `
        -SourceProjectEnv (Join-Path $sourceRoot '.env') `
        -SourcePhaseState $sourceState `
        -TargetProjectRoot $targetRoot | Out-String
    $secondEnv = Read-TestEnv -Path (Join-Path $targetRoot '.env')
    Assert-True ($secondEnv['BINIZOX_TOOL_RUNNER_TOKEN'] -eq $token) '重复迁移必须保留已经生成的独立 token'
    Assert-True (-not $secondOutput.Contains($token)) '重复迁移输出不得泄露 Tool Runner token'

    Write-Output 'Binizox local migration contract passed.'
}
finally {
    $env:USERPROFILE = $originalUserProfile
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
