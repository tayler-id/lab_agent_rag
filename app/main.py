"""FastAPI service exposing ingestion and question answering endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import retrieval
from app.config import get_settings
from app.schemas import AskRequest, AskResponse, HealthResponse, UploadResponse
from ingestion.ingest_service import ingest_document

app = FastAPI(title="Lab Agent RAG", version="0.1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version or "0.0.0")


@app.post("/upload", response_model=UploadResponse)
async def upload_document(
    tenant_id: str,
    file: Annotated[UploadFile, File(...)],
) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")

    file_bytes = await file.read()
    result = ingest_document(
        tenant_id=tenant_id,
        file_name=file.filename,
        file_bytes=file_bytes,
        metadata={"mime_type": file.content_type},
    )
    return UploadResponse(**result)


@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest) -> AskResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be blank")
    response = retrieval.ask_question(payload)
    return response


@app.get("/docs/{document_version_id}")
async def get_document_link(document_version_id: str) -> dict[str, str]:
    settings = get_settings()
    return {
        "download_url": f"{settings.supabase_url}/storage/v1/object/public/{settings.supabase_storage_bucket}/{document_version_id}"
    }
