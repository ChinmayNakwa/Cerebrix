-- Ingestion schema: sources, stage manifest, chunks (vector + full-text) and the ontology graph.
-- Idempotent: safe to run against an existing database. {embedding_dim} is filled in by schema.py.

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per ingested source: the book PDF or a single lecture video.
CREATE TABLE IF NOT EXISTS sources (
    id            text PRIMARY KEY,              -- 'book:<slug>' or 'video:<youtube id>'
    kind          text NOT NULL CHECK (kind IN ('book', 'video')),
    title         text NOT NULL,
    uri           text,                          -- file path or video URL
    content_hash  text,
    metadata      jsonb NOT NULL DEFAULT '{{}}',
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Stage bookkeeping so an interrupted run resumes instead of starting over.
CREATE TABLE IF NOT EXISTS ingest_manifest (
    source_id    text NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    stage        text NOT NULL,
    input_hash   text NOT NULL,                  -- hash of the stage inputs and parameters
    status       text NOT NULL CHECK (status IN ('running', 'done', 'failed')),
    detail       jsonb NOT NULL DEFAULT '{{}}',    -- counts, timings, cache paths
    error        text,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    PRIMARY KEY (source_id, stage)
);

-- Parent chunks hold a whole section or transcript window; child chunks are what gets embedded.
CREATE TABLE IF NOT EXISTS chunks (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id     text NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    parent_id     bigint REFERENCES chunks (id) ON DELETE CASCADE,
    level         text NOT NULL CHECK (level IN ('parent', 'child')),
    modality      text NOT NULL CHECK (modality IN
                      ('text', 'table', 'formula', 'figure', 'transcript', 'slide_caption')),
    ordinal       integer NOT NULL,              -- reading order within the source
    content       text NOT NULL,
    context       text,                          -- short LLM-written line situating the chunk
    heading_path  text[] NOT NULL DEFAULT '{{}}',
    page_start    integer,
    page_end      integer,
    start_sec     real,
    end_sec       real,
    image_url     text,
    metadata      jsonb NOT NULL DEFAULT '{{}}',
    content_hash  text NOT NULL,
    embedding     vector({embedding_dim}),
    tsv           tsvector GENERATED ALWAYS AS
                      (to_tsvector('english', coalesce(context, '') || ' ' || content)) STORED,
    UNIQUE (source_id, level, content_hash)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_source_ordinal ON chunks (source_id, ordinal);
CREATE INDEX IF NOT EXISTS chunks_parent ON chunks (parent_id);
CREATE INDEX IF NOT EXISTS chunks_metadata_gin ON chunks USING gin (metadata jsonb_path_ops);

-- Ontology nodes. canonical_name is the normalised key used for entity resolution.
CREATE TABLE IF NOT EXISTS nodes (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type            text NOT NULL CHECK (type IN
                        ('Concept', 'Definition', 'Theorem', 'Formula', 'Example', 'Figure', 'Distribution')),
    name            text NOT NULL,
    canonical_name  text NOT NULL,
    description     text,
    aliases         text[] NOT NULL DEFAULT '{{}}',
    metadata        jsonb NOT NULL DEFAULT '{{}}',
    embedding       vector({embedding_dim}),
    UNIQUE (type, canonical_name)
);

CREATE INDEX IF NOT EXISTS nodes_embedding_hnsw ON nodes USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS edges (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    src_id             bigint NOT NULL REFERENCES nodes (id) ON DELETE CASCADE,
    dst_id             bigint NOT NULL REFERENCES nodes (id) ON DELETE CASCADE,
    type               text NOT NULL CHECK (type IN
                           ('prerequisite_of', 'defined_in', 'illustrates', 'special_case_of', 'uses', 'related_to')),
    weight             real NOT NULL DEFAULT 1.0,
    evidence_chunk_id  bigint REFERENCES chunks (id) ON DELETE SET NULL,
    metadata           jsonb NOT NULL DEFAULT '{{}}',
    UNIQUE (src_id, dst_id, type),
    CHECK (src_id <> dst_id)
);

CREATE INDEX IF NOT EXISTS edges_dst ON edges (dst_id, type);

-- Which chunks talk about which nodes; drives graph expansion at retrieval time.
CREATE TABLE IF NOT EXISTS node_mentions (
    node_id   bigint NOT NULL REFERENCES nodes (id) ON DELETE CASCADE,
    chunk_id  bigint NOT NULL REFERENCES chunks (id) ON DELETE CASCADE,
    PRIMARY KEY (node_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS node_mentions_chunk ON node_mentions (chunk_id);
