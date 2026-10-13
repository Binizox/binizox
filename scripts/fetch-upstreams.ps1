$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$UpstreamRoot = Join-Path $ProjectRoot 'upstreams'
New-Item -ItemType Directory -Path $UpstreamRoot -Force | Out-Null

$Repositories = @(
    # 这里保留真实上游名称与 URL；它是来源快照，不是 Binizox 运行包。
    @{ Name = 'yuxi'; Url = 'https://github.com/xerrors/Yuxi.git'; Commit = '2def1d3ad8a7359168639acfc1494a481f6dd55d' },
    @{ Name = 'ragflow'; Url = 'https://github.com/infiniflow/ragflow.git'; Commit = '313ca90f6abd7682fe8523e16fd67b3653a3fa84' },
    @{ Name = 'weknora'; Url = 'https://github.com/Tencent/WeKnora.git'; Commit = '4df7ccbb4f650082331452a92b52854f8922da2a' },
    @{ Name = 'deer-flow'; Url = 'https://github.com/bytedance/deer-flow.git'; Commit = 'bf9a019f28dbf4af106096ad3dca38452a8dd7e4' },
    @{ Name = 'librechat'; Url = 'https://github.com/LibreChat-AI/LibreChat.git'; Commit = '7b2362d7a7c6148b84850924dc7fa5fc43307923' },
    @{ Name = 'deepseek-harness'; Url = 'https://github.com/deepseek-ai/deepseek-harness.git'; Commit = '477b4f420553e8a52c2fbccc464d7561b239c443' }
)

foreach ($repository in $Repositories) {
    $target = Join-Path $UpstreamRoot $repository.Name
    if (Test-Path -LiteralPath (Join-Path $target '.git')) {
        $actual = (git -C $target rev-parse HEAD).Trim()
        if ($actual -ne $repository.Commit) {
            throw "$($repository.Name) 已存在但 commit 不一致：$actual"
        }
        Write-Host "$($repository.Name) 已核验：$actual"
        continue
    }
    if (Test-Path -LiteralPath $target) {
        throw "$target 已存在但不是 Git 仓库，为避免覆盖请先人工处理。"
    }

    git init $target
    git -C $target remote add origin $repository.Url
    git -C $target fetch --depth 1 origin $repository.Commit
    git -C $target checkout --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "$($repository.Name) 获取失败。" }
}
