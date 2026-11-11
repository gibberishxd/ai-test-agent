-- Run 4, J2: how the worker signs in to a target (a test account) before the agent starts.
CREATE TABLE "login_setups" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "origin" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "login_url" TEXT,
    "username" TEXT,
    "password_ciphertext" TEXT,
    "username_selector" TEXT,
    "password_selector" TEXT,
    "submit_selector" TEXT,
    "success_selector" TEXT,
    "storage_state_ciphertext" TEXT,
    "check_requested_at" TIMESTAMPTZ(3),
    "last_check" JSONB,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "login_setups_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "login_setups_workspace_id_origin_key" ON "login_setups"("workspace_id", "origin");

ALTER TABLE "login_setups" ADD CONSTRAINT "login_setups_workspace_id_fkey" FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;
