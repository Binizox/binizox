# Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""RAGFlow PlainParser 的最小逐页适配。

来源：infiniflow/ragflow@313ca90f6abd7682fe8523e16fd67b3653a3fa84
原路径：deepdoc/parser/pdf_parser.py，class PlainParser

修改：删除 RAGFlow 全局常量和 outline 依赖；不再吞掉异常；按页返回文本，
使调用方能生成稳定的页码定位。此文件不包含 OCR、布局模型或模型权重。
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader


def extract_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    """用 RAGFlow PlainParser 相同的 pypdf 边界逐页提取文本。"""

    pdf = PdfReader(BytesIO(data))
    pages: list[tuple[int, str]] = []
    for page_number, page in enumerate(pdf.pages, start=1):
        pages.append((page_number, page.extract_text() or ""))
    return pages
