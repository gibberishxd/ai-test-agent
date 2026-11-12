-- Run 5, K2: the reviewer tier's share of a run's tokens and cost.
ALTER TABLE "runs" ADD COLUMN "reviewer_provider" TEXT,
ADD COLUMN "reviewer_model" TEXT,
ADD COLUMN "reviewer_input_tokens" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN "reviewer_output_tokens" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN "reviewer_cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0;
