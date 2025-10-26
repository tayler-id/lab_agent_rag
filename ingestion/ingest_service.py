"""High level ingestion workflow coordinating parsing and persistence."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
from typing import Any

from docling.document_converter import DocumentConverter, InputDocument
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.supabase_client import get_client
from ingestion.chunker import chunk_document


def _fingerprint(content: bytes) -> str:
    return sha256(content).hexdigest()


@retry(wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
def _ensure_storage_upload(bucket: str, path: str, data: bytes) -> None:
    client = get_client()
    storage = client.storage()
    bucket_client = storage.from_(bucket)
    bucket_client.upload(path, data, {"content-type": "application/octet-stream", "upsert": True})


def ingest_document(*, tenant_id: str, file_name: str, file_bytes: bytes, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ingest a document into Supabase storage and relational tables."""

    settings = get_settings()
    metadata = metadata or {}
    fingerprint = _fingerprint(file_bytes)
    now = datetime.utcnow()

    client = get_client()

    storage_path = f"{tenant_id}/{fingerprint}/{file_name}"
    _ensure_storage_upload(settings.supabase_storage_bucket, storage_path, file_bytes)

    doc_response = (
        client.table("documents")
        .upsert(
            {
                "tenant_id": tenant_id,
                "title": metadata.get("title") or file_name,
                "vendor": metadata.get("vendor"),
                "model": metadata.get("model"),
                "doc_type": metadata.get("doc_type"),
                "updated_at": now.isoformat(),
                "created_at": now.isoformat(),
            },
            on_conflict="tenant_id,title"
        )
        .execute()
    )
    document_id = doc_response.data[0]["id"]

    doc_version_response = (
        client.table("document_versions")
        .insert(
            {
                "document_id": document_id,
                "source_uri": storage_path,
                "source_sha256": fingerprint,
                "published_at": metadata.get("published_at"),
                "parsed_at": now.isoformat(),
                "parse_quality_score": None,
                "page_count": None,
                "created_at": now.isoformat(),
            }
        )
        .execute()
    )
    version_id = doc_version_response.data[0]["id"]

    converter = DocumentConverter()
    converted = converter.convert(InputDocument.from_bytes(file_name, BytesIO(file_bytes))).document

    chunks, tables = chunk_document(converted, version_id)

    chunk_rows = [
        {
            "id": chunk.chunk_id,
            "doc_version_id": version_id,
            "section_path": chunk.section_path,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "kind": chunk.kind,
            "text": chunk.text,
            "token_count": chunk.token_count,
            "meta": chunk.meta,
            "hash": chunk.hash,
            "created_at": now.isoformat(),
        }
        for chunk in chunks
    ]
    if chunk_rows:
        client.table("chunks").upsert(chunk_rows, on_conflict="id").execute()

    table_rows = [
        {
            "id": table.table_id,
            "chunk_id": table.chunk_id,
            "doc_version_id": version_id,
            "page": table.page,
            "path": table.path,
            "nrows": table.nrows,
            "ncols": table.ncols,
            "cells": table.cells,
        }
        for table in tables
    ]
    if table_rows:
        client.table("tables").upsert(table_rows, on_conflict="id").execute()

    encoder = SentenceTransformer(settings.embedding_model)
    vectors = encoder.encode([chunk.text for chunk in chunks], normalize_embeddings=True)
    embedding_rows = [
        {
            "chunk_id": chunk.chunk_id,
            "embedding": vector.tolist(),
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    if embedding_rows:
        client.table("embeddings").upsert(embedding_rows, on_conflict="chunk_id").execute()

    client.table("files").upsert(
        {
            "doc_version_id": version_id,
            "bucket": settings.supabase_storage_bucket,
            "storage_key": storage_path,
            "byte_size": len(file_bytes),
            "mime_type": metadata.get("mime_type"),
        },
        on_conflict="doc_version_id"
    ).execute()

    return {
        "document_id": document_id,
        "document_version_id": version_id,
        "chunk_count": len(chunks),
        "embedding_count": len(embedding_rows),
    }
