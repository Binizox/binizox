---
name: asterdesk-evidence
slug: asterdesk-evidence
version: 2.0.0
description: "从已入库文档检索当前用户可见的证据，并仅基于证据生成带来源回答。"
allowed-tools:
  - search_asterdesk_evidence
metadata:
  permissions:
    - knowledge:document:read
  visibility: tenant
---

# AsterDesk 文档证据问答

处理企业政策或知识问题时，先调用 `search_asterdesk_evidence`，参数中的问题保持用户原意，并使用当前 Agent 配置指定的知识库。

只能使用本次工具结果 `evidence` 中的内容回答。每个事实后附上对应的 `citation` 原文；不得自行编造文档名、版本、页码、章节或 chunk ID。

如果 `evidence` 为空，明确说明当前用户可访问的已发布文档中没有相关证据，不得使用其他用户、旧版本、解析失败版本或第一阶段预加载政策的内容补答。

第一阶段的 `asterdesk-it-policy` Skill 是固定政策全文预加载对照样例；本 Skill 是第二阶段真实文档入库和运行时检索链路。两个 Skill 不应在同一个验证 Agent 中同时预加载。
