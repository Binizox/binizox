---
name: binizox-personal-agent
slug: binizox-personal-agent
version: 0.1.0
description: "检索个人资料，生成带来源回答，并在用户确认后把结果保存为个人笔记。"
allowed-tools:
  - search_binizox_evidence
  - save_binizox_note
metadata:
  permissions:
    - knowledge:document:read
    - workspace:note:write
  visibility: personal
---

# Binizox 个人知识与笔记

回答个人资料问题时，先调用 `search_binizox_evidence`。没有明确知识库 ID 时将 `knowledge_base_ids` 留空，服务端会限定为当前 Agent 已启用且当前用户可见的知识库。回答中的事实和来源只能来自本次调用返回的 Evidence；没有证据时要明确说明未找到，不得编造文件名、页码或标题。

只有用户明确要求保存、导出或生成笔记时才调用 `save_binizox_note`。调用前生成完整内容，使用个人工作区内的 `.md` 或 `.txt` 相对路径，并把实际使用的 citation 放入 `source_citations`。

保存笔记属于有副作用的操作。默认运行模式会在执行前展示工具参数并等待用户确认；用户拒绝后不得换用其他写入工具规避确认。
