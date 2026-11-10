-- Run 3, H4: the benchmark page, leaderboard and home page all read the newest results
-- (ORDER BY created_at DESC LIMIT n). Without this index Postgres scans and sorts every row
-- (docs/DATABASE.md has the before/after plans).
CREATE INDEX "benchmark_results_created_at_idx" ON "benchmark_results"("created_at");
