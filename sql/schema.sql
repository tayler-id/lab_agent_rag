-- Core schema for Supabase Postgres
create extension if not exists vector;

create table if not exists tenants (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now()
);

create table if not exists documents (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    title text not null,
    vendor text,
    model text,
    doc_type text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, title)
);

create table if not exists document_versions (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null references documents(id) on delete cascade,
    source_uri text not null,
    source_sha256 text not null,
    published_at date,
    parsed_at timestamptz,
    parse_quality_score numeric,
    page_count integer,
    created_at timestamptz not null default now(),
    unique (document_id, source_sha256)
);

create table if not exists files (
    id uuid primary key default gen_random_uuid(),
    doc_version_id uuid not null references document_versions(id) on delete cascade,
    bucket text not null,
    storage_key text not null,
    byte_size bigint,
    mime_type text,
    created_at timestamptz not null default now(),
    unique (doc_version_id)
);

create table if not exists chunks (
    id text primary key,
    doc_version_id uuid not null references document_versions(id) on delete cascade,
    section_path text,
    page_start integer,
    page_end integer,
    kind text not null,
    text text not null,
    token_count integer,
    meta jsonb default '{}',
    hash text not null,
    created_at timestamptz not null default now()
);

create table if not exists tables (
    id text primary key,
    chunk_id text not null references chunks(id) on delete cascade,
    doc_version_id uuid not null references document_versions(id) on delete cascade,
    page integer,
    path text,
    nrows integer,
    ncols integer,
    cells jsonb not null
);

create table if not exists embeddings (
    chunk_id text primary key references chunks(id) on delete cascade,
    embedding vector(768) not null
);

create table if not exists jobs (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    payload jsonb not null,
    status text not null default 'pending',
    error_msg text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create materialized view if not exists chunk_ft as
    select
        c.id,
        c.doc_version_id,
        c.text,
        to_tsvector('english', coalesce(c.text, '')) as tsv
    from chunks c;

create index if not exists idx_chunk_ft_tsv on chunk_ft using gin(tsv);

create index if not exists idx_chunks_doc_version on chunks(doc_version_id, page_start);

create index if not exists idx_chunks_hash on chunks(hash);

create index if not exists idx_tables_chunk on tables(chunk_id);

create index if not exists idx_documents_tenant on documents(tenant_id);

create policy "tenant-isolation-documents" on documents
using (tenant_id = auth.uid());

create policy "tenant-isolation-document-versions" on document_versions
using (exists (
    select 1 from documents d where d.id = document_versions.document_id and d.tenant_id = auth.uid()
));

create policy "tenant-isolation-chunks" on chunks
using (exists (
    select 1 from document_versions dv join documents d on dv.document_id = d.id
    where dv.id = chunks.doc_version_id and d.tenant_id = auth.uid()
));

create policy "tenant-isolation-embeddings" on embeddings
using (exists (
    select 1 from chunks c join document_versions dv on c.doc_version_id = dv.id join documents d on dv.document_id = d.id
    where c.id = embeddings.chunk_id and d.tenant_id = auth.uid()
));

create policy "tenant-isolation-jobs" on jobs
using (tenant_id = auth.uid());

create or replace function refresh_chunk_ft()
returns trigger as $$
begin
    refresh materialized view concurrently chunk_ft;
    return null;
end;
$$ language plpgsql;

create trigger refresh_chunk_ft_trigger
after insert or update or delete on chunks
for each statement execute function refresh_chunk_ft();

create or replace function search_chunks(query_embedding vector(768), match_count int, tenant uuid)
returns table(
    chunk_id text,
    document_id uuid,
    doc_version_id uuid,
    title text,
    section_path text,
    text text,
    page_start integer,
    kind text,
    score float
) language plpgsql as $$
begin
    return query
    select
        c.id as chunk_id,
        d.id as document_id,
        dv.id as doc_version_id,
        d.title,
        c.section_path,
        c.text,
        c.page_start,
        c.kind,
        (1 - (e.embedding <=> query_embedding)) as score
    from embeddings e
    join chunks c on e.chunk_id = c.id
    join document_versions dv on c.doc_version_id = dv.id
    join documents d on dv.document_id = d.id
    where d.tenant_id = tenant
    order by e.embedding <=> query_embedding
    limit match_count;
end;
$$;
