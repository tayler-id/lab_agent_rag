#!/usr/bin/env python3
"""Apply database schema using direct SQL execution"""
import os
from pathlib import Path
from dotenv import load_dotenv
import httpx

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: Missing environment variables")
    exit(1)

# Read schema file
schema_sql = Path("sql/schema.sql").read_text()

print("🚀 Applying database schema via Supabase API...")

# Try using the database REST API directly
# Supabase exposes PostgreSQL via PostgREST, but for DDL we need to use supabase_admin schema
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Split statements and execute one by one
statements = [s.strip() + ";" for s in schema_sql.split(";") if s.strip()]

print(f"📊 Executing {len(statements)} SQL statements...\n")

success_count = 0
failed_count = 0

for i, statement in enumerate(statements, 1):
    if not statement.strip() or statement.strip() == ";":
        continue

    # Show first 80 chars of statement
    preview = statement[:80].replace("\n", " ")
    print(f"[{i}/{len(statements)}] {preview}...")

    # Use Supabase's query API
    try:
        response = httpx.post(
            f"{SUPABASE_URL}/rest/v1/rpc/exec",
            headers=headers,
            json={"sql": statement},
            timeout=30.0
        )

        if response.status_code in [200, 201, 204]:
            print(f"  ✅ Success")
            success_count += 1
        else:
            print(f"  ⚠️  Status {response.status_code}: {response.text[:100]}")
            failed_count += 1
    except Exception as e:
        print(f"  ⚠️  Error: {str(e)[:100]}")
        failed_count += 1

print(f"\n{'='*60}")
print(f"✅ Completed: {success_count} successful, {failed_count} failed")
print(f"{'='*60}\n")

if failed_count > 0:
    print("⚠️  Some statements failed. This might be OK if tables already exist.")
    print("   Please verify in Supabase Dashboard → Table Editor")
    print(f"   {SUPABASE_URL.replace('https://', 'https://supabase.com/dashboard/project/')}/editor")
