# Build a clean, scalable document-answering agent (plain English guide)

This guide explains—in simple language—how to build a system that takes the files you already have, turns them into searchable notes, and answers questions with page-level citations. It uses Supabase (Postgres + storage + auth), but you can self-host it so everything stays under your control.

## The idea in one sentence

Drop a file into your "Files Box," let a helper split it into short passages with page numbers, store those passages and their fingerprints, then answer questions by pulling back the best passages and showing where they came from.

## The moving parts (no buzzwords)

| Piece | What it really is | What it does |
| --- | --- | --- |
| **Files Box** | A private Supabase storage bucket | Holds the original PDFs, Word docs, and spreadsheets |
| **Library** | Supabase Postgres tables | Keeps track of documents, their versions, and every short passage |
| **Indexer helper** | A background script you run | Reads each file, slices it into passages, scores quality, stores passages + fingerprints |
| **Answer service** | Your FastAPI endpoint | Finds matching passages (keyword + meaning), reranks them locally, and returns citations |

## A clean schema that actually scales

Keep the schema small but explicit. Each upload becomes a **document version** so old citations never break. Passages keep section paths and page ranges so you know exactly where an answer came from.

```text
TENANTS
  id, name

DOCUMENTS
  id, tenant_id, title, vendor?, model?, doc_type?

DOCUMENT_VERSIONS
  id, document_id, storage_bucket, storage_key,
  source_uri?, source_sha256, published_at?, parsed_at,
  parse_quality_score, page_count

CHUNKS (your short passages)
  id, doc_version_id, section_path ("2 > Maintenance > Filters"),
  page_start, page_end, kind (paragraph|table|warning|procedure|figure),
  text, token_count, meta jsonb, chunk_sha256

EMBEDDINGS
  chunk_id (FK), vector (pgvector column)

TABLES (for structured specs)
  id, chunk_id, page, path, nrows, ncols, cells jsonb

FILES (raw uploads)
  doc_version_id, byte_size, mime_type

JOBS (ingestion log)
  id, doc_version_id, status, error_message?, timings jsonb
```

Add Row-Level Security policies keyed by `tenant_id` on every table, and unique constraints on `source_sha256` (per version) and `chunk_sha256` (per chunk) so you skip duplicates automatically.

## Indexer helper flow (plain steps)

1. **Notice an upload.** Either watch the storage bucket or have the uploader hit a `/upload` endpoint that records a job.
2. **Create a document version.** Store the file location, checksum, and tenant ID.
3. **Parse the file.** Use Docling (great layout + tables). Keep page numbers and tables separate. If OCR is needed later, add it as a fallback.
4. **Score the parse.** Simple rules: coverage %, table detection, warning flags. If the score is low, retry with another method or mark the job for review.
5. **Chunk the text.** Slice into overlapping passages (3–8 sentences), keep the section path, and classify the chunk type.
6. **Hash each chunk.** Skip storing duplicates by checking `chunk_sha256`.
7. **Store the chunks.** Insert rows into `chunks`, update the FTS column, save tables in `tables`.
8. **Create fingerprints.** Use a local embedding model (e.g., `bge-m3`) and store vectors in `embeddings` with a pgvector index.
9. **Mark the job done.** Update `jobs` so the UI can show “Indexed.”

## Answer service flow

1. Receive `/ask` with `{ question, tenant_id, filters? }`.
2. Run **keyword search** using Postgres full-text search on `chunks`.
3. Run **meaning search** by embedding the question and doing a pgvector similarity query.
4. Merge and score results (weight both signals), keep the top ~25.
5. Optionally run a **local reranker** (BGE reranker v2 m3) to pick the best 6–10 passages.
6. Return either:
   - the reranked passages directly, or
   - a short stitched answer (call your own vLLM server if you have a GPU)
7. Always include citations: `{ title, version_id, page_start, section_path }`.
8. If a chunk contains WARNING/CAUTION/DANGER, attach a safety note to the answer.

## Simple UI checklist

- **Upload tab**: drag-and-drop → show file name, status (Parsing → Indexed), and parse quality.
- **Ask tab**: question box → display either the top passages or a short answer with citations.
- **Open source page**: link straight to the PDF page (version-specific) so the answer stays grounded.
- **Flag incorrect** button: store user feedback with the cited chunk IDs.

## Daily habits that keep it healthy

- Re-run the indexer nightly on flagged documents.
- Keep a tiny eval set (real + synthetic questions) and run it each night to catch regressions.
- Backup Supabase (or your self-hosted Postgres) on a schedule; pg_dump + storage sync is enough.
- Watch RLS policies whenever you add tables—multi-tenant safety lives there.

## Why this stays clean over time

- **Versioned documents** mean old citations still point to the right page even after an update.
- **Chunk hashes** prevent duplicates and speed up re-indexing.
- **Tables kept intact** make spec answers trustworthy.
- **Hybrid search + local rerank** gives accuracy without external APIs.
- **All Supabase** (auth, storage, Postgres, pgvector) keeps the stack simple and self-hostable.

Build it step-by-step, ship retrieval + citations first, and layer on generation only when you have the hardware ready. This blueprint keeps your data tidy, your answers explainable, and your future changes safe.

## Repository quick start

This repo now ships a runnable slice of the architecture described above:

- `pyproject.toml` – application dependencies (FastAPI, Docling, sentence-transformers, Supabase client)
- `sql/schema.sql` – Postgres DDL (tables, indexes, RLS policies, hybrid-search RPC)
- `app/` – FastAPI service exposing `/health`, `/upload`, `/ask`, and `/docs/:version_id`
- `ingestion/` – parsing + chunking pipeline backed by Docling and sentence-transformers
- `workers/index_worker.py` – polling worker that processes queued ingestion jobs

### Install dependencies

```bash
uv sync  # or: pip install -e .[dev]
```

### Apply the database schema

```bash
psql "$SUPABASE_DB_URL" -f sql/schema.sql
```

### Run the API server

```bash
uvicorn app.main:app --reload --port 8000
```

Set the following environment variables before running the service:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_ANON_KEY`
- `SUPABASE_STORAGE_BUCKET` (defaults to `docs`)

### Kick off the ingestion worker

```bash
python -m workers.index_worker
```

Upload a file via `/upload` (or push a job into the `jobs` table) and query it with `/ask`. The worker uses Supabase Storage to download new files, parses them with Docling, writes normalized chunks and tables, generates embeddings, and stores everything in Postgres.
