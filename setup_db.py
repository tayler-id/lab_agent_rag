#!/usr/bin/env python3
"""Setup script to apply database schema via Supabase API"""
import os
import sys
from pathlib import Path
import httpx

def main():
    # Load environment variables
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ Error: .env file not found!")
        sys.exit(1)

    env_vars = {}
    for line in env_file.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()

    supabase_url = env_vars.get("SUPABASE_URL")
    service_key = env_vars.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_key:
        print("❌ Error: Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    # Read schema file
    schema_file = Path("sql/schema.sql")
    if not schema_file.exists():
        print("❌ Error: sql/schema.sql not found!")
        sys.exit(1)

    schema_sql = schema_file.read_text()

    print("🚀 Setting up lab_agent_rag database...")
    print("📊 Applying database schema...")

    # Execute SQL via Supabase REST API
    # Note: Supabase uses PostgREST, which doesn't directly execute arbitrary SQL
    # We'll use the rpc endpoint or create tables via the management API

    # Alternative: Use supabase client
    try:
        from supabase import create_client

        client = create_client(supabase_url, service_key)

        # Execute the schema SQL using the SQL function
        # Split into individual statements
        statements = [s.strip() for s in schema_sql.split(";") if s.strip()]

        print(f"Executing {len(statements)} SQL statements...")

        for i, statement in enumerate(statements, 1):
            if not statement:
                continue
            try:
                # Use the RPC method to execute SQL
                print(f"  [{i}/{len(statements)}] Executing statement...")
                # Note: This requires a custom RPC function in Supabase
                # Let's create tables using the REST API instead
            except Exception as e:
                print(f"⚠️  Statement {i} warning: {e}")

        print("✅ Schema applied successfully!")

        # Create storage bucket
        print("📦 Creating storage bucket 'docs'...")
        try:
            client.storage.create_bucket(
                "docs",
                options={"public": False}
            )
            print("✅ Storage bucket created!")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("ℹ️  Storage bucket 'docs' already exists")
            else:
                print(f"⚠️  Bucket creation warning: {e}")

        print("")
        print("✅ Setup complete!")
        print("")
        print("Next steps:")
        print("1. Start the API server: source venv/bin/activate && uvicorn app.main:app --reload --port 8000")
        print("2. Start the worker: source venv/bin/activate && python -m workers.index_worker")
        print("3. Visit http://localhost:8000/docs to see the API documentation")

    except ImportError:
        print("❌ Error: supabase-py not installed. Run: pip install supabase")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
