# Binizox 本地个人 Agent 设计

## 1. 产品边界

Binizox 是本地优先的个人知识与自动化 Agent。Binizox 是唯一运行时和产品命名空间，经过验证的解析、Skill 和工具能力接入同一条 Agent Run；其余上游保持候选或架构参考状态。主工程演进自 Yuxi 固定版本，但运行代码不再依赖 `yuxi` Python 包或 `YUXI_*` 配置。

第一版优先完成可运行闭环，不重新设计复杂租户角色或企业审批策略。继承的用户、部门和数据库字段暂时作为兼容基础；产品界面和新代码使用“个人工作区、操作确认、个人工具”的语义。

## 2. 运行架构

```text
Vue 对话页面
  → FastAPI 创建 AgentRun
  → PostgreSQL 保存请求与状态
  → Redis/ARQ 投递
  → worker 执行 LangGraph
  → search_binizox_evidence 检索过滤后的 Evidence
  → save_binizox_note 被 HumanInTheLoopMiddleware 拦截
  → Vue 展示固定工具参数，用户确认
  → resume Run
  → worker 使用内部服务凭据提交 uid/run/tool_call 固定调用
  → Personal Tool Runner 幂等写入 shared/<uid>/workspace 下的 Markdown
  → worker 保存 ToolResult 和最终回答
  → SSE/数据库提供过程与最终事实
```

登录后可从侧栏进入 `/binizox` 总览。该页面读取 FastAPI 提供的固定上游清单和工具服务健康投影；浏览器不会直连工具服务，也不会自行把候选能力标记为已集成。

解析链继续使用独立 parser sidecar。原文件和解析结果沿用 MinIO，文档、版本、chunk、Run、消息与 checkpoint 沿用 PostgreSQL，Redis 只负责任务和事件投递。

## 3. 本地开发拓扑

```text
Conda binizox-dev: Binizox FastAPI、worker、personal-tool-runner
Conda binizox-parser: 固定版本的 parser sidecar
Node:  Vue/Vite
Docker: PostgreSQL、Redis、MinIO
```

本地服务地址默认如下：

| 服务 | 地址 |
|---|---|
| Vue | `http://127.0.0.1:5173` |
| Binizox API | `http://127.0.0.1:5050` |
| Parser | `http://127.0.0.1:8090` |
| Personal Tool Runner | `http://127.0.0.1:8091` |

全部地址都通过环境变量注入。Docker 模式只把宿主机地址改为 Compose 服务名，不复制业务代码。默认和生产 Compose 都包含 parser 与 Personal Tool Runner；`docker-compose.binizox.yml` 仅增加测试 replay 服务。

Binizox 启动脚本、Compose 与文档服务只读取 `BINIZOX_PARSER_URL` 和 `BINIZOX_MAX_DOCUMENT_BYTES`。旧 Phase 数据通过一次性迁移脚本保留，不再把旧产品环境变量带入运行时。

### 3.1 独立命名空间

| 边界 | Binizox 标识 |
|---|---|
| Python 主包 | `binizox` |
| CLI 包 / import / 命令 | `binizox-cli` / `binizox_cli` / `binizox` |
| 自有环境变量 | `BINIZOX_*` |
| CLI 用户配置 | `~/.binizox/config.toml` |
| 容器、镜像、默认数据路径 | `binizox-*` / Binizox 专用目录 |

命名空间切换是独立项目边界。对本机 Phase 5 数据使用显式、可审计的迁移，而不是无提示的隐式兼容：

- `migrate-binizox-local-state.ps1` 先备份环境文件，再将 `YUXI_*` 转换为 `BINIZOX_*`；不会输出密钥内容。
- Phase 5 状态以只复制、不删除源数据、不覆盖非空目标的方式迁至 `.runtime/binizox/full`。
- JWT issuer/audience 已改变，旧会话需要重新登录；原 secret、instance ID 和用户密码哈希保持一致。
- 新 API Key 使用 `bzkey_` 与 Binizox 派生命名域；迁入数据库的旧 `yxkey_` Key 保留只读兼容，不再签发。
- 本机不存在 `~/.yuxi/config.toml`，因此没有 CLI 配置需要复制；新配置路径为 `~/.binizox/config.toml`。
- 上游来源仍以真实仓库名 Yuxi、真实 URL、固定 commit 和许可证记录在 `BINIZOX_UPSTREAMS.md`，不会随产品命名改写。

## 4. 最小个人工具

第一版只提供 `workspace.write_note`：

- 输入必须是工作区内相对路径；
- 只允许 `.md` 和 `.txt`；
- 不允许 `..`、绝对路径或工作区逃逸；
- 不覆盖内容不同的已有文件；
- 同一幂等键和相同参数安全回放；
- 同一幂等键和不同参数返回 HTTP 409；
- 同一幂等键仍由有效短租约执行时返回 `execution_in_progress`；租约过期后才允许以新 claim token 接管，旧 owner 无权写入终态；
- 已有文件使用 no-follow、非阻塞和按期望长度有界读取核对，FIFO、symlink 或内容不一致时不覆盖；
- 工具服务使用独立 SQLite 保存执行事实；
- 请求必须携带 API/worker 与 Tool Runner 共享的独立内部服务凭据；
- `uid`、`run_id`、`tool_call_id` 和参数一起进入幂等摘要，不同用户写入各自的 canonical UserWorkspace；
- Compose 中 Tool Runner 必须等待 `storage-migrator` 成功后才接收 workspace 写入；
- Agent 只能通过 HTTP adapter 调用，不能直接修改工具数据库。

LangGraph 已有 Human-in-the-loop 中间件负责确认。确认发生在工具函数真正执行之前，因此拒绝不会触发文件写入。

## 5. 上游串联原则

| 上游 | 第一版连接方式 |
|---|---|
| Yuxi | Binizox 主工程的固定来源基线；Agent Run、UI、API、worker、SSE 和存储已迁入 Binizox 命名空间 |
| RAGFlow | parser sidecar 中的最小 PDF 逐页解析函数 |
| DeerFlow | Skill frontmatter 解析函数 |
| WeKnora | 固定源码快照；为后续 RetrievalBackend 保留候选边界 |
| LibreChat | 固定源码快照；只参考多模型配置，不引入 React 前端 |
| DeepSeek Harness | 固定源码快照；只参考插件生命周期，不运行 Cordis 宿主 |

“包含上游”不等于把上游目录加入 Python import path。所有真正接入的代码必须经过适配层，并在复用清单中记录 commit、许可证和验证结果。

## 6. 最小验收

1. 工具服务健康检查成功；
2. 写入 `notes/demo.md` 成功；
3. 同一幂等键重复请求只得到一次文件副作用；
4. 同键不同参数返回 409；
5. 路径逃逸返回 422；
6. Binizox API 能展示六个上游的真实状态；
7. Agent 配置启用 `binizox-personal-agent` Skill 后能够检索 Evidence；
8. Agent 调用 `save_binizox_note` 时进入现有 Vue 人工确认；
9. 确认后文件写入，拒绝时文件不产生；
10. Run 的 SSE、checkpoint 和最终消息沿用基座原有持久化设计，并由 Binizox 包提供运行实现。
11. `binizox-personal-agent` 出现在内置 Skill 清单，并按需开放检索与保存笔记工具。
12. Binizox 总览能够区分已运行、候选和架构参考，工具服务不可用时显示可恢复状态。

Ubuntu system-test 使用确定性 OpenAI-compatible replay 装配第 7—10 项：测试直接加载生产
`binizox-personal-agent` Skill，经真实 API、PostgreSQL、Redis worker、LangGraph checkpoint 与 SSE
取得固定工具参数；批准后核对 Tool Runner 执行记录和文件字节，拒绝后核对无执行记录、无文件。
本机 Docker Engine 不可用时，这条容器验收只能记为已接线、待远端工作流通过，不能由单元测试替代。

## 7. 后续顺序

最小闭环稳定后，再依次增加文件分类、报告生成、日历和邮件草稿。删除、覆盖、邮件发送和任意命令执行不进入首版。WeKnora 混合检索和 DeepSeek Harness 插件宿主只有在独立验证通过后才从候选改为已集成。
