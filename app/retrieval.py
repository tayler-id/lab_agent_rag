"""Hybrid retrieval pipeline built on Supabase Postgres."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sentence_transformers import CrossEncoder, SentenceTransformer

from app.config import get_settings
from app.schemas import AskRequest, AskResponse, Citation, Passage
from app.supabase_client import get_client


class HybridRetriever:
    """Execute hybrid search combining FTS and vector similarity."""

    def __init__(self) -> None:
        settings = get_settings()
        self.encoder = SentenceTransformer(settings.embedding_model)
        self.reranker = CrossEncoder(settings.reranker_model)
        self.settings = settings

    def _vector_query(self, question: str, tenant_id: str, limit: int) -> list[dict[str, Any]]:
        client = get_client()
        embedding = self.encoder.encode(question, normalize_embeddings=True).tolist()
        response = (
            client.rpc(
                "search_chunks",
                {
                    "query_embedding": embedding,
                    "match_count": limit * 3,
                    "tenant": tenant_id,
                },
            ).execute()
        )
        return response.data or []

    def _rerank(self, query: str, candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not candidates:
            return []
        pairs = [(query, candidate["text"]) for candidate in candidates]
        scores = self.reranker.predict(pairs)
        reranked = [candidate | {"score": score} for candidate, score in zip(candidates, scores, strict=True)]
        reranked.sort(key=lambda item: item["score"], reverse=True)
        return reranked[:limit]

    def ask(self, payload: AskRequest) -> AskResponse:
        candidates = self._vector_query(payload.query, payload.tenant_id, payload.limit)
        reranked = self._rerank(payload.query, candidates, payload.limit)

        citations = [
            Citation(
                title=item["title"],
                version_id=item["doc_version_id"],
                page=item["page_start"],
                section=item.get("section_path"),
            )
            for item in reranked
        ]

        safety_notes: list[str] = []
        passages = []
        for item in reranked:
            safety_flag = any(token in item["text"].upper() for token in ("WARNING", "CAUTION", "DANGER"))
            if safety_flag:
                safety_notes.append(
                    "Review safety guidance in cited document before acting."
                )
            passages.append(
                Passage(
                    chunk_id=item["chunk_id"],
                    document_id=item["document_id"],
                    version_id=item["doc_version_id"],
                    title=item["title"],
                    page=item["page_start"],
                    section=item.get("section_path"),
                    kind=item.get("kind", "paragraph"),
                    text=item["text"],
                    score=float(item["score"]),
                    safety_flag=safety_flag,
                )
            )

        answer_text = "\n\n".join(p.text for p in passages)

        return AskResponse(
            answer=answer_text,
            citations=citations,
            passages=passages,
            notes=safety_notes,
            grounded=True,
            generated_at=datetime.utcnow(),
        )


def ask_question(payload: AskRequest) -> AskResponse:
    retriever = HybridRetriever()
    return retriever.ask(payload)
