"""PDF 与 DOCX 到 Binizox ParsedDocument 的最小结构化适配。"""

from __future__ import annotations

import re
from collections.abc import Iterator
from io import BytesIO
from typing import Any

import pdfplumber
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.vendor.ragflow_plain_pdf import extract_pdf_pages

HEADING_NUMBER = re.compile(r"^(?:\d+(?:\.\d+)*|[一二三四五六七八九十]+[、.])\s*\S+")


def _location(page: int, block_index: int, **extra: Any) -> dict[str, Any]:
    return {"page": page, "section": None, "block_index": block_index, **extra}


def _is_heading(text: str, *, first: bool, style_name: str = "") -> bool:
    if style_name.lower().startswith(("heading", "title")):
        return True
    if first:
        return True
    return len(text) <= 80 and bool(HEADING_NUMBER.match(text))


def _block(
    *,
    text: str,
    page: int,
    block_index: int,
    heading_path: list[str],
    style_name: str = "",
    first: bool = False,
) -> dict[str, Any]:
    is_heading = _is_heading(text, first=first, style_name=style_name)
    if is_heading:
        normalized_style = style_name.strip().lower()
        level_match = re.search(r"(\d+)$", normalized_style)
        # Word 的 Title 是文档根节点；Heading 1/2... 分别是其下一级。
        level = (
            0
            if normalized_style.startswith("title")
            else int(level_match.group(1))
            if level_match
            else 1
        )
        del heading_path[level:]
        heading_path.append(text)
    return {
        "block_id": f"block-{block_index}",
        "kind": "heading" if is_heading else "paragraph",
        "text": text,
        "heading_path": list(heading_path),
        "location": _location(page, block_index),
    }


def _iter_docx_blocks(document: DocxDocument) -> Iterator[Paragraph | Table]:
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _has_page_break(paragraph: Paragraph) -> bool:
    return bool(
        paragraph._element.xpath(".//w:br[@w:type='page']")
        or paragraph._element.xpath(".//w:lastRenderedPageBreak")
    )


def parse_docx(
    data: bytes,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    document = Document(BytesIO(data))
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    heading_path: list[str] = []
    page = 1
    block_index = 0

    for item in _iter_docx_blocks(document):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            has_break = _has_page_break(item)
            if text:
                blocks.append(
                    _block(
                        text=text,
                        page=page,
                        block_index=block_index,
                        heading_path=heading_path,
                        style_name=item.style.name if item.style else "",
                        first=not blocks,
                    )
                )
                block_index += 1
            if has_break:
                page += 1
            continue

        rows = [[cell.text.strip() for cell in row.cells] for row in item.rows]
        if rows:
            table_index = len(tables)
            tables.append(
                {
                    "table_id": f"table-{table_index}",
                    "rows": rows,
                    "location": _location(
                        page,
                        block_index,
                        table_index=table_index,
                        row_start=0,
                        row_end=len(rows) - 1,
                    ),
                }
            )
            block_index += 1

    return blocks, tables, errors


def parse_pdf(
    data: bytes,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    heading_path: list[str] = []
    block_index = 0

    pages = extract_pdf_pages(data)
    for page_number, text in pages:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            errors.append(
                {
                    "code": "page_text_empty",
                    "message": f"Page {page_number} has no extractable text",
                    "recoverable": True,
                    "location": _location(page_number, block_index),
                }
            )
        for line in lines:
            blocks.append(
                _block(
                    text=line,
                    page=page_number,
                    block_index=block_index,
                    heading_path=heading_path,
                    first=not blocks,
                )
            )
            block_index += 1

    with pdfplumber.open(BytesIO(data)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for raw_table in page.extract_tables() or []:
                rows = [[str(cell or "").strip() for cell in row] for row in raw_table]
                if not rows:
                    continue
                table_index = len(tables)
                tables.append(
                    {
                        "table_id": f"table-{table_index}",
                        "rows": rows,
                        "location": _location(
                            page_number,
                            block_index,
                            table_index=table_index,
                            row_start=0,
                            row_end=len(rows) - 1,
                            bbox=tuple(float(value) for value in page.bbox),
                        ),
                    }
                )
                block_index += 1

    return blocks, tables, errors


def parse_document(document_ref: dict[str, Any], data: bytes) -> dict[str, Any]:
    """解析一个不可变文档版本并返回统一 wire contract。"""

    errors: list[dict[str, Any]] = []
    try:
        if document_ref["format"] == "pdf":
            blocks, tables, errors = parse_pdf(data)
        elif document_ref["format"] == "docx":
            blocks, tables, errors = parse_docx(data)
        else:
            raise ValueError(f"Unsupported format: {document_ref['format']}")
    except Exception as exc:  # noqa: BLE001 - the service boundary must return structured parse errors.
        blocks, tables = [], []
        errors = [
            {
                "code": "parse_failed",
                "message": str(exc)[:1000] or exc.__class__.__name__,
                "recoverable": False,
                "location": None,
            }
        ]

    failed = not blocks and not tables
    if failed and not errors:
        errors.append(
            {
                "code": "empty_document",
                "message": "Document contains no indexable text or tables",
                "recoverable": False,
                "location": None,
            }
        )
    return {
        "document": document_ref,
        "status": "failed" if failed else "succeeded",
        "blocks": blocks,
        "tables": tables,
        "errors": errors,
    }
