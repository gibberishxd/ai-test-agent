-- Run 7, M1: benchmark v2 (docs/BENCHMARKS.md). Four unplanted behaviours of the demo apps were
-- fixed, which can move scores, so every result records the version of the apps it was measured
-- on, and the leaderboard keeps versions apart. Every result before this was measured on v1.

ALTER TABLE "benchmark_results" ADD COLUMN "benchmark_version" TEXT NOT NULL DEFAULT 'v1';
ALTER TABLE "benchmark_results"
  ADD CONSTRAINT "benchmark_results_version_format" CHECK (benchmark_version ~ '^v[0-9]+$');

-- The leaderboard, as in 20261115100000_estimated_cost, with the version as part of the key.
DROP MATERIALIZED VIEW model_leaderboard;
CREATE MATERIALIZED VIEW model_leaderboard AS
SELECT DISTINCT ON (benchmark_version, provider, model, judge, reviewer)
       benchmark_version, provider, model, judge, reviewer,
       id AS latest_result_id, created_at AS latest_at, git_commit,
       ai_recall, recall, precision, false_alarms,
       holdout_ai_recall, holdout_recall, holdout_false_alarms,
       avg_cost_usd, avg_duration_s,
       avg_estimated_cost_usd, estimated_cost_per_verified_bug,
       count(*) OVER (PARTITION BY benchmark_version, provider, model, judge, reviewer)::integer AS results
  FROM (SELECT *, details ->> 'reviewer' AS reviewer FROM benchmark_results
         WHERE NOT (details ? 'invalid')) valid
 ORDER BY benchmark_version, provider, model, judge, reviewer, created_at DESC;

CREATE UNIQUE INDEX model_leaderboard_key
  ON model_leaderboard (benchmark_version, coalesce(provider, ''), coalesce(model, ''), coalesce(judge, ''), coalesce(reviewer, ''));
GRANT SELECT ON model_leaderboard TO app_tenant;

DO $$
BEGIN
  IF current_user <> 'ata_owner' AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ata_owner') THEN
    ALTER MATERIALIZED VIEW model_leaderboard OWNER TO ata_owner;
  END IF;
END
$$;
