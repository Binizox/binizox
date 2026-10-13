param(
    [string]$SourceProjectEnv = 'D:\Download\AsterDesk\apps\platform\.env',
    [string]$SourcePhaseState = 'D:\Download\AsterDesk\.runtime\phase5',
    [string]$TargetProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference = 'Stop'

function ConvertTo-BinizoxKey {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($Name.StartsWith('YUXI_')) {
        return 'BINIZOX_' + $Name.Substring('YUXI_'.Length)
    }
    return $Name
}

function Read-EnvMap {
    param([Parameter(Mandatory = $true)][string]$Path)

    $result = [ordered]@{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $result
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($rawLine -notmatch '^\s*([^#=]+)=(.*)$') {
            continue
        }
        $name = ConvertTo-BinizoxKey -Name $Matches[1].Trim()
        $result[$name] = $Matches[2]
    }
    return $result
}

function Test-PlaceholderValue {
    param([AllowEmptyString()][string]$Value)

    return [string]::IsNullOrWhiteSpace($Value) -or $Value.Trim() -match '^(change-me|change-me-local-only|replace-with-.*)$'
}

function New-RandomHexSecret {
    $bytes = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToHexString($bytes).ToLowerInvariant()
}

function Merge-MissingValues {
    param(
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Target,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Source
    )

    foreach ($name in $Source.Keys) {
        $value = [string]$Source[$name]
        if (Test-PlaceholderValue -Value $value) {
            continue
        }
        if (-not $Target.Contains($name) -or (Test-PlaceholderValue -Value ([string]$Target[$name]))) {
            $Target[$name] = $value
        }
    }
}

function Copy-EnvMap {
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Source)

    $copy = [ordered]@{}
    foreach ($name in $Source.Keys) {
        $copy[$name] = $Source[$name]
    }
    return $copy
}

function Write-EnvFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Values,
        [Parameter(Mandatory = $true)][string]$BackupDirectory
    )

    $sourceLines = @()
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $sourceLines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
        Copy-Item -LiteralPath $Path -Destination (Join-Path $BackupDirectory ([IO.Path]::GetFileName($Path)))
    }

    $seen = New-Object 'System.Collections.Generic.HashSet[string]'
    $output = New-Object 'System.Collections.Generic.List[string]'
    foreach ($rawLine in $sourceLines) {
        if ($rawLine -notmatch '^\s*([^#=]+)=(.*)$') {
            $output.Add($rawLine)
            continue
        }

        $name = ConvertTo-BinizoxKey -Name $Matches[1].Trim()
        if (-not $seen.Add($name)) {
            continue
        }
        $value = if ($Values.Contains($name)) { [string]$Values[$name] } else { $Matches[2] }
        $output.Add("$name=$value")
    }

    foreach ($name in $Values.Keys) {
        if ($seen.Add([string]$name)) {
            $output.Add("$name=$($Values[$name])")
        }
    }

    [IO.File]::WriteAllLines($Path, $output, [Text.UTF8Encoding]::new($false))
}

function Copy-StateDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )

    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        return [pscustomobject]@{ Source = $Source; Target = $Target; Status = 'source-missing'; Files = 0 }
    }
    if (Test-Path -LiteralPath $Target -PathType Container) {
        $existing = @(Get-ChildItem -LiteralPath $Target -Force -ErrorAction Stop)
        if ($existing.Count -gt 0) {
            return [pscustomobject]@{ Source = $Source; Target = $Target; Status = 'target-not-empty'; Files = 0 }
        }
    } else {
        New-Item -ItemType Directory -Path $Target -Force | Out-Null
    }

    $sourceRoot = (Resolve-Path -LiteralPath $Source).Path.TrimEnd('\')
    $copied = 0
    foreach ($directory in Get-ChildItem -LiteralPath $sourceRoot -Directory -Recurse -Force) {
        $relative = $directory.FullName.Substring($sourceRoot.Length).TrimStart('\')
        New-Item -ItemType Directory -Path (Join-Path $Target $relative) -Force | Out-Null
    }
    foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -File -Recurse -Force) {
        # PostgreSQL 的 postmaster.pid 只描述旧进程，复制后会导致新实例误判仍在运行。
        if ($file.Name -eq 'postmaster.pid') {
            continue
        }
        $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')
        $destination = Join-Path $Target $relative
        $parent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination
        $copied += 1
    }

    return [pscustomobject]@{ Source = $Source; Target = $Target; Status = 'copied'; Files = $copied }
}

$targetEnv = Join-Path $TargetProjectRoot '.env'
$targetLocalEnv = Join-Path $TargetProjectRoot '.env.binizox.local'
$targetLocalExample = Join-Path $TargetProjectRoot '.env.binizox.example'
$sourcePhaseEnv = Join-Path $SourcePhaseState 'phase5.env'
$runtimeRoot = Join-Path $TargetProjectRoot '.runtime\binizox'
$targetStateRoot = Join-Path $runtimeRoot 'full'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$migrationDirectory = Join-Path (Join-Path $TargetProjectRoot '.runtime\migrations') "binizox-$timestamp"
New-Item -ItemType Directory -Path $migrationDirectory -Force | Out-Null

$values = Read-EnvMap -Path $targetEnv
Merge-MissingValues -Target $values -Source (Read-EnvMap -Path $SourceProjectEnv)
$phaseValues = Read-EnvMap -Path $sourcePhaseEnv

# 与 Phase 5 数据库一起迁移的身份和派生密钥必须保持一致，不能继续使用示例占位值。
$phaseIdentityKeys = @(
    'JWT_SECRET_KEY',
    'API_KEY_DERIVATION_SECRET',
    'SANDBOX_PROVISIONER_TOKEN',
    'BINIZOX_INSTANCE_ID'
)
foreach ($name in $phaseIdentityKeys) {
    if ($phaseValues.Contains($name) -and -not (Test-PlaceholderValue -Value ([string]$phaseValues[$name]))) {
        $values[$name] = $phaseValues[$name]
    }
}
$phaseToolRunnerToken = [string]$phaseValues['BINIZOX_TOOL_RUNNER_TOKEN']
if (
    (-not $values.Contains('BINIZOX_TOOL_RUNNER_TOKEN') -or
        (Test-PlaceholderValue -Value ([string]$values['BINIZOX_TOOL_RUNNER_TOKEN']))) -and
    -not (Test-PlaceholderValue -Value $phaseToolRunnerToken)
) {
    $values['BINIZOX_TOOL_RUNNER_TOKEN'] = $phaseToolRunnerToken
}
$toolRunnerTokenStatus = 'preserved'
$otherSecuritySecrets = @(
    [string]$values['JWT_SECRET_KEY'],
    [string]$values['API_KEY_DERIVATION_SECRET'],
    [string]$values['SANDBOX_PROVISIONER_TOKEN']
)
if (
    -not $values.Contains('BINIZOX_TOOL_RUNNER_TOKEN') -or
    (Test-PlaceholderValue -Value ([string]$values['BINIZOX_TOOL_RUNNER_TOKEN'])) -or
    $otherSecuritySecrets -contains ([string]$values['BINIZOX_TOOL_RUNNER_TOKEN'])
) {
    do {
        $generatedToolRunnerToken = New-RandomHexSecret
    } while ($otherSecuritySecrets -contains $generatedToolRunnerToken)
    $values['BINIZOX_TOOL_RUNNER_TOKEN'] = $generatedToolRunnerToken
    $toolRunnerTokenStatus = 'generated'
}
foreach ($name in @('POSTGRES_PASSWORD', 'MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY', 'NEO4J_PASSWORD')) {
    if ($phaseValues.Contains($name) -and -not (Test-PlaceholderValue -Value ([string]$phaseValues[$name]))) {
        $values[$name] = $phaseValues[$name]
    }
}

$values['COMPOSE_PROJECT_NAME'] = 'binizox'
$values['BINIZOX_ENV'] = 'development'
$values['BINIZOX_STATE_DIR'] = './.runtime/binizox/full'
$values['BINIZOX_POSTGRES_USER'] = 'postgres'
$values['BINIZOX_POSTGRES_DB'] = 'postgres'
$defaultPorts = [ordered]@{
    BINIZOX_POSTGRES_PORT = '55432'
    BINIZOX_REDIS_PORT = '56379'
    BINIZOX_MINIO_PORT = '59000'
    BINIZOX_MINIO_CONSOLE_PORT = '59001'
}
foreach ($name in $defaultPorts.Keys) {
    if (-not $values.Contains($name)) {
        $values[$name] = $defaultPorts[$name]
    }
}
$values['BINIZOX_POSTGRES_PASSWORD'] = $values['POSTGRES_PASSWORD']
$values['BINIZOX_MINIO_ACCESS_KEY'] = $values['MINIO_ACCESS_KEY']
$values['BINIZOX_MINIO_SECRET_KEY'] = $values['MINIO_SECRET_KEY']

$encodedPassword = [Uri]::EscapeDataString([string]$values['POSTGRES_PASSWORD'])
$composeValues = Copy-EnvMap -Source $values
$composeValues['POSTGRES_URL'] = "postgresql+asyncpg://postgres:$encodedPassword@postgres:5432/postgres"
$composeValues['REDIS_URL'] = 'redis://redis:6379/0'
$composeValues['MINIO_URI'] = 'http://minio:9000'

$localValues = Copy-EnvMap -Source $values
$localPostgresPort = $values['BINIZOX_POSTGRES_PORT']
$localValues['POSTGRES_URL'] = "postgresql+asyncpg://postgres:$encodedPassword@127.0.0.1:$localPostgresPort/postgres"
$localValues['REDIS_URL'] = "redis://127.0.0.1:$($values['BINIZOX_REDIS_PORT'])/0"
$localValues['MINIO_URI'] = "http://127.0.0.1:$($values['BINIZOX_MINIO_PORT'])"

if (-not (Test-Path -LiteralPath $targetLocalEnv -PathType Leaf)) {
    Copy-Item -LiteralPath $targetLocalExample -Destination $targetLocalEnv
}
Write-EnvFile -Path $targetEnv -Values $composeValues -BackupDirectory $migrationDirectory
Write-EnvFile -Path $targetLocalEnv -Values $localValues -BackupDirectory $migrationDirectory

$legacyCliConfig = Join-Path $env:USERPROFILE '.yuxi\config.toml'
$binizoxCliConfig = Join-Path $env:USERPROFILE '.binizox\config.toml'
$cliConfigStatus = 'source-missing'
if (Test-Path -LiteralPath $legacyCliConfig -PathType Leaf) {
    if (Test-Path -LiteralPath $binizoxCliConfig -PathType Leaf) {
        $cliConfigStatus = 'target-exists'
    } else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $binizoxCliConfig) -Force | Out-Null
        Copy-Item -LiteralPath $legacyCliConfig -Destination $binizoxCliConfig
        $cliConfigStatus = 'copied'
    }
}

$stateMappings = @(
    @{ Source = 'postgresql'; Target = 'postgresql' },
    @{ Source = 'redis'; Target = 'redis' },
    @{ Source = 'milvus'; Target = 'milvus' },
    @{ Source = 'yuxi'; Target = 'binizox' }
)
$results = @(
    foreach ($mapping in $stateMappings) {
        Copy-StateDirectory `
            -Source (Join-Path $SourcePhaseState $mapping.Source) `
            -Target (Join-Path $targetStateRoot $mapping.Target)
    }
)

$manifest = New-Object 'System.Collections.Generic.List[string]'
$manifest.Add("timestamp=$timestamp")
$manifest.Add("source_phase=$SourcePhaseState")
$manifest.Add("target_state=$targetStateRoot")
$manifest.Add('secrets=redacted')
$manifest.Add("tool_runner_token=$toolRunnerTokenStatus")
$manifest.Add("cli_config=$cliConfigStatus")
foreach ($result in $results) {
    $manifest.Add("state=$($result.Status);files=$($result.Files);source=$($result.Source);target=$($result.Target)")
}
[IO.File]::WriteAllLines((Join-Path $migrationDirectory 'manifest.txt'), $manifest, [Text.UTF8Encoding]::new($false))

Write-Output "Binizox 本地迁移完成。证据目录：$migrationDirectory"
foreach ($result in $results) {
    Write-Output "$($result.Status): $($result.Source) -> $($result.Target) ($($result.Files) files)"
}
