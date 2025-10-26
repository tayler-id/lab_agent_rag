"""Supabase client factory."""
from supabase import create_client, Client

from app.config import get_settings


_client: Client | None = None


def get_client() -> Client:
    """Return a cached Supabase client."""

    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client
