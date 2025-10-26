"""Utilities for transforming Docling output into indexed chunks."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from docling_core.types.doc.document import DoclingDocument

from app.config import get_settings


@dataclass(slots=True)
class Chunk:
    """Normalized content that is ready for indexing."""

    chunk_id: str
    doc_version_id: str
    section_path: str
    page_start: int
    page_end: int
    kind: str
    text: str
    token_count: int
    meta: dict
    hash: str


@dataclass(slots=True)
class TableRecord:
    """Normalized table metadata."""

    table_id: str
    chunk_id: str
    page: int
    path: str
    nrows: int
    ncols: int
    cells: list[list[str]]


def normalize_tables(doc: DoclingDocument, doc_version_id: str) -> list[TableRecord]:
    """Extract tables from Docling 2.x document."""
    tables: list[TableRecord] = []
    for idx, table in enumerate(doc.tables):
        table_id = f"{doc_version_id}:table:{idx}"
        chunk_id = f"tbl_{table_id}"

        # Get page number from provenance
        page = 1
        if table.prov and len(table.prov) > 0:
            page = table.prov[0].page_no

        # Extract cells - table.data is a grid of TableCell objects
        cells: list[list[str]] = []
        if hasattr(table, 'data') and table.data:
            for row in table.data:
                row_texts = []
                for cell in row:
                    if hasattr(cell, 'text'):
                        row_texts.append(cell.text or "")
                    else:
                        row_texts.append(str(cell) if cell else "")
                cells.append(row_texts)

        nrows = len(cells)
        ncols = len(cells[0]) if cells else 0

        tables.append(
            TableRecord(
                table_id=table_id,
                chunk_id=chunk_id,
                page=page,
                path="",  # Could extract from hierarchy if needed
                nrows=nrows,
                ncols=ncols,
                cells=cells,
            )
        )
    return tables


def chunk_document(doc: DoclingDocument, doc_version_id: str) -> tuple[list[Chunk], list[TableRecord]]:
    """Convert a Docling 2.x :class:`DoclingDocument` into normalized chunks."""

    settings = get_settings()
    max_tokens = settings.max_chunk_tokens
    overlap = settings.chunk_overlap_tokens

    chunks: list[Chunk] = []
    docling_doc = doc

    # Process all text items from the document
    buffer: list[str] = []
    token_count = 0
    page_start = 1
    page_end = 1
    section_path = "Document"

    for text_item in docling_doc.texts:
        text = text_item.text.strip() if hasattr(text_item, 'text') and text_item.text else ""
        if not text:
            continue

        # Get page number from provenance
        if hasattr(text_item, 'prov') and text_item.prov and len(text_item.prov) > 0:
            current_page = text_item.prov[0].page_no
            if not page_start or current_page < page_start:
                page_start = current_page
            if current_page > page_end:
                page_end = current_page

        # Update section path if this is a header
        if hasattr(text_item, 'label') and 'header' in str(text_item.label).lower():
            section_path = text[:100]  # Use first 100 chars as section name

        tokens = text.split()

        # Check if adding this text would exceed max tokens
        if token_count + len(tokens) > max_tokens and buffer:
            # Create chunk from buffer
            chunk_text = "\n".join(buffer)
            chunk_hash = sha256(chunk_text.encode("utf-8")).hexdigest()
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_version_id}:{len(chunks)}",
                    doc_version_id=doc_version_id,
                    section_path=section_path,
                    page_start=page_start,
                    page_end=page_end,
                    kind="paragraph",
                    text=chunk_text,
                    token_count=token_count,
                    meta={"source": "docling"},
                    hash=chunk_hash,
                )
            )

            # Keep overlap
            if overlap and buffer:
                overlap_size = min(len(buffer), int(overlap / 10))  # Keep last few items
                buffer = buffer[-overlap_size:] if overlap_size > 0 else []
                token_count = sum(len(p.split()) for p in buffer)
            else:
                buffer = []
                token_count = 0

        buffer.append(text)
        token_count += len(tokens)

    # Add remaining buffer as final chunk
    if buffer:
        chunk_text = "\n".join(buffer)
        chunk_hash = sha256(chunk_text.encode("utf-8")).hexdigest()
        chunks.append(
            Chunk(
                chunk_id=f"{doc_version_id}:{len(chunks)}",
                doc_version_id=doc_version_id,
                section_path=section_path,
                page_start=page_start,
                page_end=page_end,
                kind="paragraph",
                text=chunk_text,
                token_count=token_count,
                meta={"source": "docling"},
                hash=chunk_hash,
            )
        )

    tables = normalize_tables(docling_doc, doc_version_id)
    return chunks, tables
