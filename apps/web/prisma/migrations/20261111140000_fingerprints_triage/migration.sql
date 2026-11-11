-- Run 4, J4: fingerprints to recognise a bug across runs, and triage that follows them.
ALTER TABLE "bugs" ADD COLUMN     "fingerprint" TEXT,
ADD COLUMN     "suppressed" BOOLEAN NOT NULL DEFAULT false;


-- CreateTable
CREATE TABLE "finding_triage" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "origin" TEXT NOT NULL,
    "fingerprint" TEXT NOT NULL,
    "state" TEXT NOT NULL,
    "comment" TEXT,
    "title" TEXT NOT NULL,
    "updated_by_id" UUID,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "finding_triage_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "finding_triage_workspace_id_origin_fingerprint_key" ON "finding_triage"("workspace_id", "origin", "fingerprint");

-- AddForeignKey
ALTER TABLE "finding_triage" ADD CONSTRAINT "finding_triage_workspace_id_fkey" FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Only these three decisions exist (Prisma can't express a CHECK; the database enforces it).
ALTER TABLE "finding_triage" ADD CONSTRAINT "finding_triage_state_check" CHECK ("state" IN ('confirmed', 'false_positive', 'wont_fix'));
