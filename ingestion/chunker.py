"""Utilities for transforming Docling output into indexed chunks."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterator, Sequence

from docling.datamodel.document import ConversionResult as ConvertedDocument
from docling_core.types.doc.document import DoclingDocument, TableItem as Table, SectionHeaderItem as Section

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


def walk_sections(section: Section, parents: Sequence[str] | None = None) -> Iterator[tuple[str, Section]]:
    """Yield sections with their hierarchical path."""

    parents = parents or []
    current_path = " > ".join([*parents, section.title.strip()]) if section.title else " > ".join(parents)
    yield current_path, section
    for child in section.children:
        yield from walk_sections(child, [*parents, section.title.strip() or "Section"])


def normalize_tables(doc: ConvertedDocument, doc_version_id: str) -> list[TableRecord]:
    tables: list[TableRecord] = []
    for table in doc.tables:
        chunk_id = f"tbl_{table.id}"
        path = table.metadata.get("section_path", "") if table.metadata else ""
        cells = [[cell.plain_text for cell in row.cells] for row in table.rows]
        tables.append(
            TableRecord(
                table_id=table.id,
                chunk_id=chunk_id,
                page=table.metadata.get("page", 0) if table.metadata else 0,
                path=path,
                nrows=len(table.rows),
                ncols=len(table.rows[0].cells) if table.rows else 0,
                cells=cells,
            )
        )
    return tables


def chunk_document(doc: ConvertedDocument, doc_version_id: str) -> tuple[list[Chunk], list[TableRecord]]:
    """Convert a Docling :class:`ConvertedDocument` into normalized chunks."""

    settings = get_settings()
    max_tokens = settings.max_chunk_tokens
    overlap = settings.chunk_overlap_tokens

    chunks: list[Chunk] = []
    for section_path, section in walk_sections(doc.root_section):
        if not section.content:
            continue

        buffer: list[str] = []
        token_count = 0
        page_start = section.metadata.get("page", 1) if section.metadata else 1
        page_end = page_start

        for paragraph in section.content:
            text = paragraph.plain_text.strip()
            if not text:
                continue
            tokens = text.split()
            if token_count + len(tokens) > max_tokens and buffer:
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
                buffer = buffer[int(overlap / 2):] if overlap and buffer else []
                token_count = sum(len(p.split()) for p in buffer)

            buffer.append(text)
            token_count += len(tokens)
            page_end = max(page_end, paragraph.metadata.get("page", page_end) if paragraph.metadata else page_end)

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

    tables = normalize_tables(doc, doc_version_id)
    return chunks, tables
