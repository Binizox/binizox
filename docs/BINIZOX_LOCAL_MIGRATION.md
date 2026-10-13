# Binizox 本地迁移记录

## 已执行迁移

2026-10-09 已从 AsterDesk Phase 5 隔离状态执行一次非破坏性迁移：

- `.env` 中的 `YUXI_*` 转换为 `BINIZOX_*`；
- 创建被 Git 忽略的 `.env.binizox.local`，供本地 Conda API/worker 使用；
- Compose `.env` 使用容器服务名，本地环境文件使用 `127.0.0.1`，避免容器内连接宿主回环地址；
- Phase 5 的 JWT、API Key 派生和 sandbox secret 被保留，但任何文档与迁移证据都不记录其内容；
- PostgreSQL、Redis、Milvus/MinIO 和线程/Skill 文件复制到 `.runtime/binizox/full`；
- 未复制旧 PostgreSQL 的 `postmaster.pid`；源目录没有删除或修改；
- VPN simulator 和 Phase 5 验收证据没有迁入个人 Agent 运行目录。

旧工程中的模型供应商 Key 与公开模板占位值相同，不属于可用凭据。迁移脚本没有虚构模型密钥；首次启动前仍需在被 Git 忽略的本地环境文件或产品配置页中填写自己的模型服务凭据。

迁移脚本：

```powershell
.\scripts\migrate-binizox-local-state.ps1
```

脚本遵循以下边界：

1. 修改环境文件前，备份到 `.runtime/migrations/binizox-<timestamp>/`；
2. 不在终端输出环境变量值；
3. 目标数据目录非空时跳过，不合并或覆盖数据库文件；
4. 所有源数据原地保留；
5. 生成不含密钥的 `manifest.txt`。

本次证据目录为 `.runtime/migrations/binizox-20261009-100925/`，它被 Git 忽略，仅保存在本机。

## 身份迁移规则

- Binizox 新 JWT 使用新的 issuer/audience，因此浏览器和 CLI 需要重新登录一次。
- 原 JWT secret 与 instance ID 已保留，数据库用户和密码哈希不需要重建。
- 新 API Key 使用 `bzkey_` 前缀和 Binizox 派生命名域。
- 已保存到迁入数据库的旧 `yxkey_` Key 仍可按哈希验证；已消费的 CLI 授权会话可通过旧命名域重建相同密钥。
- 兼容逻辑不签发旧前缀，后续确认所有客户端完成轮换后可以删除。

## Git remote

当前 `origin` 已设置为 `https://github.com/Binizox/binizox.git`，并保留 `asterdesk-source` 和 `yuxi-upstream` 作为来源追溯。需要更换个人远程仓库时执行：

```powershell
.\scripts\set-binizox-origin.ps1 -RepositoryUrl 'git@github.com:Binizox/binizox.git'
```

该脚本只新增或更新 `origin`，不会删除两个来源 remote。
不要把 token 嵌入 HTTPS URL；脚本会拒绝带 userinfo 的 URL。建议使用 Git Credential Manager 或 SSH。

## 尚未执行

本次只迁移文件和代码，没有启动 Docker、恢复 PostgreSQL WAL、执行 schema migration、登录或运行 Agent E2E。首次启动时应保留迁移目录，确认 PostgreSQL、Redis、MinIO、worker 和 API 均健康后再决定是否归档旧 Phase 数据。
