"""知识库运行时单例。"""

import os

from binizox.config import get_runtime_dir
from binizox.config.runtime import knowledge_capability_enabled
from binizox.knowledge.factory import KnowledgeBaseFactory
from binizox.knowledge.implementations.dify import DifyKB
from binizox.knowledge.implementations.milvus import MilvusKB
from binizox.knowledge.implementations.notion import NotionKB
from binizox.knowledge.manager import KnowledgeBaseManager

if knowledge_capability_enabled():
    KnowledgeBaseFactory.register(MilvusKB)
KnowledgeBaseFactory.register(DifyKB)
KnowledgeBaseFactory.register(NotionKB)

knowledge_base = KnowledgeBaseManager(os.path.join(get_runtime_dir(), "knowledge_base_data"))
