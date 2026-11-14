-- Run 6, L1: claude-cli runs made measurable (docs/DATABASE.md, "Cost").
--
-- steps / runs: the model the provider reported, the cached share of input_tokens (cache reads
-- and writes) and the API-equivalent cost: what the calls would cost on the Claude API at list
-- price. claude-cli runs are charged $0 on the owner's Pro plan, so for them it is an estimate;
-- for a provider that charges it equals cost_usd. Budgets (MAX_RUN_COST_USD) use it.
-- benchmark_results: the estimate per run and per verified planted bug; null = not measured.
-- model_leaderboard is recreated to show both.

ALTER TABLE "steps"
  ADD COLUMN "model" TEXT,
  ADD COLUMN "cache_read_tokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "cache_write_tokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "estimated_cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE "runs"
  ADD COLUMN "cache_read_tokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "cache_write_tokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "estimated_cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN "reviewer_cache_read_tokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "reviewer_cache_write_tokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "reviewer_estimated_cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE "benchmark_results"
  ADD COLUMN "avg_estimated_cost_usd" DOUBLE PRECISION,
  ADD COLUMN "estimated_cost_per_verified_bug" DOUBLE PRECISION;

-- Older rows: what was charged is the best estimate there is (claude-cli rows stay 0, unknown).
UPDATE "steps" SET "estimated_cost_usd" = "cost_usd" WHERE "cost_usd" > 0;
UPDATE "runs" SET "estimated_cost_usd" = "cost_usd", "reviewer_estimated_cost_usd" = "reviewer_cost_usd"
 WHERE "cost_usd" > 0 OR "reviewer_cost_usd" > 0;

ALTER TABLE "steps"
  ADD CONSTRAINT "steps_estimates_not_negative" CHECK (
    cache_read_tokens >= 0 AND cache_write_tokens >= 0 AND estimated_cost_usd >= 0);
ALTER TABLE "runs"
  ADD CONSTRAINT "runs_estimates_not_negative" CHECK (
    cache_read_tokens >= 0 AND cache_write_tokens >= 0 AND estimated_cost_usd >= 0
    AND reviewer_cache_read_tokens >= 0 AND reviewer_cache_write_tokens >= 0
    AND reviewer_estimated_cost_usd >= 0);
ALTER TABLE "benchmark_results"
  ADD CONSTRAINT "benchmark_results_estimates_not_negative" CHECK (
    (avg_estimated_cost_usd IS NULL OR avg_estimated_cost_usd >= 0)
    AND (estimated_cost_per_verified_bug IS NULL OR estimated_cost_per_verified_bug >= 0));

-- The leaderboard, as in 20261112110000_database_rules plus the two estimates.
DROP MATERIALIZED VIEW model_leaderboard;
CREATE MATERIALIZED VIEW model_leaderboard AS
SELECT DISTINCT ON (provider, model, judge, reviewer)
       provider, model, judge, reviewer,
       id AS latest_result_id, created_at AS latest_at, git_commit,
       ai_recall, recall, precision, false_alarms,
       holdout_ai_recall, holdout_recall, holdout_false_alarms,
       avg_cost_usd, avg_duration_s,
       avg_estimated_cost_usd, estimated_cost_per_verified_bug,
       count(*) OVER (PARTITION BY provider, model, judge, reviewer)::integer AS results
  FROM (SELECT *, details ->> 'reviewer' AS reviewer FROM benchmark_results
         WHERE NOT (details ? 'invalid')) valid
 ORDER BY provider, model, judge, reviewer, created_at DESC;

CREATE UNIQUE INDEX model_leaderboard_key
  ON model_leaderboard (coalesce(provider, ''), coalesce(model, ''), coalesce(judge, ''), coalesce(reviewer, ''));
GRANT SELECT ON model_leaderboard TO app_tenant;

DO $$
BEGIN
  IF current_user <> 'ata_owner' AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ata_owner') THEN
    ALTER MATERIALIZED VIEW model_leaderboard OWNER TO ata_owner;
  END IF;
END
$$;
