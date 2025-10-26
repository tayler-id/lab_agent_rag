#!/bin/bash
set -e

source .env

# Read the SQL file
SQL_CONTENT=$(cat sql/schema.sql)

# Execute SQL via Supabase Management API
curl -X POST \
  "${SUPABASE_URL}/rest/v1/rpc/exec_sql" \
  -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"query\": $(jq -Rs . < sql/schema.sql)}"
