-- Bring any model (run 2, G5): a workspace's model settings, with its API key encrypted.
CREATE TABLE "model_configs" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "label" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "base_url" TEXT,
    "model" TEXT NOT NULL,
    "cheap_model" TEXT,
    "api_key_ciphertext" TEXT,
    "api_key_last4" TEXT,
    "input_price" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "output_price" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "is_default" BOOLEAN NOT NULL DEFAULT false,
    "probe" JSONB,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "model_configs_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "model_configs_workspace_id_idx" ON "model_configs"("workspace_id");

ALTER TABLE "model_configs" ADD CONSTRAINT "model_configs_workspace_id_fkey"
    FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "runs" ADD COLUMN "model_config_id" UUID;

ALTER TABLE "runs" ADD CONSTRAINT "runs_model_config_id_fkey"
    FOREIGN KEY ("model_config_id") REFERENCES "model_configs"("id") ON DELETE SET NULL ON UPDATE CASCADE;
