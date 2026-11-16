-- Run 7, M4: critical flows (docs/DATABASE.md, "Flows").
--
-- flows: per target, the journeys a team wants covered on every run, in plain language. Once the
-- agent completes one, the steps it took are saved as a replayable script (JSON) and later runs
-- replay it without a model; the model is used only when a replay breaks.
-- flow_results: what happened to each journey in each run (the run report shows them).
-- Both are tenant tables under row-level security.

CREATE TABLE "flows" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "target_id" UUID NOT NULL,
    "name" TEXT NOT NULL,
    "goal" TEXT NOT NULL,
    "position" INTEGER NOT NULL DEFAULT 0,
    "script" JSONB,
    "script_saved_at" TIMESTAMPTZ(3),
    "last_status" TEXT,
    "last_run_id" UUID,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "flows_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "flows_name_length" CHECK (char_length(name) BETWEEN 1 AND 100),
    CONSTRAINT "flows_goal_length" CHECK (char_length(goal) BETWEEN 1 AND 2000),
    CONSTRAINT "flows_last_status_known" CHECK (
      last_status IS NULL OR last_status IN ('passed', 'replayed', 'repaired', 'failed', 'skipped'))
);
CREATE INDEX "flows_target_id_position_idx" ON "flows"("target_id", "position");
ALTER TABLE "flows" ADD CONSTRAINT "flows_workspace_id_fkey"
  FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "flows" ADD CONSTRAINT "flows_target_id_fkey"
  FOREIGN KEY ("target_id") REFERENCES "targets"("id") ON DELETE CASCADE ON UPDATE CASCADE;
CREATE TRIGGER flows_updated_at BEFORE UPDATE ON flows
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- A team defines 3–10 journeys per target (the roadmap's range); more would crowd out exploration.
CREATE OR REPLACE FUNCTION flows_per_target_limit() RETURNS trigger
  LANGUAGE plpgsql
  AS $$
BEGIN
  IF (SELECT count(*) FROM flows WHERE target_id = NEW.target_id) >= 10 THEN
    RAISE EXCEPTION 'a target has at most 10 critical flows' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END
$$;
CREATE TRIGGER flows_limit BEFORE INSERT ON flows
  FOR EACH ROW EXECUTE FUNCTION flows_per_target_limit();

CREATE TABLE "flow_results" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "run_id" UUID NOT NULL,
    "flow_id" UUID NOT NULL,
    "status" TEXT NOT NULL,
    "replayed" BOOLEAN NOT NULL DEFAULT false,
    "model_calls" INTEGER NOT NULL DEFAULT 0,
    "estimated_cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "detail" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "flow_results_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "flow_results_status_known" CHECK (status IN ('passed', 'replayed', 'repaired', 'failed', 'skipped')),
    CONSTRAINT "flow_results_counts_not_negative" CHECK (model_calls >= 0 AND estimated_cost_usd >= 0)
);
CREATE INDEX "flow_results_run_id_idx" ON "flow_results"("run_id");
ALTER TABLE "flow_results" ADD CONSTRAINT "flow_results_workspace_id_fkey"
  FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "flow_results" ADD CONSTRAINT "flow_results_run_id_fkey"
  FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "flow_results" ADD CONSTRAINT "flow_results_flow_id_fkey"
  FOREIGN KEY ("flow_id") REFERENCES "flows"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "flows" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "flows" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());
ALTER TABLE "flow_results" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "flow_results" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

GRANT SELECT, INSERT, UPDATE, DELETE ON flows, flow_results TO app_tenant;

DO $$
BEGIN
  IF current_user = 'ata_owner' OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ata_owner') THEN
    RETURN;
  END IF;
  ALTER TABLE flows OWNER TO ata_owner;
  ALTER TABLE flow_results OWNER TO ata_owner;
  ALTER FUNCTION flows_per_target_limit() OWNER TO ata_owner;
END
$$;
