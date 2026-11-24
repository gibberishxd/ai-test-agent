-- Deep mode (run 9): a second agent engine next to the current loop, chosen per run.
--
-- runs.engine         'loop' (the current agent, the default) or 'deep'. `mode` keeps meaning
--                     passive / interactive, because every safety rule depends on it; a deep
--                     run is always interactive.
-- runs.engine_model   the model a deep run asked for (a pinned ID); NULL = the worker's default.
-- runs.coverage       what a deep run covered: its map of the app, its test plan, which plan
--                     items it ticked off, and what it needs to resume. Saved as it goes.
-- runs.paused_reason  why a paused run stopped (a plan's usage limit); it can be resumed.
-- run_status 'paused' a run that stopped on a usage limit and can continue later.
-- bug_status 'unverified'  a finding that neither replay nor a re-measurement could check: kept
--                     apart from verified findings, never counted as found.
-- workspaces.deep_max_steps / deep_max_seconds  the workspace's deep-mode limits; NULL = the
--                     product defaults (400 steps, 60 minutes). A run can only lower them.

CREATE TYPE "run_engine" AS ENUM ('loop', 'deep');

ALTER TYPE "run_status" ADD VALUE 'paused';
ALTER TYPE "bug_status" ADD VALUE 'unverified';

ALTER TABLE "runs" ADD COLUMN "engine" "run_engine" NOT NULL DEFAULT 'loop';
ALTER TABLE "runs" ADD COLUMN "engine_model" TEXT;
ALTER TABLE "runs" ADD COLUMN "coverage" JSONB;
ALTER TABLE "runs" ADD COLUMN "paused_reason" TEXT;
ALTER TABLE "runs"
  ADD CONSTRAINT "runs_engine_model_deep_only" CHECK (engine_model IS NULL OR engine = 'deep');
ALTER TABLE "runs"
  ADD CONSTRAINT "runs_engine_model_pinned" CHECK (engine_model IS NULL OR engine_model ~ '^claude-[a-z]+(-[0-9]+)+$');

ALTER TABLE "workspaces" ADD COLUMN "deep_max_steps" INTEGER;
ALTER TABLE "workspaces" ADD COLUMN "deep_max_seconds" INTEGER;
ALTER TABLE "workspaces"
  ADD CONSTRAINT "workspaces_deep_max_steps_positive" CHECK (deep_max_steps IS NULL OR deep_max_steps > 0);
ALTER TABLE "workspaces"
  ADD CONSTRAINT "workspaces_deep_max_seconds_positive" CHECK (deep_max_seconds IS NULL OR deep_max_seconds > 0);
