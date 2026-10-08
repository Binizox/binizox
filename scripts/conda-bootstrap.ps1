param(
    [switch]$InstallPlatform
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$EnvironmentName = 'binizox-dev'
$ParserEnvironmentName = 'binizox-parser'

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw '未找到 conda，请先安装 Miniconda 或 Anaconda。'
}

Write-Host '正在创建或更新 Binizox Conda 环境...'
conda env update --name $EnvironmentName --file (Join-Path $ProjectRoot 'environment.yml') --prune
if ($LASTEXITCODE -ne 0) { throw 'Conda 环境更新失败。' }

Write-Host '正在安装个人工具服务及测试依赖...'
conda run --name $EnvironmentName python -m pip install -e `
    "$ProjectRoot\services\personal-tool-runner[dev]"
if ($LASTEXITCODE -ne 0) { throw '个人工具服务依赖安装失败。' }

Write-Host '正在创建或更新独立解析环境...'
conda env update --name $ParserEnvironmentName `
    --file (Join-Path $ProjectRoot 'environment.parser.yml') --prune
if ($LASTEXITCODE -ne 0) { throw '解析服务 Conda 环境更新失败。' }

conda run --name $ParserEnvironmentName python -m pip install `
    -r (Join-Path $ProjectRoot 'services\parser-sidecar\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw '解析服务依赖安装失败。' }

if ($InstallPlatform) {
    Write-Host '正在安装完整 Yuxi/Binizox 后端，首次执行可能耗时较长...'
    Push-Location (Join-Path $ProjectRoot 'backend')
    try {
        conda run --name $EnvironmentName uv sync --active --group dev --group test
        if ($LASTEXITCODE -ne 0) { throw '完整后端依赖安装失败。' }
    } finally {
        Pop-Location
    }
}

Write-Host "环境准备完成：主环境 $EnvironmentName；解析环境 $ParserEnvironmentName"
