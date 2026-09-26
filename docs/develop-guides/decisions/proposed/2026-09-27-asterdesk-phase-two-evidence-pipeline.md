# AsterDesk 第二阶段文档证据链

状态：proposed
类型：architecture
Owner：backend/package/yuxi/asterdesk/document_service.py

## 问题

第一阶段政策问答把政策作为预加载 Skill 放入模型上下文，验证了 Yuxi 的 API、worker、LangGraph、SSE 和持久化 Run 主链路，但它不是文档入库与检索。第二阶段需要在不破坏第一阶段环境和数据的前提下，完成 PDF/DOCX 上传、结构化解析、索引、服务端权限过滤以及 Agent 基于本次检索证据回答的闭环。

## 范围

- 复用 Yuxi 的 `KnowledgeBase`、`KnowledgeFile`、`KnowledgeChunk`、MinIO、用户部门和资源权限模型。
- 增加独立解析 sidecar；运行时只安装 PDF/DOCX 解析所需的最小依赖。
- 在 `processing_params.asterdesk` 和 `extraction_result.asterdesk` 中保存 AsterDesk 的版本、租户、ACL、状态和来源位置，不新增数据库表。
- 使用 PostgreSQL 中的已授权片段做确定性词法检索；本阶段不依赖外部 embedding 模型，也不把它描述为混合或语义检索。
- 增加一个只能看到过滤后 `Evidence` 的 Agent 工具，并用独立 Compose 项目执行端到端验证。

非目标：不替换 Yuxi 已有 Milvus 检索；不启动 RAGFlow 全平台；不引入 OCR/版面模型权重；不改动第一阶段运行中的数据库卷；不连接真实企业系统。

## 提案

1. 原文件保存在 Yuxi MinIO 的文档桶；解析后的 `ParsedDocument` JSON 保存在解析桶；文档版本和处理状态保存在 `knowledge_files`；可检索片段及来源位置保存在 `knowledge_chunks`。
2. `file_id` 由租户、知识库、逻辑文档 ID 和版本确定性生成。同一版本同一内容重复提交返回已有结果；同一版本不同内容拒绝覆盖。
3. 状态依次为 `uploaded -> parsing -> indexed -> active`。解析或索引失败进入对应失败状态；重新解析沿用同一版本记录但先删除其未发布片段。新版本只有完全索引后才成为 `active`，之前的活动版本变为 `superseded`。
4. 旧版本的原文件、解析结果和片段暂不自动删除，以保证已完成 Run 的引用可以回查。显式保留策略或管理员清理任务未来由文档服务统一执行。
5. tenant 使用 Yuxi 当前用户的 `department_id` 作为服务端派生边界；API 不信任客户端提供的用户或租户。文档 ACL 使用 `global`、`department`、`user` 三种范围，并复用 Yuxi 资源权限的字段语义。
6. 检索 repository 先用 tenant、知识库权限、文档 ACL、`active` 状态筛选 `KnowledgeFile.file_id`，然后只查询这些 file ID 的片段。Agent 工具只返回该 repository 产生的 `Evidence`。
7. sidecar 中按 Apache-2.0 保留并修改 RAGFlow `PlainParser` 的逐页 PDF 文本提取边界；DOCX 使用同一服务内的 `python-docx` 适配器。RAGFlow 的 OCR、布局模型、ONNX、XGBoost 和模型权重不进入运行时。

## 替代方案

- 直接调用 RAGFlow 全服务：依赖 MySQL、Redis、对象存储、模型和任务编排，超过本阶段最小边界。
- 新建 AsterDesk 文档、版本和片段表：表达更直接，但会重复 Yuxi 已有知识模型并要求在第一阶段数据库上迁移。
- 先查全部片段再由 Agent 或前端过滤：无权限内容已经跨越服务端安全边界，拒绝采用。
- 直接复用 Milvus 检索：当前独立验证环境没有可用 embedding 模型，无法形成确定性、离线可重复的验收。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 | 负向案例 |
|---|---|---|---|---|
| PDF/DOCX 输出正文、标题路径、页码和表格 | 只看 HTTP 200 | parser sidecar | sidecar contract tests 与样例 JSON | 损坏文件返回结构化错误 |
| 未完成文档不进入检索 | 半成品泄露 | document repository | 状态过滤集成测试 | `parse_failed` 返回零 Evidence |
| 权限在检索服务执行 | 前端隐藏不构成授权 | search repository | 两个用户对同一查询的 E2E | 无权限用户零 Evidence |
| 重复提交和版本更新保持唯一活动版本 | 重复片段或版本串线 | document service | 幂等与版本测试 | 同版本不同内容返回冲突 |
| Agent 引用只来自本次 Evidence | 模型编造来源 | Agent evidence tool | worker/Run E2E 与持久化回读 | 工具零结果时不得输出受限内容 |
| API 重启后终态和引用可查询 | 只存在于 SSE | Yuxi Run repository | 重启 API 后回读 Run | 输出消息不存在则失败 |

## 风险

- 词法检索只适合证明数据与权限闭环，召回质量不代表生产语义检索。
- `processing_params` JSON 不具备专用列的数据库约束；本阶段通过服务、repository 和测试维持不变量，后续规模化前应评估正式迁移。
- PDF 纯文本/表格提取不包含 OCR 和复杂版面模型。扫描件或复杂合并单元格会形成可查询的解析失败或降级结果，不能静默发布。
