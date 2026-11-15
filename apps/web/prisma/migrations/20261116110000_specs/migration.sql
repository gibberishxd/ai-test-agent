-- Run 7, M3: testing against a team's own requirements (docs/DATABASE.md, "Specs").
--
-- targets: an app a workspace tests, by origin. specs: requirements per target (Markdown or text).
-- spec_chunks: a spec split at its headings, each piece with a 768-dimension embedding from a local
-- model (nomic-embed-text through Ollama, D94), searched with pgvector's cosine distance (HNSW).
-- All three are tenant tables: row-level security like every other workspace table. The worker
-- writes chunks; the web app writes targets and specs.

-- pgvector: the image is pgvector/pgvector:0.8.1-pg17 in dev, CI and production. A managed Postgres
-- must offer the extension (RDS, Cloud SQL and Supabase do).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE "targets" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "origin" TEXT NOT NULL,
    "name" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "targets_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "targets_origin_format" CHECK (origin ~ '^https?://[^/?#\s]+$'),
    CONSTRAINT "targets_name_length" CHECK (name IS NULL OR char_length(name) BETWEEN 1 AND 100)
);
CREATE UNIQUE INDEX "targets_workspace_id_origin_key" ON "targets"("workspace_id", "origin");
ALTER TABLE "targets" ADD CONSTRAINT "targets_workspace_id_fkey"
  FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "specs" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "target_id" UUID NOT NULL,
    "title" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "chunked_at" TIMESTAMPTZ(3),
    "embedding_model" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "specs_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "specs_title_length" CHECK (char_length(title) BETWEEN 1 AND 200),
    -- ~25k words: a product's acceptance criteria, not a manual. Keeps embedding and prompts small.
    CONSTRAINT "specs_body_length" CHECK (char_length(body) BETWEEN 1 AND 100000)
);
CREATE INDEX "specs_target_id_idx" ON "specs"("target_id");
ALTER TABLE "specs" ADD CONSTRAINT "specs_workspace_id_fkey"
  FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "specs" ADD CONSTRAINT "specs_target_id_fkey"
  FOREIGN KEY ("target_id") REFERENCES "targets"("id") ON DELETE CASCADE ON UPDATE CASCADE;
CREATE TRIGGER specs_updated_at BEFORE UPDATE ON specs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE "spec_chunks" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "spec_id" UUID NOT NULL,
    "target_id" UUID NOT NULL,
    "ord" INTEGER NOT NULL,
    "heading" TEXT NOT NULL,
    "text" TEXT NOT NULL,
    "embedding" vector(768) NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "spec_chunks_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "spec_chunks_ord_not_negative" CHECK (ord >= 0)
);
CREATE INDEX "spec_chunks_target_id_idx" ON "spec_chunks"("target_id");
-- Nearest chunks by cosine distance. HNSW: good recall without a training step, and it stays
-- correct as rows are added (IVFFlat would need rebuilding as specs grow).
CREATE INDEX "spec_chunks_embedding_idx" ON "spec_chunks" USING hnsw ("embedding" vector_cosine_ops);
ALTER TABLE "spec_chunks" ADD CONSTRAINT "spec_chunks_workspace_id_fkey"
  FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "spec_chunks" ADD CONSTRAINT "spec_chunks_spec_id_fkey"
  FOREIGN KEY ("spec_id") REFERENCES "specs"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "spec_chunks" ADD CONSTRAINT "spec_chunks_target_id_fkey"
  FOREIGN KEY ("target_id") REFERENCES "targets"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Row-level security: a tenant sees only its own workspace's rows.
ALTER TABLE "targets" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "targets" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());
ALTER TABLE "specs" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "specs" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());
ALTER TABLE "spec_chunks" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "spec_chunks" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

GRANT SELECT, INSERT, UPDATE, DELETE ON targets, specs, spec_chunks TO app_tenant;

DO $$
BEGIN
  IF current_user = 'ata_owner' OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ata_owner') THEN
    RETURN;
  END IF;
  ALTER TABLE targets OWNER TO ata_owner;
  ALTER TABLE specs OWNER TO ata_owner;
  ALTER TABLE spec_chunks OWNER TO ata_owner;
END
$$;
