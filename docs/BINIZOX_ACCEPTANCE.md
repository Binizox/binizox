# Binizox v0.1 本地验收记录

## 基线

- 仓库：`D:\Download\Binizox`
- 分支：`codex/binizox-mvp`
- Yuxi/AsterDesk 基线：`afea2c4bcacd760f8de36a90552218a94a8f0c72`（`asterdesk-phase4`）
- Python：Conda `binizox-dev` / `binizox-parser`，均为 Python 3.12
- 上游：六个研究快照均已核验到 `docs/BINIZOX_UPSTREAMS.md` 所列 commit

原 `D:\Download\AsterDesk` 未被修改，Phase 1–5 运行目录和数据卷未删除或迁移。

## 已通过验证

| 项目 | 命令 | 结果 |
|---|---|---|
| Personal Tool Runner 单元测试 | `conda run -n binizox-dev pytest -q services/personal-tool-runner/test` | `4 passed` |
| Parser sidecar 测试 | 设置 sidecar `PYTHONPATH` 后运行 `conda run -n binizox-parser pytest -q services/parser-sidecar/test` | `2 passed` |
| Binizox 集成、Skill 注册、检索边界与健康接口 | `conda run -n binizox-dev pytest -q backend/test/unit/binizox/test_integrations_and_tool_policy.py` | `7 passed` |
| Binizox 总览状态、API 边界、路由与导航 | `conda run -n binizox-dev corepack pnpm@11.24.0 --dir web run test:unit -- test/unit/binizox_overview.test.js` | `4 passed` |
| 完整本地质量脚本 | `scripts/quality-check.ps1` | Ruff、`4 + 2 + 7` 个 Python 测试、工程契约 gate 及其负向测试、Vue lint、全量 Vue unit 和 build 全部通过 |
| Vue lint | `pnpm run lint:check` | 通过 |
| Vue 单元测试 | `pnpm run test:unit` | 既有 `166` 项与新增 `4` 项全部通过 |
| Vue build | `pnpm run build` | 通过；只有已有的大 chunk 警告 |
| Personal Tool Runner HTTP 冒烟 | `scripts/dev-smoke.ps1` | 健康检查、首次写入、同键重放、文件存在均通过 |
| Compose 配置 | 合并 `docker-compose.yml` 与 `docker-compose.binizox.yml` 后执行 `config --quiet` | 通过 |
| 工程契约 gate | `conda run -n binizox-dev python scripts/verify_engineering_contracts.py` | 通过：61 decisions / 5 workflows / 4 AGENTS / 113 docs / 27 routers / 260 web sources |
| 工程契约负向测试 | `conda run -n binizox-dev python -m unittest scripts.test_verify_engineering_contracts` | `61 passed, 1 skipped`；跳过项为当前 Windows 账户无符号链接权限 |
| 本地登录页品牌检查 | Vite 启动后使用本地浏览器访问 | 实际 DOM 显示 `Binizox` 及 `© 2026 Binizox` |

真实冒烟测试在 `.runtime/binizox/workspace/smoke/` 写入 Markdown。该目录和 SQLite 状态均被 Git 忽略。

## 尚未在本轮运行

Docker Desktop 的 Linux Engine 未启动，访问 `npipe:////./pipe/dockerDesktopLinuxEngine` 失败。因此本轮没有启动最终全栈容器，也没有把“Compose 配置可解析”描述为“容器运行成功”。由于 API/认证不可用，登录后 `/binizox` 总览页的浅色、深色和 375px 窄屏视觉验收也未执行；这一项仅通过源码契约、lint 和 build，不计为真实页面验收。

完整 Yuxi 后端依赖较大，本轮没有执行 `conda-bootstrap.ps1 -InstallPlatform`，因此尚未在新仓库中完成需要模型配置、登录账号、PostgreSQL、Redis 和 MinIO 的真实 AgentRun E2E。相关串联代码、Skill、人工确认中间件注册和启动脚本已经落盘。

`save_binizox_note` 的来源引用目前由 Skill 提示词和工具参数契约约束，还没有在服务端将其与“当前 Run 真实返回的 Evidence ID”做强绑定。因此它是当前最小闭环的明确限制，不应宣称为已完成引用防伪。

## 用户可执行的最终验证

```powershell
Set-Location D:\Download\Binizox

# 1. 首次准备完整环境
.\scripts\conda-bootstrap.ps1 -InstallPlatform
Copy-Item .env.binizox.example .env.binizox.local
# 编辑本地文件，填写数据库、MinIO、认证及模型配置；不要提交。

# 2. 启动 Docker Desktop 后启动基础设施
.\scripts\dev-infra-up.ps1

# 3. 分别在终端启动
.\scripts\dev-parser.ps1
.\scripts\dev-tool-runner.ps1
.\scripts\dev-api.ps1
.\scripts\dev-worker.ps1
.\scripts\dev-web.ps1

# 4. 轻量 HTTP 验证
.\scripts\dev-smoke.ps1
```

进入 Vue 后创建/配置 Agent，启用 `binizox-personal-agent` Skill，上传 `examples/personal/personal-knowledge-workflow.md` 或示例 DOCX，完成索引后提问并要求保存笔记。预期 `save_binizox_note` 在真正写文件前弹出 Yuxi 既有工具确认框；批准后文件出现在 `.runtime/binizox/workspace`，拒绝时不写入。

最终容器验证使用：

```powershell
# 完整 Compose 沿用 Yuxi 的 .env，首次需先按 README 快速启动章节创建并填写它。
.\scripts\binizox-up.ps1
```

停止服务使用 `scripts/binizox-stop.ps1`。该脚本只执行 `stop`，不会删除卷。
