-- Honest benchmark (run 2, G3): AI-only recall, the holdout app's scores, who judged, and
-- the commit a rescore ran on. Nullable: older rows didn't record them.
ALTER TABLE "benchmark_results"
    ADD COLUMN "ai_recall" DOUBLE PRECISION,
    ADD COLUMN "holdout_runs_buggy" INTEGER,
    ADD COLUMN "holdout_recall" DOUBLE PRECISION,
    ADD COLUMN "holdout_ai_recall" DOUBLE PRECISION,
    ADD COLUMN "holdout_precision" DOUBLE PRECISION,
    ADD COLUMN "holdout_false_alarms" DOUBLE PRECISION,
    ADD COLUMN "judge" TEXT,
    ADD COLUMN "rescore_commit" TEXT;
