-- Run 4, J5: workspace roles and invitation links.
-- CreateEnum
CREATE TYPE "workspace_role" AS ENUM ('owner', 'admin', 'member', 'viewer');

ALTER TABLE "users" ADD COLUMN     "role" "workspace_role" NOT NULL DEFAULT 'member';


-- CreateTable
CREATE TABLE "invitations" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "token_hash" TEXT NOT NULL,
    "role" "workspace_role" NOT NULL,
    "created_by_id" UUID,
    "expires_at" TIMESTAMPTZ(3) NOT NULL,
    "accepted_at" TIMESTAMPTZ(3),
    "accepted_by_id" UUID,
    "revoked_at" TIMESTAMPTZ(3),
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "invitations_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "invitations_token_hash_key" ON "invitations"("token_hash");

-- CreateIndex
CREATE INDEX "invitations_workspace_id_created_at_idx" ON "invitations"("workspace_id", "created_at");

-- AddForeignKey
ALTER TABLE "invitations" ADD CONSTRAINT "invitations_workspace_id_fkey" FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Until now every user created their own workspace: they are its owner.
UPDATE "users" SET "role" = 'owner';

-- Ownership is transferred, never handed out by a link.
ALTER TABLE "invitations" ADD CONSTRAINT "invitations_role_not_owner" CHECK ("role" <> 'owner');
