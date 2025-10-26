#!/usr/bin/env python3
"""Apply database schema using Supabase client"""
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: Missing environment variables")
    exit(1)

client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("🚀 Setting up database and storage...")

# Create storage bucket
print("📦 Creating storage bucket 'docs'...")
try:
    result = client.storage.create_bucket("docs", options={"public": False})
    print("✅ Storage bucket 'docs' created!")
except Exception as e:
    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
        print("ℹ️  Storage bucket 'docs' already exists")
    else:
        print(f"⚠️  Bucket error: {e}")

print("")
print("📊 To apply the database schema, please:")
print("1. Go to your Supabase Dashboard: https://supabase.com/dashboard/project/olpitkhqjloduzssbnrl/sql/new")
print("2. Copy the contents of 'sql/schema.sql'")
print("3. Paste into the SQL Editor")
print("4. Click 'Run' or press Cmd+Enter")
print("")
print("Once that's done, you can:")
print("• Start the API: source venv/bin/activate && uvicorn app.main:app --reload --port 8000")
print("• Start the worker: source venv/bin/activate && python -m workers.index_worker")
