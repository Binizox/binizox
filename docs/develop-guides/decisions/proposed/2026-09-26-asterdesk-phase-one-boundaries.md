# AsterDesk 第一阶段边界与确定性验证

状态：proposed
类型：architecture
Owner：backend/package/yuxi/asterdesk/contracts.py

## 问题

Yuxi 已拥有请求持久化、队列、worker、LangGraph、SSE 与终态存储，但 AsterDesk 还没有明确的解析、检索、工具、Skill 和 Run 交换边界，也没有无外部企业数据、无真实业务副作用的政策问答验证。

## 范围

- 类型：`architecture`、`feature`、`testing`。
- 目标：增加最小契约模型；用一个虚构 IT 政策 Skill 验证现有 Run 主链路；用 DeerFlow 的 Skill frontmatter 解析模块验证一次真实的跨项目源码复用。
- 非目标：不增加第二套 Agent 循环；不连接 OA、账号、采购或审批系统；不把 RAGFlow、WeKnora、LibreChat 或 DeepSeek Harness 整体引入运行时；不改变 Yuxi 已有 Run 数据库状态。
- 假设：第一阶段政策内容可通过预加载 Skill 进入模型上下文。向量知识库上传、索引和检索仍作为后续集成，不把本次 Skill 上下文验证描述成向量检索。

## 提案

1. 保留 Yuxi 的 Request、AgentRun、LangGraph checkpoint 与 SSE 语义，AsterDesk 不再造同名状态机。
2. 在 `yuxi.asterdesk.contracts` 中定义跨服务交换模型；模型只描述边界，不直接接管 Yuxi repository。
3. 将 DeerFlow 的纯函数 `split_skill_markdown` 及其不可变返回类型按 MIT 许可保留来源后直接复用，并由 `skill_adapter` 映射为 AsterDesk `SkillManifest`。
4. 通过现有 ChatbotAgent、确定性 OpenAI 兼容 replay、真实 worker 和 PostgreSQL 完成政策问答 E2E；答案必须包含文档、版本和章节定位，SSE 必须出现消息事件与唯一终止事件。

## 替代方案

- 直接部署 DeerFlow：会引入第二套 Agent 循环与沙盒生命周期，第一阶段风险过高。
- 直接部署 RAGFlow 全平台：解析与检索依赖面过大；第一阶段只调查并保留独立解析服务候选。
- 新建 AsterDesk Run 表：会与 Yuxi `AgentRun`、request FIFO 和终态事实冲突，因此拒绝。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 契约模型拒绝缺少幂等键的工具调用 | 重投产生重复副作用 | `yuxi.asterdesk.contracts` | `pytest test/unit/asterdesk`（5 个用例） | 空幂等键校验失败 | Passed |
| DeerFlow frontmatter 源码被实际调用 | 只写文档却没有运行复用代码 | `_vendor/deerflow_skill_frontmatter.py`、`skill_adapter.py` | `pytest test/unit/asterdesk` | 无 frontmatter 时失败 | Passed |
| 政策问答经过 API、worker、LangGraph、SSE 和 PostgreSQL | 仅进程内 mock 或仅 HTTP 200 | Yuxi Run services/repositories | 真实 Compose 中执行 AsterDesk 政策 E2E | 缺少政策 Skill 时 replay 返回 `policy_context_missing` | Passed |
| 最终答案可从持久化终态读取并含来源定位 | SSE 文本存在但业务终态丢失 | `agent_runs.output_message_id` 与 Message | E2E 回读 API 与 PostgreSQL；API 重启后结果 API 200 | 输出缺少来源时断言失败 | Passed |

## 风险

- Docker 或外部镜像不可用会阻止 E2E；必须记录为 `Not run`，不能用 unit 替代。
- Skill 上下文不是向量检索，文档必须持续明确这一区别。
- 复用文件的上游 commit、原始路径与 MIT 版权必须保留在源码头和复用清单中。
