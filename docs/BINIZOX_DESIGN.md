# Binizox 本地个人 Agent 设计

## 1. 产品边界

Binizox 是本地优先的个人知识与自动化 Agent。Yuxi 是唯一运行基座，经过验证的解析、Skill 和工具能力接入同一条 Agent Run；其余上游保持候选或架构参考状态。

第一版优先完成可运行闭环，不重新设计复杂租户角色或企业审批策略。Yuxi 现有用户、部门和数据库字段暂时作为兼容基础；产品界面和新代码使用“个人工作区、操作确认、个人工具”的语义。

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
  → Personal Tool Runner 幂等写入 Markdown
  → worker 保存 ToolResult 和最终回答
  → SSE/数据库提供过程与最终事实
```

登录后可从侧栏进入 `/binizox` 总览。该页面读取 FastAPI 提供的固定上游清单和工具服务健康投影；浏览器不会直连工具服务，也不会自行把候选能力标记为已集成。

解析链继续使用独立 parser sidecar。原文件和解析结果沿用 MinIO，文档、版本、chunk、Run、消息与 checkpoint 沿用 PostgreSQL，Redis 只负责任务和事件投递。

## 3. 本地开发拓扑

```text
Conda binizox-dev: Yuxi FastAPI、worker、personal-tool-runner
Conda binizox-parser: 固定版本的 parser sidecar
Node:  Vue/Vite
Docker: PostgreSQL、Redis、MinIO
```

本地服务地址默认如下：

| 服务 | 地址 |
|---|---|
| Vue | `http://127.0.0.1:5173` |
| Yuxi/Binizox API | `http://127.0.0.1:5050` |
| Parser | `http://127.0.0.1:8090` |
| Personal Tool Runner | `http://127.0.0.1:8091` |

全部地址都通过环境变量注入。Docker 模式只把宿主机地址改为 Compose 服务名，不复制业务代码。

Binizox 启动脚本和 Compose 使用 `BINIZOX_PARSER_URL` 与 `BINIZOX_MAX_DOCUMENT_BYTES`。文档服务仍兼容旧的 `ASTERDESK_PARSER_URL` 和 `ASTERDESK_MAX_DOCUMENT_BYTES`，以便保留 Phase 2–4 环境的可恢复性；如果新旧变量同时存在，Binizox 变量优先。

## 4. 最小个人工具

第一版只提供 `workspace.write_note`：

- 输入必须是工作区内相对路径；
- 只允许 `.md` 和 `.txt`；
- 不允许 `..`、绝对路径或工作区逃逸；
- 不覆盖内容不同的已有文件；
- 同一幂等键和相同参数安全回放；
- 同一幂等键和不同参数返回 HTTP 409；
- 工具服务使用独立 SQLite 保存执行事实；
- Agent 只能通过 HTTP adapter 调用，不能直接修改工具数据库。

LangGraph 已有 Human-in-the-loop 中间件负责确认。确认发生在工具函数真正执行之前，因此拒绝不会触发文件写入。

## 5. 上游串联原则

| 上游 | 第一版连接方式 |
|---|---|
| Yuxi | 唯一主工程、Agent Run、UI、API、worker、SSE 和存储 |
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
10. Run 的 SSE、checkpoint 和最终消息沿用 Yuxi 持久化链路。
11. `binizox-personal-agent` 出现在内置 Skill 清单，并按需开放检索与保存笔记工具。
12. Binizox 总览能够区分已运行、候选和架构参考，工具服务不可用时显示可恢复状态。

## 7. 后续顺序

最小闭环稳定后，再依次增加文件分类、报告生成、日历和邮件草稿。删除、覆盖、邮件发送和任意命令执行不进入首版。WeKnora 混合检索和 DeepSeek Harness 插件宿主只有在独立验证通过后才从候选改为已集成。
