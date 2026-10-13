"""Binizox 固定上游能力清单。

“已运行”与“候选”必须严格区分。该清单既供 API 展示，也用于文档和
测试核对，避免把架构参考错误描述为已经集成的源代码。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


IntegrationState = Literal["active", "adapter_ready", "candidate", "reference"]


@dataclass(frozen=True)
class UpstreamIntegration:
    """一个固定上游快照在 Binizox 中的真实使用范围。"""

    name: str
    commit: str
    license: str
    state: IntegrationState
    role: str
    boundary: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


UPSTREAM_INTEGRATIONS = (
    UpstreamIntegration(
        name="Yuxi",
        commit="bd07ab4ac4faa2e5452507580b1c841543bbec61",
        license="MIT",
        state="active",
        role="主工程基座",
        boundary=(
            "Binizox 改名并扩展后继续使用的 Vue、FastAPI、AgentRun、ARQ worker、"
            "LangGraph、SSE、PostgreSQL 与 MinIO 基座"
        ),
    ),
    UpstreamIntegration(
        name="RAGFlow",
        commit="313ca90f6abd7682fe8523e16fd67b3653a3fa84",
        license="Apache-2.0",
        state="active",
        role="PDF 最小逐页解析",
        boundary="只复用 PlainParser 的轻量边界，不包含 OCR、模型或完整 RAGFlow 服务",
    ),
    UpstreamIntegration(
        name="DeerFlow",
        commit="bf9a019f28dbf4af106096ad3dca38452a8dd7e4",
        license="MIT",
        state="active",
        role="Skill frontmatter 解析",
        boundary="不启动 DeerFlow 的第二套 Agent 循环",
    ),
    UpstreamIntegration(
        name="WeKnora",
        commit="4df7ccbb4f650082331452a92b52854f8922da2a",
        license="MIT",
        state="candidate",
        role="混合检索后端候选",
        boundary="当前仅固定研究快照，尚未部署 Go/Python 服务",
    ),
    UpstreamIntegration(
        name="LibreChat",
        commit="7b2362d7a7c6148b84850924dc7fa5fc43307923",
        license="MIT",
        state="reference",
        role="多模型配置与会话接口参考",
        boundary="保留 Binizox Vue 前端，不引入第二套 React 前端",
    ),
    UpstreamIntegration(
        name="DeepSeek Harness",
        commit="477b4f420553e8a52c2fbccc464d7561b239c443",
        license="MIT",
        state="reference",
        role="插件发现与生命周期参考",
        boundary="尚未运行 TypeScript/Cordis 插件宿主",
    ),
)


def list_upstream_integrations() -> list[dict[str, str]]:
    """返回可直接序列化的固定上游清单。"""

    return [integration.to_dict() for integration in UPSTREAM_INTEGRATIONS]
