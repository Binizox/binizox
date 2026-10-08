# Binizox 固定上游清单

`upstreams/` 是被 Git 忽略的本地研究快照，不进入主工程 import 路径。Binizox 仓库只提交必要的适配代码、许可证通知和本清单。

| 项目 | 地址 | 固定 commit | 许可证 | 当前状态 |
|---|---|---|---|---|
| Yuxi | `https://github.com/xerrors/Yuxi.git` | `2def1d3ad8a7359168639acfc1494a481f6dd55d`（研究快照）；Binizox 运行基座源于 Yuxi `v0.7.2` | MIT | 主工程基座 |
| RAGFlow | `https://github.com/infiniflow/ragflow.git` | `313ca90f6abd7682fe8523e16fd67b3653a3fa84` | Apache-2.0 | 最小 PDF 解析函数已复用 |
| WeKnora | `https://github.com/Tencent/WeKnora.git` | `4df7ccbb4f650082331452a92b52854f8922da2a` | MIT 及第三方通知 | 检索服务候选 |
| DeerFlow | `https://github.com/bytedance/deer-flow.git` | `bf9a019f28dbf4af106096ad3dca38452a8dd7e4` | MIT | Skill frontmatter 已复用 |
| LibreChat | `https://github.com/LibreChat-AI/LibreChat.git` | `7b2362d7a7c6148b84850924dc7fa5fc43307923` | MIT | 多模型接口参考 |
| DeepSeek Harness | `https://github.com/deepseek-ai/deepseek-harness.git` | `477b4f420553e8a52c2fbccc464d7561b239c443` | MIT 及第三方通知 | 插件生命周期参考 |

## 已实际运行的复用

- Yuxi：修改后复用主工程；Binizox 新增代码仍位于 `yuxi` Python 包中，以避免复制运行时。
- RAGFlow：`services/parser-sidecar/app/vendor/ragflow_plain_pdf.py`，保留 Apache-2.0 来源和第三方通知。
- DeerFlow：`backend/package/yuxi/asterdesk/_vendor/deerflow_skill_frontmatter.py`，保留 MIT 来源和 NOTICE。

## 尚未声称为集成

WeKnora、LibreChat 与 DeepSeek Harness 当前只有本地固定快照和清晰的候选接口。没有运行其服务或源码之前，不将其写成“已复用”。

## 本地核验命令

```powershell
$names = 'yuxi','ragflow','weknora','deer-flow','librechat','deepseek-harness'
foreach ($name in $names) {
    git -C "upstreams/$name" rev-parse HEAD
    git -C "upstreams/$name" remote -v
}
```
