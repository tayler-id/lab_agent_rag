"""Simple worker that polls Supabase for pending ingestion jobs."""
from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings
from app.supabase_client import get_client
from ingestion.ingest_service import ingest_document


async def fetch_pending_jobs(limit: int = 10) -> list[dict[str, Any]]:
    client = get_client()
    response = (
        client.table("jobs")
        .select("id, tenant_id, payload")
        .eq("status", "pending")
        .limit(limit)
        .execute()
    )
    return response.data or []


async def mark_job(job_id: str, status: str, error: str | None = None) -> None:
    client = get_client()
    update = {"status": status}
    if error:
        update["error_msg"] = error
    client.table("jobs").update(update).eq("id", job_id).execute()


async def run_once() -> None:
    jobs = await fetch_pending_jobs()
    for job in jobs:
        job_id = job["id"]
        payload = job["payload"] or {}
        try:
            storage_key = payload["storage_key"]
            file_name = payload.get("file_name", storage_key.split("/")[-1])
            tenant_id = payload["tenant_id"]
            settings = get_settings()
            storage = get_client().storage().from_(settings.supabase_storage_bucket)
            data = storage.download(storage_key)
            ingest_document(
                tenant_id=tenant_id,
                file_name=file_name,
                file_bytes=data,
                metadata={"mime_type": payload.get("mime_type")},
            )
            mark_job(job_id, "completed")
        except Exception as exc:  # noqa: BLE001
            mark_job(job_id, "failed", str(exc))


async def main(poll_interval: float = 5.0) -> None:
    while True:
        await run_once()
        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    asyncio.run(main())
