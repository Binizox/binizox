# Binizox

Binizox 是一个本地优先的个人知识与自动化 Agent。项目以 Yuxi 固定源码版本为工程基座，保留 Vue、FastAPI、PostgreSQL、Redis、MinIO、ARQ worker、LangGraph checkpoint、SSE、Skills、MCP 与独立文档解析服务，并将产品命名空间、Python 包、CLI、容器和配置统一为 Binizox。

当前主闭环：

```text
个人文档上传 → PDF/DOCX 结构化解析 → 服务端可见范围过滤 → Evidence
→ Agent 生成带来源回答 → 用户确认工具参数 → 保存个人笔记
→ Run 终态、工具结果与引用持久化 → Vue/SSE 展示
```

## 已实现

- `binizox` Python 主包与 `binizox` CLI；自有环境变量统一使用 `BINIZOX_*`。
- Vue 对话工作台、FastAPI API、Redis/ARQ worker、LangGraph 与 PostgreSQL Run/checkpoint 主链路。
- PDF/DOCX 解析 sidecar；文档版本、页码、标题路径、表格和错误使用统一契约。
- `search_binizox_evidence`：身份由服务端 Run 上下文取得，只向 Agent 返回过滤后的 Evidence。
- `binizox-personal-agent` Skill：检索个人资料并使用实际 Evidence 生成引用。
- `save_binizox_note`：用户确认后，通过独立 HTTP Tool Runner 幂等写入个人工作区中的 `.md`/`.txt`。
- `/binizox` 总览：展示运行链、工具服务状态以及上游能力的真实接入状态。

早期 AsterDesk VPN 审批原型已经退出当前运行面：不再注册路由、worker、Vue 页面、Skill、模拟服务或新建 action 表。迁入数据库中的旧表不会被删除；旧 Evidence 元数据和旧 API Key 仅保留受限读取兼容。

## 本地开发

要求：Windows PowerShell、Conda、Node.js/Corepack；完整基础设施验证还需要 Docker Desktop。

```powershell
Set-Location D:\Download\Binizox
.\scripts\conda-bootstrap.ps1 -InstallPlatform
Copy-Item .env.binizox.example .env.binizox.local
.\scripts\dev-infra-up.ps1
.\scripts\dev-parser.ps1
.\scripts\dev-tool-runner.ps1
.\scripts\dev-api.ps1
.\scripts\dev-worker.ps1
.\scripts\dev-web.ps1
```

默认地址：

| 服务 | 地址 |
|---|---|
| Vue | `http://127.0.0.1:5173` |
| API | `http://127.0.0.1:5050` |
| Parser | `http://127.0.0.1:8090` |
| Personal Tool Runner | `http://127.0.0.1:8091` |

Docker 打包模式：

```powershell
docker compose -f docker-compose.yml -f docker-compose.binizox.yml config
.\scripts\binizox-up.ps1
docker compose -f docker-compose.yml -f docker-compose.binizox.yml ps
Invoke-RestMethod http://127.0.0.1:5050/api/system/ready
```

默认 `docker-compose.yml` 和生产 `docker-compose.prod.yml` 已包含 Parser 与 Personal Tool Runner；附加的 `docker-compose.binizox.yml` 只用于确定性 Evidence 测试。`BINIZOX_TOOL_RUNNER_TOKEN` 是 API/worker 与工具服务之间的独立内部凭据，初始化脚本会生成，不能暴露给浏览器或模型上下文。

## 验证

```powershell
conda run -n binizox-dev python -m pytest backend/test/unit -q
conda run -n binizox-parser python -m pytest services/parser-sidecar/test -q
corepack pnpm --dir web lint:check
corepack pnpm --dir web test:unit
corepack pnpm --dir web build
python scripts/verify_engineering_contracts.py
git diff --check
```

本机已执行的结果与未执行项记录在 [验收记录](docs/BINIZOX_ACCEPTANCE.md)。

## 上游与许可证

Binizox 不把 `upstreams/` 加入应用 import 路径，也不重复提交整套研究快照。当前边界：

| 上游 | 使用方式 |
|---|---|
| Yuxi | MIT；主工程历史基座，来源与版权保留 |
| RAGFlow | Apache-2.0；最小 PDF 逐页解析边界 |
| DeerFlow | MIT；Skill frontmatter 解析边界 |
| WeKnora | 候选，只保留接口研究 |
| LibreChat | 架构参考，不引入第二套 React UI |
| DeepSeek Harness | 架构参考，不运行 Cordis 插件宿主 |

精确 commit、复用文件和许可证说明见 [上游与复用清单](docs/BINIZOX_UPSTREAMS.md)。根 [LICENSE](LICENSE) 只标识 Binizox；依法需要保留的 Yuxi 版权与 MIT 条款位于 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。Binizox 新增代码的作者标识为 `Binizox <binizox@163.com>`。

## 设计资料

- [架构设计](docs/BINIZOX_DESIGN.md)
- [本地迁移](docs/BINIZOX_LOCAL_MIGRATION.md)
- [工程架构约束](ARCHITECTURE.md)
- [贡献指南](CONTRIBUTING.md)

## 当前限制

- 需要用户自行配置可用的聊天、Embedding 与可选 Rerank 模型凭据。
- WeKnora、LibreChat、DeepSeek Harness 仍是候选/参考，不能描述为已运行集成。
- 旧企业审批数据仅保留，不在个人版继续提供业务 API。
