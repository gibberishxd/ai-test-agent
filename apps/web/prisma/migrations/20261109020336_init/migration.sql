-- CreateEnum
CREATE TYPE "run_mode" AS ENUM ('passive', 'interactive');

-- CreateEnum
CREATE TYPE "run_status" AS ENUM ('queued', 'running', 'done', 'failed', 'stopped');

-- CreateEnum
CREATE TYPE "severity" AS ENUM ('critical', 'high', 'medium', 'low');

-- CreateEnum
CREATE TYPE "bug_source" AS ENUM ('deterministic', 'agent');

-- CreateEnum
CREATE TYPE "bug_status" AS ENUM ('candidate', 'confirmed', 'dismissed');

-- CreateTable
CREATE TABLE "workspaces" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "name" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "monthly_run_quota" INTEGER NOT NULL DEFAULT 50,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "workspaces_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "users" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "email" TEXT NOT NULL,
    "name" TEXT,
    "workspace_id" UUID NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "runs" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "created_by_id" UUID,
    "target_url" TEXT NOT NULL,
    "mode" "run_mode" NOT NULL DEFAULT 'passive',
    "focus" TEXT,
    "status" "run_status" NOT NULL DEFAULT 'queued',
    "stop_requested" BOOLEAN NOT NULL DEFAULT false,
    "claimed_by" TEXT,
    "provider" TEXT,
    "model" TEXT,
    "pages_visited" INTEGER NOT NULL DEFAULT 0,
    "step_count" INTEGER NOT NULL DEFAULT 0,
    "input_tokens" INTEGER NOT NULL DEFAULT 0,
    "output_tokens" INTEGER NOT NULL DEFAULT 0,
    "cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "error" TEXT,
    "summary" JSONB,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "started_at" TIMESTAMPTZ(3),
    "finished_at" TIMESTAMPTZ(3),

    CONSTRAINT "runs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "steps" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "run_id" UUID NOT NULL,
    "index" INTEGER NOT NULL,
    "action" TEXT NOT NULL,
    "args" JSONB NOT NULL DEFAULT '{}',
    "reasoning" TEXT,
    "url" TEXT,
    "screenshot" TEXT,
    "events" JSONB NOT NULL DEFAULT '[]',
    "blocked" BOOLEAN NOT NULL DEFAULT false,
    "block_reason" TEXT,
    "input_tokens" INTEGER NOT NULL DEFAULT 0,
    "output_tokens" INTEGER NOT NULL DEFAULT 0,
    "cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "steps_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "bugs" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "run_id" UUID NOT NULL,
    "title" TEXT NOT NULL,
    "severity" "severity" NOT NULL,
    "category" TEXT NOT NULL,
    "page_url" TEXT NOT NULL,
    "expected" TEXT,
    "actual" TEXT,
    "repro_steps" JSONB NOT NULL DEFAULT '[]',
    "evidence" JSONB NOT NULL DEFAULT '{}',
    "reasoning" TEXT,
    "screenshot" TEXT,
    "step_indexes" INTEGER[] DEFAULT ARRAY[]::INTEGER[],
    "source" "bug_source" NOT NULL,
    "status" "bug_status" NOT NULL DEFAULT 'candidate',
    "dismiss_reason" TEXT,
    "duplicate_of_id" UUID,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "bugs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "benchmark_results" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "git_commit" TEXT NOT NULL,
    "runs_buggy" INTEGER NOT NULL,
    "recall" DOUBLE PRECISION NOT NULL,
    "precision" DOUBLE PRECISION NOT NULL,
    "false_alarms" DOUBLE PRECISION NOT NULL,
    "avg_cost_usd" DOUBLE PRECISION NOT NULL,
    "avg_duration_s" DOUBLE PRECISION NOT NULL,
    "details" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "benchmark_results_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_log" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "user_id" UUID,
    "action" TEXT NOT NULL,
    "target_url" TEXT,
    "mode" "run_mode",
    "run_id" UUID,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_log_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "workspaces_slug_key" ON "workspaces"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE INDEX "users_workspace_id_idx" ON "users"("workspace_id");

-- CreateIndex
CREATE INDEX "runs_status_created_at_idx" ON "runs"("status", "created_at");

-- CreateIndex
CREATE INDEX "runs_workspace_id_created_at_idx" ON "runs"("workspace_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "steps_run_id_index_key" ON "steps"("run_id", "index");

-- CreateIndex
CREATE INDEX "bugs_run_id_idx" ON "bugs"("run_id");

-- CreateIndex
CREATE INDEX "benchmark_results_provider_created_at_idx" ON "benchmark_results"("provider", "created_at");

-- CreateIndex
CREATE INDEX "audit_log_workspace_id_created_at_idx" ON "audit_log"("workspace_id", "created_at");

-- AddForeignKey
ALTER TABLE "users" ADD CONSTRAINT "users_workspace_id_fkey" FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "runs" ADD CONSTRAINT "runs_workspace_id_fkey" FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "runs" ADD CONSTRAINT "runs_created_by_id_fkey" FOREIGN KEY ("created_by_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "steps" ADD CONSTRAINT "steps_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "bugs" ADD CONSTRAINT "bugs_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_log" ADD CONSTRAINT "audit_log_workspace_id_fkey" FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_log" ADD CONSTRAINT "audit_log_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
