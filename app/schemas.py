"""Pydantic models used across the API."""
from datetime import datetime
from typing import Literal, Sequence

from pydantic import BaseModel, Field

ChunkKind = Literal["paragraph", "table", "figure", "warning", "procedure"]


class UploadResponse(BaseModel):
    document_id: str
    document_version_id: str
    chunk_count: int
    embedding_count: int


class AskRequest(BaseModel):
    query: str = Field(..., min_length=3)
    tenant_id: str
    limit: int = Field(10, ge=1, le=20)


class Citation(BaseModel):
    title: str
    version_id: str
    page: int
    section: str | None = None


class Passage(BaseModel):
    chunk_id: str
    document_id: str
    version_id: str
    title: str
    page: int
    section: str | None = None
    kind: ChunkKind
    text: str
    score: float
    safety_flag: bool


class AskResponse(BaseModel):
    answer: str
    citations: Sequence[Citation]
    passages: Sequence[Passage]
    notes: Sequence[str] = ()
    grounded: bool = True
    generated_at: datetime


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
