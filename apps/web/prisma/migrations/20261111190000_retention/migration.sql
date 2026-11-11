-- Run 4, J6: retention per workspace, and which runs it already purged.
ALTER TABLE "runs" ADD COLUMN "purged_at" TIMESTAMPTZ(3);

ALTER TABLE "workspaces" ADD COLUMN "retention_days" INTEGER NOT NULL DEFAULT 30;
