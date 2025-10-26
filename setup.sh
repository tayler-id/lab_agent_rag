#!/bin/bash
set -e

echo "🚀 Setting up lab_agent_rag project..."

# Load environment variables
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    exit 1
fi

source .env

# Apply database schema
echo "📊 Applying database schema..."
psql "$SUPABASE_DB_URL" -f sql/schema.sql

# Create storage bucket using Supabase API
echo "📦 Creating storage bucket 'docs'..."
curl -X POST \
  "${SUPABASE_URL}/storage/v1/bucket" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "docs",
    "name": "docs",
    "public": false,
    "file_size_limit": 52428800,
    "allowed_mime_types": ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword", "text/plain"]
  }'

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Start the API server: source venv/bin/activate && uvicorn app.main:app --reload --port 8000"
echo "2. Start the worker: source venv/bin/activate && python -m workers.index_worker"
echo "3. Visit http://localhost:8000/docs to see the API documentation"
